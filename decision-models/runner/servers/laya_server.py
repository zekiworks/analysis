from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
import signal
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

os.environ.setdefault("USE_TF", "0")

import laya


DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "convaiinnovations" / "laya"
MAX_BODY_BYTES = 1_048_576
MAX_QUESTIONS = 64
MAX_OPTIONS = 32
REQUEST_TIMEOUT_SECONDS = 30
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class APIError(Exception):
    def __init__(self, status: HTTPStatus, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def validate_predict_request(payload: Any) -> tuple[str | dict[str, Any] | list[Any], dict[str, dict[str, Any]]]:
    if not isinstance(payload, dict):
        raise APIError(HTTPStatus.BAD_REQUEST, "invalid_request", "Request body must be a JSON object.")

    allowed_fields = {"state", "questions"}
    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "invalid_request",
            f"Unknown request field(s): {', '.join(unknown_fields)}.",
        )

    if "state" not in payload:
        raise APIError(HTTPStatus.BAD_REQUEST, "invalid_request", "Missing required field: state.")
    state = payload["state"]
    if isinstance(state, bool) or not isinstance(state, (str, dict, list)):
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "invalid_request",
            "state must be a string, object, or array.",
        )

    questions = payload.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "invalid_request",
            "questions must be a non-empty object.",
        )
    if len(questions) > MAX_QUESTIONS:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "invalid_request",
            f"questions may contain at most {MAX_QUESTIONS} entries.",
        )

    for question_id, question in questions.items():
        _validate_question(question_id, question)

    return state, questions


def _validate_question(question_id: Any, question: Any) -> None:
    if not isinstance(question_id, str) or not question_id.strip():
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "invalid_request",
            "Every question ID must be a non-empty string.",
        )
    if not isinstance(question, dict):
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "invalid_request",
            f"Question {question_id!r} must be an object.",
        )

    allowed_fields = {"type", "instructions", "criteria"}
    unknown_fields = sorted(set(question) - allowed_fields)
    if unknown_fields:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "invalid_request",
            f"Question {question_id!r} has unknown field(s): {', '.join(unknown_fields)}.",
        )

    question_type = question.get("type")
    if question_type not in {"choice", "score", "noul"}:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "invalid_request",
            f"Question {question_id!r} type must be choice, score, or noul.",
        )

    instructions = question.get("instructions")
    if not isinstance(instructions, str) or not instructions.strip():
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "invalid_request",
            f"Question {question_id!r} instructions must be a non-empty string.",
        )

    criteria = question.get("criteria")
    if question_type == "choice":
        if isinstance(criteria, dict):
            labels = list(criteria)
        elif isinstance(criteria, list):
            if not all(isinstance(label, str) and label.strip() for label in criteria):
                raise APIError(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_request",
                    f"Question {question_id!r} choice criteria list must contain non-empty strings.",
                )
            if len(set(criteria)) != len(criteria):
                raise APIError(
                    HTTPStatus.BAD_REQUEST,
                    "invalid_request",
                    f"Question {question_id!r} choice criteria labels must be unique.",
                )
            labels = criteria
        else:
            raise APIError(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                f"Question {question_id!r} choice criteria must be an object or array.",
            )
        if not all(isinstance(label, str) and label.strip() for label in labels):
            raise APIError(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                f"Question {question_id!r} choice criteria labels must be non-empty strings.",
            )
        _validate_option_count(question_id, labels)
    elif question_type == "score":
        if not isinstance(criteria, list):
            raise APIError(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                f"Question {question_id!r} score criteria must be an array.",
            )
        _validate_option_count(question_id, criteria)
    elif criteria is not None:
        if not isinstance(criteria, dict) or not set(criteria).issubset({"false", "true"}):
            raise APIError(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                f"Question {question_id!r} noul criteria may only define false and true.",
            )


def _validate_option_count(question_id: str, options: list[Any]) -> None:
    if not 2 <= len(options) <= MAX_OPTIONS:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "invalid_request",
            f"Question {question_id!r} must define between 2 and {MAX_OPTIONS} options.",
        )


class LayaRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LayaHTTP/1.0"
    sys_version = ""

    @property
    def laya_server(self) -> LayaHTTPServer:
        return cast(LayaHTTPServer, self.server)

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)

    def version_string(self) -> str:
        return self.server_version

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Endpoint not found.")

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/v1/predict":
            self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Endpoint not found.")
            return
        if not self._is_authorized():
            self._send_error(
                HTTPStatus.UNAUTHORIZED,
                "unauthorized",
                "A valid Bearer token is required.",
                {"WWW-Authenticate": "Bearer"},
            )
            return

        try:
            payload = self._read_json_body()
            state, questions = validate_predict_request(payload)
        except APIError as exc:
            self._send_error(exc.status, exc.code, exc.message)
            return

        try:
            with self.laya_server.inference_lock:
                result = self.laya_server.agent.predict(state, questions)
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            self._send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "prediction_rejected", str(exc))
            return
        except Exception:
            logging.exception("Laya prediction failed")
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "prediction_failed",
                "The model could not complete the prediction.",
            )
            return

        self._send_json(HTTPStatus.OK, result)

    def _is_authorized(self) -> bool:
        expected = self.laya_server.api_key
        if expected is None:
            return True

        scheme, separator, provided = self.headers.get("Authorization", "").partition(" ")
        if separator != " " or scheme.casefold() != "bearer" or not provided:
            return False
        return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))

    def _read_json_body(self) -> Any:
        if self.headers.get("Transfer-Encoding"):
            raise APIError(
                HTTPStatus.BAD_REQUEST,
                "unsupported_transfer_encoding",
                "Transfer-Encoding is not supported; send Content-Length.",
            )
        if self.headers.get_content_type() != "application/json":
            raise APIError(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "unsupported_media_type",
                "Content-Type must be application/json.",
            )

        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise APIError(
                HTTPStatus.LENGTH_REQUIRED,
                "length_required",
                "Content-Length is required.",
            )
        try:
            content_length = int(raw_length)
        except ValueError as exc:
            raise APIError(
                HTTPStatus.BAD_REQUEST,
                "invalid_content_length",
                "Content-Length must be an integer.",
            ) from exc
        if content_length <= 0:
            raise APIError(
                HTTPStatus.BAD_REQUEST,
                "invalid_content_length",
                "Content-Length must be greater than zero.",
            )
        if content_length > MAX_BODY_BYTES:
            raise APIError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "request_too_large",
                f"Request body exceeds the {MAX_BODY_BYTES}-byte limit.",
            )

        try:
            body = self.rfile.read(content_length)
        except TimeoutError as exc:
            raise APIError(
                HTTPStatus.REQUEST_TIMEOUT,
                "request_timeout",
                "Timed out while reading the request body.",
            ) from exc
        if len(body) != content_length:
            raise APIError(
                HTTPStatus.BAD_REQUEST,
                "incomplete_body",
                "Request body ended before Content-Length bytes were received.",
            )

        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise APIError(
                HTTPStatus.BAD_REQUEST,
                "invalid_json",
                "Request body must contain valid UTF-8 JSON.",
            ) from exc

    def _send_error(
        self,
        status: HTTPStatus,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._send_json(status, {"error": {"code": code, "message": message}}, headers)

    def _send_json(
        self,
        status: HTTPStatus,
        payload: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
        self.close_connection = True

    def log_message(self, format: str, *args: Any) -> None:
        logging.info("%s - %s", self.client_address[0], format % args)


class LayaHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        agent: laya.Agent,
        api_key: str | None,
    ) -> None:
        self.agent = agent
        self.api_key = api_key
        self.inference_lock = threading.Lock()
        super().__init__(server_address, LayaRequestHandler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve a local Laya model over HTTP.")
    parser.add_argument(
        "--model",
        default=os.environ.get("LAYA_MODEL", str(DEFAULT_MODEL_PATH)),
        help="Local model path or Hugging Face model ID.",
    )
    parser.add_argument(
        "--device",
        default=os.environ.get("LAYA_DEVICE"),
        help="Torch device such as cuda, cuda:0, or cpu (default: automatic).",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("LAYA_HOST", "127.0.0.1"),
        help="Address to bind (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        default=os.environ.get("LAYA_PORT", "8000"),
        type=int,
        help="TCP port (default: 8000).",
    )
    args = parser.parse_args()

    api_key = os.environ.get("LAYA_API_KEY")
    if args.host not in LOOPBACK_HOSTS and not api_key:
        parser.error("LAYA_API_KEY is required when binding to a non-loopback address.")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535.")
    return args


def _raise_keyboard_interrupt(_signum: int, _frame: Any) -> None:
    raise KeyboardInterrupt


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("LAYA_API_KEY") or None

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.info("Loading Laya model from %s", args.model)
    try:
        agent = laya.load(args.model, device=args.device)
    except Exception:
        logging.exception("Failed to load Laya model")
        raise SystemExit(1)

    try:
        server = LayaHTTPServer((args.host, args.port), agent, api_key)
    except OSError as exc:
        logging.error("Could not bind to %s:%s: %s", args.host, args.port, exc)
        raise SystemExit(1) from exc

    with server:
        signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
        bound_host, bound_port = server.server_address[:2]
        logging.info("Listening on http://%s:%s", bound_host, bound_port)
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            logging.info("Stopping Laya server")


if __name__ == "__main__":
    main()
