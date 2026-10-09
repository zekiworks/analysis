"""Serve GLiNER2.5 Multi over HTTP with TypeSafe's System One request and response format.

    .venv/bin/python server.py --device cuda:3 --port 18090
    .venv/bin/python server.py --device cuda:1 --port 18094 --model-dir model-decide --model-name gliner2.5-multi-decide

POST /v1/systemone takes {"state": ..., "questions": {id: {"type": "choice", "instructions": ...,
"criteria": {label: description}}}} and returns {"model", "answers", "usage"}, as Jev does. Each choice
question becomes one GLiNER classification task: the state is the text, the criteria are the labels
with their descriptions, and the instructions are the task prompt. GLiNER scores every label in one
pass and a softmax over them gives each label's probability; the answer is the most probable label.
Only choice questions are supported. Requests are answered one at a time.
"""

import argparse
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import torch
from gliner2 import AutoExtractor

MODEL_DIR = str(Path(__file__).resolve().parent / "model")
MODEL_NAME = "gliner2.5-multi-v1"


class RequestError(Exception):
    pass


def state_text(state: Any) -> str:
    if isinstance(state, str):
        return state
    return json.dumps(state, ensure_ascii=False)


def answer(model: Any, text: str, question_id: str, question: dict[str, Any]) -> dict[str, Any]:
    """One choice question's answer: GLiNER's softmax over its labels, all of them returned."""
    if question.get("type") != "choice":
        raise RequestError(f"{question_id}: only choice questions are supported")
    criteria = question.get("criteria")
    if isinstance(criteria, list):
        criteria = {str(label): str(label) for label in criteria}
    if not isinstance(criteria, dict) or len(criteria) < 2:
        raise RequestError(f"{question_id}: choice criteria must name at least two options")
    task: dict[str, Any] = {
        "labels": {str(label): str(description) for label, description in criteria.items()},
        # Multi-label decoding with a threshold of 0 returns every label; the explicit softmax keeps the
        # single-label probabilities. Neither changes what the model reads.
        "multi_label": True,
        "cls_threshold": 0.0,
        "class_act": "softmax",
    }
    if question.get("instructions"):
        task["prompt"] = str(question["instructions"])
    result = model.classify_text(text, {question_id: task}, include_confidence=True)[question_id]
    probabilities = {}
    for item in result:
        label, probability = (item["label"], item["confidence"]) if isinstance(item, dict) else item
        probabilities[str(label)] = float(probability)
    choice = max(probabilities, key=probabilities.__getitem__)
    return {"type": "choice", "choice": choice, "confidence": probabilities[choice], "probabilities": probabilities}


class Handler(BaseHTTPRequestHandler):
    server: "Server"

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/v1/systemone":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            request = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            if not isinstance(request, dict) or "state" not in request or not isinstance(request.get("questions"), dict):
                raise RequestError("state and questions are required")
            text = state_text(request["state"])
            with self.server.lock, torch.inference_mode():
                answers = {qid: answer(self.server.model, text, qid, question) for qid, question in request["questions"].items()}
            tokens = len(self.server.tokenizer(text, add_special_tokens=True)["input_ids"])
            self.send_json(
                HTTPStatus.OK,
                {"model": self.server.model_name, "answers": answers, "usage": {"input_tokens": tokens, "output_tokens": 0}},
            )
        except (RequestError, json.JSONDecodeError, ValueError) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

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
    def __init__(self, address: tuple[str, int], model: Any, tokenizer: Any, model_name: str) -> None:
        super().__init__(address, Handler)
        self.model, self.tokenizer, self.lock, self.model_name = model, tokenizer, threading.Lock(), model_name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", default="cuda:0", help="torch device (default: cuda:0)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18090)
    parser.add_argument(
        "--model-dir",
        default=MODEL_DIR,
        help="checkpoint directory, relative to this file; model-decide holds GLiNER2.5-multi-Decide (default: model)",
    )
    parser.add_argument("--model-name", default=MODEL_NAME, help=f"model name in responses (default: {MODEL_NAME})")
    args = parser.parse_args()
    model_dir = str(Path(__file__).resolve().parent / args.model_dir)
    model = AutoExtractor.from_pretrained(model_dir, map_location=args.device)
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    server = Server((args.host, args.port), model, tokenizer, args.model_name)
    print(json.dumps({"url": f"http://{args.host}:{args.port}", "model": args.model_name, "device": args.device}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
