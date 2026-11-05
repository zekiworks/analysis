#!/usr/bin/env python3
"""Write web-grounding.json, the inputs of results.json's `web_grounding` that answers.json cannot hold.

    python3 web_grounding_inputs.py BENCHMARK_RESULTS_SQLITE PWS_FOLDER RUN... [--output web-grounding.json]

Perplexity's web grounding test (export_results.web_grounding: the runs of both hosted Decider v1.2 setups, with
grounding off and on, that its pairs hold, and WEB_GROUNDING_PILOTS): Perplexity's Decider v1.2 through its Decisions
API with grounding off and on. From the benchmark database (the runner's benchmark-results.sqlite), per run of the test
and its Text tab run: each group's input tokens (the usage in each answer's stored raw response; a run's cost by group
follows from them at its price) and, for a run with grounding on, what the search returned (each raw response's
search_results): the pages per question, the sites and the ten most returned, and three lists of question ids: the
questions with SHARED_WORDS consecutive words of the question or of one of its options (their stored texts, without the
option letters) in a returned page's title or snippet, the questions with a page from Paraf, the publisher of the bank's
source book (PUBLISHER), and those with a page of the source book itself (SOURCE_BOOK, by its title). From
PWS-Decisions' folder (Perplexity's 100 public English questions, Parallel's gated dataset: evaluation only, no
redistribution; grounding_test.py's runs and summary): aggregates only, that is each arm's counts, request times and
input tokens, what the search returned, the questions with shared words (its state with its instructions, or a choice's
description) as a count, and the paired counts of right answers. No question text, option, snippet, page address or
per-question row of PWS-Decisions is written, and none of our bank but its question ids.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.dont_write_bytecode = True  # no __pycache__ next to the published files
import export_results as er  # noqa: E402

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "web-grounding.json"
# The source check: SHARED_WORDS consecutive words (\w+ runs, case-folded) of the question (its stored text up to the
# options' heading, OPTIONS_HEADING) or of one option's text in a returned title or snippet; a page from the source
# book's publisher (its address names Paraf); a page of the source book itself, by its title (TYT IQ Türkçe Soru
# Kütüphanesi, in the address or the title as Scribd and others spell it).
OPTIONS_HEADING = re.compile(r"\n\n(?:Seçenekler|Options):\n")
SHARED_WORDS = 8
PUBLISHER = re.compile(r"paraf", re.IGNORECASE)
SOURCE_BOOK = re.compile(r"paraf\W+tyt\W+iq\W+t[uü]rk[cç]e\W+soru\W+k[uü]t[uü]phanesi", re.IGNORECASE)
TOP_DOMAINS = 10
# PWS-Decisions' run files and summary in grounding_test.py's folder, by arm.
PWS_RUNS = {"off": "runs/pws-off.jsonl", "on": "runs/pws-web_grounding.jsonl"}
PWS_SUMMARY = "runs/pws-summary.json"
PWS_ANSWERS = "data/public-100-answers.jsonl"
PWS_MANIFEST = "data/manifest.json"
PWS_QUESTIONS = "data/public-100.jsonl"


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def shares_words(asked: str, page: str) -> bool:
    """Whether SHARED_WORDS consecutive words of `asked` appear, consecutively, in `page`."""
    have = words(page)
    grams = {tuple(have[i:i + SHARED_WORDS]) for i in range(len(have) - SHARED_WORDS + 1)}
    question = words(asked)
    return any(tuple(question[i:i + SHARED_WORDS]) in grams for i in range(len(question) - SHARED_WORDS + 1))


def returned(pages: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """What the search returned over a run's questions: pages per question, the sites and the most returned ones."""
    counts = [len(found) for found in pages]
    domains = collections.Counter(urlsplit(page["url"]).hostname.removeprefix("www.") for found in pages for page in found
                                  if page.get("url"))
    return {
        # Pages returned in the run (up to five per question), the denominator of the sites' counts.
        "pages": sum(counts),
        "pages_per_question": {"mean": statistics.mean(counts), "min": min(counts), "max": max(counts),
                               "none": sum(not count for count in counts)},
        "sites": len(domains),
        # Most returned first; equal counts by name, so the list does not depend on the answers' order.
        "top_domains": sorted(domains.items(), key=lambda item: (-item[1], item[0]))[:TOP_DOMAINS],
    }


def group(category: str) -> str:
    unit = int(re.match(r"(\d+)\.", category).group(1))
    return "reading" if unit in er.READING_UNITS else "grammar"


