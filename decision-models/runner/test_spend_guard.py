"""Offline tests of the paid route's spending cap (SpendGuard; Zeki #9930): a local HTTP server stands in for
OpenRouter, so no request leaves the machine and nothing is billed. Run: python3 -m unittest test_spend_guard."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import benchmark_ollama as bo

PRICE = bo.Price("test price", "local", "2026-11-16", input=1.0, output=1.0)  # USD per 1M tokens
PAYLOAD = {"model": "m", "messages": [{"role": "user", "content": "x" * 400}], "max_tokens": 1000}
BODY = len(json.dumps(PAYLOAD, ensure_ascii=False, separators=(",", ":")).encode())


class Server:
    """A chat completions stand-in: replies in order from `script` (status, reply or None), then the last one."""

    def __init__(self, script: list[tuple[int, dict | None]]) -> None:
        self.script, self.count, self.lock = script, 0, threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                self.rfile.read(int(self.headers["Content-Length"]))
                with outer.lock:
                    status, reply = outer.script[min(outer.count, len(outer.script) - 1)]
                    outer.count += 1
                data = json.dumps(reply if reply is not None else {"error": "x"}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1/chat/completions"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def reply(cost: float | None) -> dict:
    usage = {"prompt_tokens": 10, "completion_tokens": 10}
    if cost is not None:
        usage["cost"] = cost
    return {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}], "usage": usage}


class SpendGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.ledger = Path(self.dir.name) / "share.jsonl"
        self.bound = ((BODY + getattr(bo, "SPEND_INPUT_MARGIN", 1024)) + 1000) / 1_000_000

    def tearDown(self) -> None:
        self.dir.cleanup()

    def send(self, server: Server, guard: bo.SpendGuard | None) -> None:
        bo.post_json(server.url, PAYLOAD, {"Content-Type": "application/json"}, 5, None, "OpenRouter", guard)

    def test_worst_case_bound(self) -> None:
        guard = bo.SpendGuard(self.ledger, 1.0, PRICE)
        self.assertAlmostEqual(guard.bound(BODY, 1000), self.bound)

    def test_without_a_guard_nothing_stops_requests(self) -> None:
        # the gap: post_json alone sends every request it is given
        server = Server([(200, reply(1.0))])
        try:
            for _ in range(5):
                self.send(server, None)
        finally:
            server.close()
        self.assertEqual(server.count, 5)

    def test_cap_holds_back_the_request_that_could_pass_it(self) -> None:
        guard = bo.SpendGuard(self.ledger, 2.5 * self.bound, PRICE)
        server = Server([(200, reply(0.9 * self.bound))])
        try:
            self.send(server, guard)
            self.send(server, guard)
            with self.assertRaises(bo.SpendCapReached):
                self.send(server, guard)
        finally:
            server.close()
        self.assertEqual(server.count, 2)  # the third was never sent
        lines = [json.loads(line) for line in self.ledger.read_text().splitlines()]
        self.assertAlmostEqual(bo.SpendGuard.exposure(lines), 1.8 * self.bound)

    def test_missing_usage_counts_the_whole_worst_case(self) -> None:
        guard = bo.SpendGuard(self.ledger, 2.5 * self.bound, PRICE)
        server = Server([(200, reply(None))])
        try:
            self.send(server, guard)
            self.send(server, guard)
            with self.assertRaises(bo.SpendCapReached):
                self.send(server, guard)
        finally:
            server.close()
        lines = [json.loads(line) for line in self.ledger.read_text().splitlines()]
        self.assertAlmostEqual(bo.SpendGuard.exposure(lines), 2 * self.bound)

    def test_failed_attempts_are_reserved_and_charged_whole(self) -> None:
        guard = bo.SpendGuard(self.ledger, 10 * self.bound, PRICE)
        server = Server([(500, None), (200, reply(0.5 * self.bound))])
        try:
            with mock.patch.object(bo.time, "sleep"):
                self.send(server, guard)
        finally:
            server.close()
        lines = [json.loads(line) for line in self.ledger.read_text().splitlines()]
        self.assertEqual(sum(line["t"] == "reserve" for line in lines), 2)  # the retry reserved again
        self.assertAlmostEqual(bo.SpendGuard.exposure(lines), 1.5 * self.bound)

    def test_cost_above_the_worst_case_is_charged_as_reported(self) -> None:
        guard = bo.SpendGuard(self.ledger, 10 * self.bound, PRICE)
        server = Server([(200, reply(3 * self.bound))])
        try:
            self.send(server, guard)
        finally:
            server.close()
        lines = [json.loads(line) for line in self.ledger.read_text().splitlines()]
        self.assertAlmostEqual(bo.SpendGuard.exposure(lines), 3 * self.bound)

    def test_unsettled_reservation_from_a_crash_counts_in_a_new_process(self) -> None:
        guard = bo.SpendGuard(self.ledger, 1.5 * self.bound, PRICE)
        guard.reserve(BODY, 1000)  # sent, then the process died before its reply
        again = bo.SpendGuard(self.ledger, 1.5 * self.bound, PRICE)
        with self.assertRaises(bo.SpendCapReached):
            again.reserve(BODY, 1000)

    def test_a_shares_cap_never_changes(self) -> None:
        bo.SpendGuard(self.ledger, 6.0, PRICE)
        with self.assertRaises(ValueError):
            bo.SpendGuard(self.ledger, 7.0, PRICE)

    def test_concurrent_requests_never_pass_the_cap(self) -> None:
        guard = bo.SpendGuard(self.ledger, 3.5 * self.bound, PRICE)
        server = Server([(200, reply(self.bound))])
        blocked = []

        def worker() -> None:
            try:
                self.send(server, guard)
            except bo.SpendCapReached:
                blocked.append(1)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        try:
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        finally:
            server.close()
        self.assertEqual(server.count, 3)
        self.assertEqual(len(blocked), 5)
        lines = [json.loads(line) for line in self.ledger.read_text().splitlines()]
        self.assertLessEqual(bo.SpendGuard.exposure(lines), 3.5 * self.bound)

    def test_a_halt_from_a_known_overrun_holds_in_a_new_process(self) -> None:
        guard = bo.SpendGuard(self.ledger, 10 * self.bound, PRICE)
        guard.settle(guard.reserve(BODY, 1000), reply(2 * self.bound))
        again = bo.SpendGuard(self.ledger, 10 * self.bound, PRICE)
        with self.assertRaises(bo.SpendCapReached):
            again.reserve(BODY, 1000)
        lines = [json.loads(line) for line in self.ledger.read_text().splitlines()]
        self.assertAlmostEqual(bo.SpendGuard.exposure(lines), 2 * self.bound)  # the larger known charge is kept

    def test_a_reservation_without_a_valid_worst_case_stops_the_ledger(self) -> None:
        guard = bo.SpendGuard(self.ledger, 10 * self.bound, PRICE)
        with self.ledger.open("a") as handle:
            handle.write('{"t":"reserve","id":"x","bound":-1}\n')
        with self.assertRaises(ValueError):
            guard.reserve(BODY, 1000)

    def test_records_after_a_cut_line_stay_readable(self) -> None:
        guard = bo.SpendGuard(self.ledger, 10 * self.bound, PRICE)
        with self.ledger.open("a") as handle:
            handle.write('{"t":"res')
        guard.reserve(BODY, 1000)
        guard.reserve(BODY, 1000)
        lines = [json.loads(line) for line in self.ledger.read_text().splitlines() if line != '{"t":"res']
        self.assertEqual(sum(line["t"] == "reserve" for line in lines), 2)

    def test_an_empty_reply_held_back_twice_still_gets_one_more_ask_only(self) -> None:
        def empty() -> dict:
            r = reply(0.0)
            r["choices"][0]["message"]["content"] = ""
            return r
        guard = bo.SpendGuard(self.ledger, 10 * self.bound, PRICE)
        server = Server([(200, empty()), (200, empty()), (200, reply(0.0))])
        real_reserve, calls = guard.reserve, {"n": 0}

        def reserve(*args):
            # the first ask goes out (empty); its once-more ask is held back twice in a row, then let through
            calls["n"] += 1
            if calls["n"] in (2, 3):
                raise bo.SpendCapReached("held back")
            return real_reserve(*args)
        try:
            with mock.patch.object(guard, "reserve", side_effect=reserve):
                for _ in range(2):
                    with self.assertRaises(bo.SpendCapReached):
                        bo.post_chat(server.url, PAYLOAD, {}, 5, None, "OpenRouter", True, guard)
                result, first = bo.post_chat(server.url, PAYLOAD, {}, 5, None, "OpenRouter", True, guard)
        finally:
            server.close()
        self.assertEqual(server.count, 2)
        self.assertTrue(bo.empty_reply(result))
        self.assertTrue(bo.empty_reply(first))

    def test_a_stop_after_the_once_more_ask_went_out_never_asks_a_third_time(self) -> None:
        def empty() -> dict:
            r = reply(0.0)
            r["choices"][0]["message"]["content"] = ""
            return r
        server = Server([(200, empty()), (200, reply(0.0)), (200, reply(0.0))])
        code = """import os,sys
