"""Serve Nace.AI's Drex Max v1 open weights over HTTP with TypeSafe's System One request and response format.

    CUDA_VISIBLE_DEVICES=N .venv-drex-max/bin/python drex_max_server.py --checkpoint SNAPSHOT --code CHECKOUT \
        --name drex-max-v1 --host HOST --port PORT

SNAPSHOT is the Hugging Face snapshot of nace-ai/drex-max-v1 at revision cac65e1982a0237e996419ba559004522d9a33ac (bf16,
49 GB); CHECKOUT is github.com/nace-ai/drex-decision-models at commit e206b278e3988ad1b58e6f1556b559a65947a4e6 (30 October
2026), whose drex_max package is Nace's own loader; .venv-drex-max (Python 3.12) holds only that commit's
models/drex-max-v1/requirements.txt. GPU: one RTX PRO 6000 Blackwell (96 GB), bf16, the loader's default on CUDA.
Nace ships no HTTP server for Drex Max, only `python -m drex_max` for one request at a time. POST /v1/systemone takes the
System One request (state and questions) with an optional top-level `images` list of data URLs, and scores each question
as that command does: drex_max.model.DecisionModel.predict on {state, question, images}, then drex_max.model.answer, both
unchanged (the loader applies the checkpoint's non-causal full attention and its temperature). It returns
{"model", "answers", "usage"}; usage.input_tokens counts the prompt tokens the loader's processor makes of each question,
images included. The model field must name the loaded checkpoint (--name), so a run never reaches the wrong model on the
shared port. Only data URLs are accepted as images (the loader would also open a file path). A request longer than
--max-length tokens (default: the loader's, 16,384 or DREX_MAX_CONTEXT) is refused with 400, never cut. Requests are
answered one at a time; each response carries an x-request-id header.
"""

import argparse
import json
import subprocess
import sys
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class Handler(BaseHTTPRequestHandler):
    server: "Server"

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] == "/health":
            self.send_json(HTTPStatus.OK, {"status": "ok", "model": self.server.name})
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/v1/systemone":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            request = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            if not isinstance(request, dict):
                raise ValueError("the request body must be a JSON object")
            model = request.get("model", self.server.name)
            if model != self.server.name:
                raise ValueError(f"this server answers for {self.server.name}, not {model}")
            questions = request.get("questions")
            if not isinstance(questions, dict) or not questions:
                raise ValueError("questions must be a nonempty object")
            images = request.get("images") or []
            if not isinstance(images, list) or not all(isinstance(image, str) and image.startswith("data:image/") for image in images):
                raise ValueError("images must be a list of data:image/ URLs")
            with self.server.lock:
                answers, tokens = self.server.score(request.get("state", ""), questions, images)
            self.send_json(HTTPStatus.OK, {"model": self.server.name, "answers": answers, "usage": {"input_tokens": tokens}})
        # drex_max raises ValueError for a request it cannot score (too long, too many options, a bad image).
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def send_json(self, status: HTTPStatus, body: dict[str, Any]) -> None:
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("x-request-id", uuid.uuid4().hex)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


class Server(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], model: Any, answer: Any, name: str, max_length: int) -> None:
        super().__init__(address, Handler)
        self.model, self.answer, self.name, self.max_length = model, answer, name, max_length
        self.lock = threading.Lock()

    def score(self, state: Any, questions: dict[str, Any], images: list[str]) -> tuple[dict[str, Any], int]:
        """Each question scored as `python -m drex_max` scores it, and the prompt tokens of all of them."""
        answers, tokens = {}, 0
        for name, question in questions.items():
            row = {"state": state, "question": question}
            if images:
                row["images"] = images
            # The loader's own encoding of the row, for its token count only; predict encodes it again.
            tokens += int(self.model.prepare([row], self.max_length).inputs["input_ids"].shape[1])
            answers[name] = self.answer(question, self.model.predict([row], max_length=self.max_length)[0])
        return answers, tokens


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkpoint", type=Path, required=True, help="the downloaded nace-ai/drex-max-v1 snapshot")
    parser.add_argument("--code", type=Path, required=True, help="a checkout of github.com/nace-ai/drex-decision-models")
    parser.add_argument("--name", required=True, help="the checkpoint's name, which every request's model field must give")
    parser.add_argument("--max-length", type=int, help="longest request in tokens (default: the loader's)")
    parser.add_argument("--device", default="cuda:0", help="torch device (default: cuda:0)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18099)
    args = parser.parse_args()
    code = args.code.resolve()
    sys.path.insert(0, str(code))
    from drex_max.model import MAX_LENGTH, DecisionModel, answer

    commit = subprocess.run(["git", "-C", str(code), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    model = DecisionModel(args.checkpoint.resolve(), device=args.device)  # bf16 on CUDA, the loader's default
    max_length = args.max_length or MAX_LENGTH
    server = Server((args.host, args.port), model, answer, args.name, max_length)
    print(json.dumps({"url": f"http://{args.host}:{args.port}", "model": args.name, "checkpoint": str(args.checkpoint),
                      "code_commit": commit, "device": args.device, "max_length": max_length}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
