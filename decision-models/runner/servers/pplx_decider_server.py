"""Serve a Perplexity Decider v1.2 checkpoint over HTTP with TypeSafe's System One request and response format.

    .venv-v1.2/bin/python pplx_decider_server.py --checkpoint checkpoint-v1.2 --host 0.0.0.0 --port 18097
    .venv-v1.2/bin/python pplx_decider_server.py --checkpoint checkpoint-flash-v1.2 --host 0.0.0.0 --port 18097

--checkpoint is a downloaded perplexity-ai/pplx-decider-v1.2 or perplexity-ai/pplx-decider-flash-v1.2 repository;
.venv-v1.2 holds only its requirements.txt, so the package runs as Perplexity verified it (no flash-linear-attention).
Torch sends some operations to Triton kernels, whose first use compiles a helper against Python's headers: build the
environment on a Python that has them (uv's own Python 3.12 does; a system Python may not).
POST /v1/systemone passes the request body, without its model field, to the pplx_decider package the checkpoint ships
(source/src): Decider.decide on its reference path, one request per call, with the checkpoint's fitted temperature.
It returns {"model", "answers", "usage"}, as Jev does. The model field must name the loaded checkpoint (the repo_id in
its release-manifest.json, such as pplx-decider-v1.2), so a run never reaches the wrong one on the shared port.
Requests are answered one at a time; each response carries an x-request-id header.
"""

import argparse
import json
import sys
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


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
            model = request.pop("model", self.server.name)
            if model != self.server.name:
                raise ValueError(f"this server answers for {self.server.name}, not {model}")
            with self.server.lock:
                response = self.server.decider.decide(request)
            self.send_json(HTTPStatus.OK, {"model": self.server.name, **response})
        # pplx_decider's RequestError and LengthError are ValueErrors.
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
    def __init__(self, address: tuple[str, int], decider: Any, name: str) -> None:
        super().__init__(address, Handler)
        self.decider, self.name, self.lock = decider, name, threading.Lock()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkpoint", type=Path, required=True, help="the downloaded checkpoint repository")
    parser.add_argument("--device", default="cuda:0", help="torch device (default: cuda:0)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18097)
    args = parser.parse_args()
    checkpoint = args.checkpoint.resolve()
    name = json.loads((checkpoint / "release-manifest.json").read_text())["repo_id"].split("/")[-1]
    sys.path.insert(0, str(checkpoint / "source" / "src"))
    from pplx_decider import Decider

    decider = Decider.from_pretrained(checkpoint, device=args.device)  # reference path (fast=False)
    server = Server((args.host, args.port), decider, name)
    print(json.dumps({"url": f"http://{args.host}:{args.port}", "model": name, "device": args.device}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
