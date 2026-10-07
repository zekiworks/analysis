"""Serve Metask-Jev-4B over HTTP with TypeSafe's System One request and response format.

    .venv/bin/python server.py --device cuda:1 --port 18092

POST /v1/systemone takes {"state": ..., "questions": {id: {"type", "instructions", "criteria"}}} and returns
{"model", "answers", "usage"}, as Jev does: a choice answer has choice, confidence and probabilities, a score
answer the expected score, and a noul answer the probability of true. Each question is scored by the vendor's
jev_scorer.score (one forward pass, a softmax over the option letters' logits) with the temperature that
model/temperature.json gives for its kind. The model's own serve.py returns no choice and uses older
temperatures, so it is not used. Requests are answered one at a time.
"""

import argparse
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import torch

from jev_schema import prepare_prompts
from jev_scorer import load_model, score

MODEL_DIR = Path(__file__).resolve().parent / "model"
MODEL_NAME = "metask-jev-4b-policy-mix"
MAX_INPUT_TOKENS = 4096


class RequestError(Exception):
    pass


def schema_for(question_id: str, question: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The question's kind and its schema in the vendor's format."""
    kind = question.get("type")
    criteria = question.get("criteria") or {}
    description = question.get("instructions") or question_id
    if kind == "noul":
        field = {
            "type": "boolean",
            "choices": [False, True],
            "choice_descriptions": {"false": criteria.get("false", "No"), "true": criteria.get("true", "Yes")},
        }
    elif kind == "score":
        labels = [str(index) for index in range(len(criteria))]
        field = {"type": "enum", "choices": labels, "choice_descriptions": dict(zip(labels, map(str, criteria)))}
    elif kind == "choice":
        labels = [str(label) for label in (criteria if isinstance(criteria, (dict, list)) else [])]
        descriptions = {label: str(criteria[label] or label) for label in labels} if isinstance(criteria, dict) else {}
        field = {"type": "enum", "choices": labels, "choice_descriptions": descriptions}
    else:
        raise RequestError(f"{question_id}: type must be noul, choice or score")
    return kind, {"decision": {"description": description, **field}}


def answer(server: "Server", state: str, question_id: str, question: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """One question's System One answer and its prompt's token count."""
    kind, schema = schema_for(question_id, question)
    try:
        tokens = len(prepare_prompts(server.tokenizer, state, schema, MAX_INPUT_TOKENS).full_ids[0])
        result = score(server.model, server.tokenizer, state, schema, server.temperatures[kind], MAX_INPUT_TOKENS)
    except ValueError as exc:
        raise RequestError(f"{question_id}: {exc}") from exc
    probabilities = result["probabilities"]
    if kind == "noul":
        return {"type": "noul", "noul": probabilities["true"]}, tokens
    if kind == "score":
        levels = list(probabilities)
        return {
            "type": "score",
            "score": sum(index * probabilities[level] for index, level in enumerate(levels)),
            "confidence": max(probabilities.values()),
            "probabilities": probabilities,
        }, tokens
    choice = str(result["prediction"])
    return {"type": "choice", "choice": choice, "confidence": probabilities[choice], "probabilities": probabilities}, tokens


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
            state = request["state"] if isinstance(request["state"], str) else json.dumps(request["state"], ensure_ascii=False)
            answers, input_tokens = {}, 0
            with self.server.lock:
                for question_id, question in request["questions"].items():
                    answers[question_id], tokens = answer(self.server, state, question_id, question)
                    input_tokens += tokens
            self.send_json(
                HTTPStatus.OK,
                {"model": MODEL_NAME, "answers": answers, "usage": {"input_tokens": input_tokens, "output_tokens": 0}},
            )
        except (RequestError, json.JSONDecodeError) as exc:
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
    def __init__(self, address: tuple[str, int], model: Any, tokenizer: Any, temperatures: dict[str, float]) -> None:
        super().__init__(address, Handler)
        self.model, self.tokenizer, self.temperatures = model, tokenizer, temperatures
        self.lock = threading.Lock()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", default="cuda:0", help="torch device (default: cuda:0)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18092)
    args = parser.parse_args()
    temperatures = json.loads((MODEL_DIR / "temperature.json").read_text(encoding="utf-8"))["by_kind"]
    model, tokenizer, _ = load_model(str(MODEL_DIR), device=(args.device, torch.bfloat16))
    server = Server((args.host, args.port), model, tokenizer, temperatures)
    print(
        json.dumps({"url": f"http://{args.host}:{args.port}", "model": MODEL_NAME, "device": args.device, "temperatures": temperatures}),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
