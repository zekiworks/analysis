"""Serve Clef-flash over HTTP with TypeSafe's System One request and response format.

    ../clef/.venv/bin/python server.py --device cuda:2 --port 18095   # the Clef environment (torch 2.11, transformers 5.10.2)

POST /v1/systemone passes the request body to the release code's systemone() (model/joint_schema_model.py)
and returns its response: {"model", "answers", "usage"}, as Jev does. Requests are answered one at a time.
"""

import argparse
import json
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

MODEL_DIR = Path(__file__).resolve().parent / "model"
sys.path.insert(0, str(MODEL_DIR))
from joint_schema_model import load_release_model, systemone  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    server: "Server"

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/v1/systemone":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            request = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            if not isinstance(request, dict):
                raise ValueError("the request body must be a JSON object")
            with self.server.lock:
                response = systemone(self.server.model, self.server.processor, request)
            self.send_json(HTTPStatus.OK, response)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
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
    def __init__(self, address: tuple[str, int], model: Any, processor: Any) -> None:
        super().__init__(address, Handler)
        self.model, self.processor, self.lock = model, processor, threading.Lock()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", default="cuda:0", help="torch device (default: cuda:0)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18095)
    args = parser.parse_args()
    model, processor = load_release_model(MODEL_DIR, device=args.device)
    server = Server((args.host, args.port), model, processor)
    print(json.dumps({"url": f"http://{args.host}:{args.port}", "model": "clef-flash", "device": args.device}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
