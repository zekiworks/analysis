"""Serve Liquid AI's open d1 decision model LiquidAI/d1-2B over HTTP with TypeSafe's System One request and response format.

    CUDA_VISIBLE_DEVICES=N HF_HUB_OFFLINE=1 .venv/bin/python d1_server.py --model LiquidAI/d1-2B \
        --revision 10e7671d44e4b37700020b1eed3f594c5f2af0b4 --host HOST --port PORT

The model loads as its model card shows: transformers' AutoModel with trust_remote_code=True (Liquid's own model code,
from the same revision), in bfloat16 on the GPU. Each request is answered by the card's call, model.system_one(state,
questions, media), unchanged: one forward pass and no sampling. Environment: Python 3.12 with only the card's
requirements (transformers>=5.19, torch, torchvision, pillow); GPU: one RTX PRO 6000 Blackwell (96 GB).

POST /v1/systemone takes the System One request (state and named questions) with an optional top-level `images` list of
data URLs, decoded to the PIL images system_one takes as media (through transformers' load_image, as in the card). An
empty state with images goes in as None, which the card gives for media that are the whole state. It returns
{"model", "answers", "usage"}, the answers and usage as system_one returns them. The model field must name the loaded
model (--model), so a run never reaches the wrong one on a shared port. Requests are answered one at a time; each
response carries an x-request-id header.
"""

import argparse
import base64
import io
import json
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
            media = [self.server.picture(image) for image in images]
            state = request.get("state")
            if media and state in (None, ""):
                state = None
            with self.server.lock:
                out = self.server.model.system_one(state, questions, media or None)
            self.send_json(HTTPStatus.OK, {"model": self.server.name, "answers": out["answers"], "usage": out["usage"]})
        # Liquid's code raises ValueError for a request it cannot answer (an unknown question type, bad criteria).
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
    def __init__(self, address: tuple[str, int], model: Any, load_image: Any, name: str) -> None:
        super().__init__(address, Handler)
        self.model, self.load_image, self.name = model, load_image, name
        self.lock = threading.Lock()

    def picture(self, url: str) -> Any:
        """A data URL as the PIL image load_image makes of it (EXIF orientation applied, RGB)."""
        from PIL import Image

        return self.load_image(Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, help="the Hugging Face model ID, which every request's model field must give")
    parser.add_argument("--revision", required=True, help="the model's commit on Hugging Face")
    parser.add_argument("--device", default="cuda:0", help="torch device (default: cuda:0)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18100)
    args = parser.parse_args()
    import torch
    import transformers
    from transformers import AutoModel
    from transformers.image_utils import load_image

    model = AutoModel.from_pretrained(args.model, revision=args.revision, trust_remote_code=True, dtype=torch.bfloat16)
    model = model.to(args.device)
    server = Server((args.host, args.port), model, load_image, args.model)
    print(json.dumps({"url": f"http://{args.host}:{args.port}", "model": args.model, "revision": args.revision,
                      "device": args.device, "torch": torch.__version__, "transformers": transformers.__version__}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
