"""Serve GLiClass v4 Edge over HTTP with TypeSafe's System One request and response format.

    pip install gliclass==0.1.22
    .venv/bin/python gliclass_server.py --device cuda:0 --port 18096
    .venv/bin/python gliclass_server.py --device cpu --port 18096 --model /path/to/checkpoint

gliclass 0.1.22 (github.com/Knowledgator/GLiClass tag v0.1.22, af82d42) is what the model card's `pip install gliclass -U`
installs on 11 November 2026. The checkpoint is knowledgator/gliclass-v4-edge at 885af1a unless --model and --revision
name another.

POST /v1/systemone takes {"model"?, "state": ..., "questions": {id: {"type": "choice", "instructions": ...,
"criteria": {label: description}}}} and returns {"model", "answers", "usage"}, as Jev does. This is the model card's
own System One mapping ("Serving a Jev-style decision API", jev_api.py in the card) for choice questions: each question
is one GLiClass pass in which the state is the text (a list or object state rendered as the card renders it), the
instructions are the prompt (the library's `prompt` argument), and every option's description is a label (its key when
the description is null). The library packs them into one sequence, `<<LABEL>>option...<<SEP>>instructions` then the text
(UniEncoderZeroShotClassificationPipeline.prepare_input), so the options and instructions share the token budget with the
state. Each option's probability is the softmax over the model's calibrated logits for the labels, as the card's server
and the pipeline's single-label mode compute it, here in float64 so that the reported values sum to 1; the answer is the
most probable option. input_tokens counts every token of each question's sequence, [CLS] and [SEP] included.

The library's tokenizer call truncates to the pipeline's max_length without notice, so, as in the card's server, the
pipeline is built with no effective limit and a sequence longer than --max-length tokens (default 16384, the card's
MAX_LENGTH and its Decision Index setting) is refused with HTTP 422, never cut. Also refused with 422: questions other
than choice, fewer than two options, an option or state holding the `<<LABEL>>` marker (the model would read another
option), images anywhere in the request (the model reads text only), request fields other than model, state and
questions, and a model field naming another checkpoint (absent is accepted). Requests are answered one at a time.
"""

import argparse
import json
import math
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import torch
from gliclass import GLiClassModel, ZeroShotClassificationPipeline
from transformers import AutoTokenizer

MODEL_ID = "knowledgator/gliclass-v4-edge"
REVISION = "885af1af8a07edf4ed34df83ca0d995ed8201283"
MAX_LENGTH = 16384
FIELDS = {"model", "state", "questions"}


class RequestError(Exception):
    pass


def as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def has_image(value: Any) -> bool:
    """Whether a state holds an image part (OpenAI-style `image_url`/`input_image` parts or TypeSafe-style `image`
    parts), which this text-only model would drop."""
    if isinstance(value, dict):
        if value.get("type") in ("image", "image_url", "input_image") or "image_url" in value:
            return True
        return any(has_image(item) for item in value.values())
    if isinstance(value, list):
        return any(has_image(item) for item in value)
    return False


def render_state(state: Any) -> str:
    """The card's render_state: a string as is, a list as `- item` lines, an object as `key: value` lines."""
    if state in (None, "", {}, []):
        return ""
    if isinstance(state, str):
        return state
    if isinstance(state, list):
        return "\n".join(f"- {as_text(item)}" for item in state)
    if not isinstance(state, dict):
        return as_text(state)
    lines = []
    for key, value in state.items():
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            lines += [f"{key}:"] + [f"- {item}" for item in value]
        else:
            lines.append(f"{key}: {as_text(value)}")
    return "\n".join(lines)


def question_parts(question_id: str, question: Any) -> tuple[list[str], list[str], str | None]:
    """A choice question's option keys, its labels (the descriptions, or the key when one is null) and its prompt."""
    if not isinstance(question, dict) or question.get("type") != "choice":
        raise RequestError(f"{question_id}: only choice questions are supported")
    criteria = question.get("criteria")
    if not isinstance(criteria, dict) or len(criteria) < 2:
        raise RequestError(f"{question_id}: choice criteria must map at least two options to their descriptions")
    keys = [str(key) for key in criteria]
    labels = [as_text(value) if value is not None else str(key) for key, value in criteria.items()]
    prompt = as_text(question.get("instructions") or "") or None
    return keys, labels, prompt