from pathlib import Path
import benchmark_ollama as bo
from test_spend_guard import PRICE,PAYLOAD
p,url,cap=sys.argv[1:]
g=bo.SpendGuard(Path(p),float(cap),PRICE)
append=g._append
def cut(line):
    append(line)
    if line.get("t")=="reserve" and line.get("empty_key"):os._exit(73)
g._append=cut
bo.post_chat(url,PAYLOAD,{},5,None,"OpenRouter",True,g)
"""
        try:
            done = subprocess.run([sys.executable, "-B", "-c", code, str(self.ledger), server.url, str(10 * self.bound)],
                                  capture_output=True, text=True, timeout=15)
            self.assertEqual(done.returncode, 73, done.stdout + done.stderr)
            self.assertEqual(server.count, 1)  # stopped after the reservation, before the send
            with self.assertRaises(bo.UncertainRetry):  # reply unknown: neither asked a third time nor scored empty
                bo.post_chat(server.url, PAYLOAD, {}, 5, None, "OpenRouter", True,
                             bo.SpendGuard(self.ledger, 10 * self.bound, PRICE))
        finally:
            server.close()
        self.assertEqual(server.count, 1)

    def test_a_failed_once_more_ask_may_be_asked_again_on_resume(self) -> None:
        def empty() -> dict:
            r = reply(0.0)
            r["choices"][0]["message"]["content"] = ""
            return r
        guard = bo.SpendGuard(self.ledger, 10 * self.bound, PRICE)
        good = reply(0.0)
        good["choices"][0]["message"]["content"] = '{"synthetic":"nonempty"}'
        server = Server([(200, empty())] + [(500, None)] * (bo.JEV_MAX_RETRIES + 1) + [(200, good)])
        try:
            with mock.patch.object(bo.time, "sleep"), self.assertRaises(RuntimeError):
                bo.post_chat(server.url, PAYLOAD, {}, 5, None, "OpenRouter", True, guard)
            result, first = bo.post_chat(server.url, PAYLOAD, {}, 5, None, "OpenRouter", True, guard)
        finally:
            server.close()
        self.assertFalse(bo.empty_reply(result))  # the once-more ask's reply, not a fresh first attempt
        self.assertTrue(bo.empty_reply(first))
        self.assertEqual(server.count, bo.JEV_MAX_RETRIES + 3)

    def test_a_repeat_run_does_not_replay_another_runs_outcome(self) -> None:
        def answer(text: str) -> dict:
            r = reply(0.0)
            r["choices"][0]["message"]["content"] = text
            return r
        guard = bo.SpendGuard(self.ledger, 10 * self.bound, PRICE)
        server = Server([(200, answer("")), (200, answer("first run's second reply")), (200, answer("repeat run's reply"))])
        try:
            with guard.scoped("run 1"):
                bo.post_chat(server.url, PAYLOAD, {}, 5, None, "OpenRouter", True, guard)
            with guard.scoped("run 2"):
                result, first = bo.post_chat(server.url, PAYLOAD, {}, 5, None, "OpenRouter", True, guard)
        finally:
            server.close()
        self.assertEqual(server.count, 3)
        self.assertEqual(result["choices"][0]["message"]["content"], "repeat run's reply")
        self.assertIsNone(first)

    def test_an_outcome_replays_until_the_caller_acknowledges_it_then_asks_afresh(self) -> None:
        def answer(text: str) -> dict:
            r = reply(0.0)
            r["choices"][0]["message"]["content"] = text
            return r
        guard = bo.SpendGuard(self.ledger, 10 * self.bound, PRICE)
        server = Server([(200, answer("")), (200, answer("second")), (200, answer("asked afresh"))])
        try:
            with guard.scoped("run 7"):
                bo.post_chat(server.url, PAYLOAD, {}, 5, None, "OpenRouter", True, guard)
                pending = guard.take_pending()
                replayed, _ = bo.post_chat(server.url, PAYLOAD, {}, 5, None, "OpenRouter", True, guard)
                self.assertEqual((server.count, replayed["choices"][0]["message"]["content"]), (2, "second"))
                guard.take_pending()
                guard.acknowledge(pending)  # the run loop, once store_answers has committed
                fresh, first = bo.post_chat(server.url, PAYLOAD, {}, 5, None, "OpenRouter", True, guard)
        finally:
            server.close()
        self.assertEqual(len(pending), 1)
        self.assertEqual((server.count, fresh["choices"][0]["message"]["content"], first), (3, "asked afresh", None))

    def test_openrouter_chat_sends_nothing_without_a_guard(self) -> None:
        with mock.patch.dict(bo.os.environ, {"OPENROUTER_API_KEY": "test"}), \
                mock.patch.object(bo, "SPEND_GUARD", None, create=True), \
                mock.patch.object(bo, "post_json", return_value=(reply(0.0), {})) as post:
            with self.assertRaises(ValueError):
                bo.ask_openrouter_chat("m", [], 5, "high", "endpoint", False, False, None)
        post.assert_not_called()

    def test_openrouter_chat_passes_its_guard_to_every_send(self) -> None:
        guard = bo.SpendGuard(self.ledger, 1.0, PRICE)
        with mock.patch.dict(bo.os.environ, {"OPENROUTER_API_KEY": "test"}), \
                mock.patch.object(bo, "SPEND_GUARD", guard), \
                mock.patch.object(bo, "post_chat", return_value=(reply(0.0), None)) as chat, \
                mock.patch.object(bo, "read_chat_reply", return_value=([], "{}")):
            bo.ask_openrouter_chat("m", [], 5, "high", "endpoint", False, False, None)
        self.assertIs(chat.call_args.args[-1], guard)


if __name__ == "__main__":
    unittest.main()