def our_run(database: sqlite3.Connection, run: int) -> dict[str, Any]:
    mode = database.execute("SELECT perplexity_mode FROM runs WHERE id=?", (run,)).fetchone()
    if mode is None:
        raise SystemExit(f"run {run} is not in the database")
    rows = database.execute(
        "SELECT question_id, category, question, options_json, raw_response FROM answers WHERE run_id=? ORDER BY ordinal",
        (run,),
    ).fetchall()
    tokens: dict[str, int] = collections.Counter()
    questions: dict[str, int] = collections.Counter()
    pages, shared, publisher, source_book = [], [], [], []
    for question_id, category, asked, options, raw in rows:
        response = json.loads(raw)["response"]
        tokens[group(category)] += int(response["usage"]["input_tokens"])
        questions[group(category)] += 1
        found = response.get("search_results") or []
        pages.append(found)
        parts = OPTIONS_HEADING.split(asked)
        if len(parts) != 2:
            raise SystemExit(f"run {run}, question {question_id}: its stored text has no options heading")
        texts = [parts[0], *(option["text"] for option in json.loads(options))]
        if any(shares_words(text, f"{page.get('title', '')}\n{page.get('snippet', '')}") for text in texts for page in found):
            shared.append(question_id)
        if any(PUBLISHER.search(page.get("url", "")) for page in found):
            publisher.append(question_id)
        if any(SOURCE_BOOK.search(page.get("url", "")) or SOURCE_BOOK.search(page.get("title", "")) for page in found):
            source_book.append(question_id)
    entry: dict[str, Any] = {
        "run": run,
        "mode": mode[0],
        "groups": {name: {"questions": questions[name], "input_tokens": tokens[name]} for name in sorted(questions)},
    }
    if mode[0] is not None:
        entry["search"] = {
            **returned(pages),
            "shared_words": sorted(shared),
            "publisher": sorted(publisher),
            "source_book": sorted(source_book),
        }
    return entry


def nearest_rank(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def pws(folder: Path) -> dict[str, Any]:
    """PWS-Decisions' aggregates: per arm from its run file, checked against grounding_test.py's summary."""

    def rows(path: Path) -> list[dict[str, Any]]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    gold = {row["id"]: row["answer"] for row in rows(folder / PWS_ANSWERS)}
    summary = json.loads((folder / PWS_SUMMARY).read_text(encoding="utf-8"))
    manifest = json.loads((folder / PWS_MANIFEST).read_text(encoding="utf-8"))
    arms, right = {}, {}
    for arm, name in PWS_RUNS.items():
        found = rows(folder / name)
        if sorted(row["id"] for row in found) != sorted(gold):
            raise SystemExit(f"{name}: not one answer per question")
        right[arm] = {row["id"]: row["status"] == "success" and row["prediction"] == gold[row["id"]] for row in found}
        responses = [row.get("response") or {} for row in found]
        seconds = [row["latency_ms"] / 1000 for row in found]
        arms[arm] = {
            "questions": len(found),
            "correct": sum(right[arm].values()),
            "errors": sum(not response for response in responses),
            "median_request_seconds": statistics.median(seconds),
            "p95_request_seconds": nearest_rank(seconds, 0.95),
            "input_tokens": sum(int((response.get("usage") or {}).get("input_tokens") or 0) for response in responses),
        }
        if arm == "on":
            pages = [response.get("search_results") or [] for response in responses]
            questions = {row["id"]: row for row in rows(folder / PWS_QUESTIONS)}

            def texts(question: dict[str, Any]) -> list[str]:
                """A PWS-Decisions question's texts: its state with its instructions, and each choice's description."""
                return [json.dumps(question["state"], ensure_ascii=False) + " " + question["instructions"],
                        *(choice["description"] for choice in question["choices"])]

            arms[arm]["search"] = {
                **returned(pages),
                "shared_words": sum(
                    any(shares_words(text, f"{page.get('title', '')}\n{page.get('snippet', '')}")
                        for text in texts(questions[row["id"]]) for page in found_pages)
                    for row, found_pages in zip(found, pages)
                ),
            }
        published = summary[name]
        for key, value in (("questions", "questions"), ("correct", "correct"), ("errors", "errors"), ("input_tokens", "input_tokens")):
            if published[value] != arms[arm][key]:
                raise SystemExit(f"{name}: {key} {arms[arm][key]} differs from the summary's {published[value]}")
    ids = sorted(gold)
    return {
        "name": "PWS-Decisions",
        "version": manifest["version"],
        "questions_sha256": manifest["questions_sha256"],
        "language": "English",
        "off": arms["off"],
        "on": arms["on"],
        # Right answers off only and on only, over the same questions (for the exact McNemar test).
        "off_only": sum(right["off"][item] and not right["on"][item] for item in ids),
        "on_only": sum(right["on"][item] and not right["off"][item] for item in ids),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("database", type=Path, help="the runner's benchmark-results.sqlite")
    parser.add_argument("pws", type=Path, help="grounding_test.py's folder (PWS-Decisions' runs, summary and answers)")
    parser.add_argument("runs", type=int, nargs="+", help="the test's runs (every run of its pairs, the pilots included)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"default: {DEFAULT_OUTPUT}")
    args = parser.parse_args()
    database = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    runs = sorted(set(args.runs) | er.WEB_GROUNDING_ONLY)
    document = {
        "rules": {"shared_words": SHARED_WORDS, "publisher": PUBLISHER.pattern, "source_book": SOURCE_BOOK.pattern},
        "runs": [our_run(database, run) for run in runs],
        "pws": pws(args.pws),
    }
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {len(document['runs'])} runs and PWS-Decisions' aggregates to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