def encode(pipe: Any, text: str, labels: list[str], prompt: str | None, max_length: int) -> dict[str, torch.Tensor]:
    """The library's own input (pipe.prepare_inputs, as the card's server calls it), refused when it is over max_length
    tokens or when its <<LABEL>> markers are not exactly the options'."""
    inputs = pipe.prepare_inputs([text], labels, same_labels=True, prompt=prompt)
    length = inputs["input_ids"].shape[-1]
    if length > max_length:
        raise RequestError(f"input of {length} tokens exceeds the {max_length}-token limit")
    markers = int((inputs["input_ids"][0] == pipe.model.config.class_token_index).sum())
    if markers != len(labels):
        raise RequestError(f"the input holds {markers} <<LABEL>> markers for {len(labels)} options")
    return inputs


def answer(pipe: Any, text: str, question_id: str, question: Any, max_length: int) -> tuple[dict[str, Any], int]:
    """One choice question's answer, a softmax over the calibrated label logits, and its input tokens."""
    keys, labels, prompt = question_parts(question_id, question)
    inputs = encode(pipe, text, labels, prompt, max_length)
    logits = pipe.model(**inputs, max_num_classes=len(labels)).logits[0, : len(labels)].double()
    probabilities = dict(zip(keys, torch.softmax(logits, dim=-1).tolist(), strict=True))
    if not all(math.isfinite(value) for value in probabilities.values()):
        raise RuntimeError(f"{question_id}: the model returned non-finite logits")
    choice = max(keys, key=probabilities.__getitem__)
    result = {"type": "choice", "choice": choice, "confidence": probabilities[choice], "probabilities": probabilities}
    return result, int(inputs["input_ids"].shape[-1])


def respond(pipe: Any, request: Any, model_name: str, max_length: int) -> dict[str, Any]:
    if not isinstance(request, dict) or "state" not in request or not isinstance(request.get("questions"), dict):
        raise RequestError("state and questions are required")
    if not request["questions"]:
        raise RequestError("questions is empty")
    extra = sorted(set(request) - FIELDS)
    if extra:
        raise RequestError("unsupported request fields: " + ", ".join(extra))
    if request.get("model") is not None and request["model"] != model_name:
        raise RequestError(f"this server serves {model_name}, not {request['model']!r}")
    if has_image(request["state"]):
        raise RequestError("images are not supported: this model reads text only")
    text = render_state(request["state"])
    answers, tokens = {}, 0
    for question_id, question in request["questions"].items():
        answers[question_id], length = answer(pipe, text, question_id, question, max_length)
        tokens += length
    return {"model": model_name, "answers": answers, "usage": {"input_tokens": tokens, "output_tokens": 0}}


class Handler(BaseHTTPRequestHandler):
    server: "Server"

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/v1/systemone":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            request = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON: {exc}"})
            return
        try:
            with self.server.lock, torch.inference_mode():
                body = respond(self.server.pipe, request, self.server.model_name, self.server.max_length)
        except RequestError as exc:
            self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
            return
        self.send_json(HTTPStatus.OK, body)

    def send_json(self, status: HTTPStatus, body: dict[str, Any]) -> None:
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


class Server(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], pipe: Any, model_name: str, max_length: int) -> None:
        super().__init__(address, Handler)
        self.pipe, self.model_name, self.max_length, self.lock = pipe, model_name, max_length, threading.Lock()


def pipeline(model: Any, tokenizer: Any, device: str) -> Any:
    """The card's pipeline (single-label, no progress bar) with no effective max_length, so the tokenizer never cuts;
    encode applies the limit instead."""
    return ZeroShotClassificationPipeline(
        model, tokenizer, max_length=10**9, classification_type="single-label", device=device, progress_bar=False
    ).pipe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", default="cuda:0", help="torch device (default: cuda:0)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18096)
    parser.add_argument("--model", default=MODEL_ID, help=f"Hugging Face ID or checkpoint directory (default: {MODEL_ID})")
    parser.add_argument("--revision", default=REVISION, help="commit of a Hugging Face ID (default: the pinned 885af1a)")
    parser.add_argument("--model-name", default=MODEL_ID, help=f"model name in responses (default: {MODEL_ID})")
    parser.add_argument("--max-length", type=int, default=MAX_LENGTH, help=f"longest input in tokens (default: {MAX_LENGTH})")
    args = parser.parse_args()
    # The card's precision: bfloat16 on a GPU, float32 on the CPU.
    dtype = torch.float32 if args.device == "cpu" else torch.bfloat16
    model = GLiClassModel.from_pretrained(args.model, revision=args.revision, dtype=dtype).to(args.device).eval()
    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision)
    server = Server((args.host, args.port), pipeline(model, tokenizer, args.device), args.model_name, args.max_length)
    print(json.dumps({"url": f"http://{args.host}:{args.port}", "model": args.model_name, "device": args.device,
                      "dtype": str(dtype), "max_length": args.max_length}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
