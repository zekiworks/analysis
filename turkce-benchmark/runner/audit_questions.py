#!/usr/bin/env python3
"""Flag benchmark questions whose extracted text lost its markup, and keys the strongest runs dispute.

Step 1.2 of turkce-benchmark-plan.md. Writes one CSV row per benchmark question. A question is a
re-transcription candidate when it refers to underlined words but carries no <u> marking, refers to
numbered words without an inline number, or has a Roman numeral stuck to a word. "word- word"
patterns are listed for a manual look only: most are deliberate dashes in punctuation questions.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import benchmark_ollama as bo

HERE = Path(__file__).resolve().parent
NUMERAL_IN_WORD = re.compile(r"[a-zçğıöşü](?:I|II|III|IV|V)\b")
HYPHEN_SPACE = re.compile(r"[a-zçğıöşü]- [a-zçğıöşü]")
# Runs whose agreement on a non-key option marks the key as suspect: (provider, model, thinking).
REFERENCE_RUNS = {
    "GPT-6 Astra (low)": ("openai", "gpt-6-astra", "low"),
    "Opus 5.5 (low)": ("claude", "claude-opus-5-5", "low"),
    "Sonnet 5.5 (high)": ("claude", "claude-sonnet-5-5", "high"),
}
FLAGS = ("underline_missing", "numbering_missing", "numeral_in_word", "hyphen_space", "suspect_key")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=HERE / "questions.sqlite", help="question bank to audit")
    parser.add_argument("--results", type=Path, default=HERE / "benchmark-results.sqlite", help="benchmark results")
    parser.add_argument(
        "--reference-data",
        type=Path,
        default=HERE / "questions.sqlite",
        help="question bank the reference runs answered (default: questions.sqlite)",
    )
    parser.add_argument("--output", type=Path, default=HERE / "repair" / "flags.csv", help="CSV to write")
    return parser.parse_args()


def shares_questions(data: Path, reference_data: Path) -> bool:
    """Whether `data` is the reference question bank or a copy made from it, so its question IDs match."""
    reference_hash = bo.file_sha256(reference_data)
    if bo.file_sha256(data) == reference_hash:
        return True
    connection = sqlite3.connect(f"file:{data}?mode=ro", uri=True)
    try:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dataset_info'").fetchone():
            return False
        derived = connection.execute("SELECT value FROM dataset_info WHERE key='derived_from_sha256'").fetchone()
        return derived is not None and derived[0] == reference_hash
    finally:
        connection.close()


def reference_answers(results: Path, reference_data: Path) -> dict[str, dict[int, tuple[str | None, float | None]]]:
    """Answer and confidence per question for each reference run over the full reference question bank."""
    dataset_hash = bo.file_sha256(reference_data)
    connection = sqlite3.connect(f"file:{results}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        answers: dict[str, dict[int, tuple[str | None, float | None]]] = {}
        for name, (provider, model, thinking) in REFERENCE_RUNS.items():
            run = connection.execute(
                """
                SELECT id FROM runs
                WHERE provider=? AND model=? AND thinking_mode=? AND dataset_sha256=? AND status='completed'
                ORDER BY evaluated_total DESC, id DESC LIMIT 1
                """,
                (provider, model, thinking, dataset_hash),
            ).fetchone()
            if run is None:
                raise ValueError(f"no completed {name} run on {reference_data.name}")
            answers[name] = {
                int(row["question_id"]): (
                    row["predicted_answer"],
                    bo.answer_usage(provider, int(row["question_id"]), row["raw_response"])[1],
                )
                for row in connection.execute(
                    "SELECT question_id, predicted_answer, raw_response FROM answers WHERE run_id=?",
                    (run["id"],),
                )
            }
        return answers
    finally:
        connection.close()


def question_texts(data: Path, question_ids: list[int]) -> dict[int, sqlite3.Row]:
    connection = sqlite3.connect(f"file:{data}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            f"""
            SELECT question_id, unit_number, unit_title, question_number, source_page_start, answer,
                   passage_text, passage_markdown, question, choices_json
            FROM benchmark_questions WHERE question_id IN ({",".join("?" * len(question_ids))})
            """,
            question_ids,
        ).fetchall()
        return {int(row["question_id"]): row for row in rows}
    finally:
        connection.close()


def audit(data: Path, results: Path, reference_data: Path) -> list[dict[str, Any]]:
    """One row of flags per benchmark question in `data`, whatever its review status.

    Keys are checked against the reference runs only when `data` shares the reference bank's question IDs.
    """
    selection = bo.load_questions(data, None, None, None, 0, include_excluded=True)
    question_ids = [question.question_id for question in selection.questions]
    texts = question_texts(data, question_ids)
    reference = reference_answers(results, reference_data) if shares_questions(data, reference_data) else {}
    rows = []
    for question in selection.questions:
        question_id = question.question_id
        row = texts[question_id]
        choices = json.loads(row["choices_json"] or "[]")
        choice_texts = [str(choice.get("text") or "").strip() for choice in choices]
        full = "\n".join([str(row["passage_text"] or ""), str(row["passage_markdown"] or ""), str(row["question"] or ""), *choice_texts])
        underline_missing, numbering_missing = bo.missing_markup(question.prompt, [option.text for option in question.options])
        picks = [reference.get(name, {}).get(question_id, (None, None))[0] for name in REFERENCE_RUNS]
        flags = {
            "underline_missing": underline_missing,
            "numbering_missing": numbering_missing,
            "numeral_in_word": bool(NUMERAL_IN_WORD.search(full)),
            "hyphen_space": bool(HYPHEN_SPACE.search(full)),
            "suspect_key": picks[0] is not None and len(set(picks)) == 1 and picks[0] != row["answer"],
        }
        rows.append(
            {
                "question_id": question_id,
                "unit": f"{row['unit_number']}. {row['unit_title']}" if row["unit_number"] else row["unit_title"],
                "page": int(row["source_page_start"]),
                "printed_number": row["question_number"],
                "key": row["answer"],
                **{flag: int(value) for flag, value in flags.items()},
                "candidate": int(flags["underline_missing"] or flags["numbering_missing"] or flags["numeral_in_word"]),
                "reference_answers": "/".join(pick or "-" for pick in picks),
            }
        )
    return rows


def main() -> int:
    args = parse_args()
    try:
        rows = audit(args.data.resolve(), args.results.resolve(), args.reference_data.resolve())
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    counts = Counter(flag for row in rows for flag in FLAGS if row[flag])
    flagged = sum(row["underline_missing"] or row["numbering_missing"] for row in rows)
    candidates = sum(row["candidate"] for row in rows)
    unflagged_suspects = sum(row["suspect_key"] and not row["candidate"] for row in rows)
    print(f"{len(rows)} questions in {args.data.name}")
    for flag in FLAGS:
        print(f"  {flag}: {counts[flag]}")
    print(f"  underline or numbering missing: {flagged}")
    print(f"  re-transcription candidates: {candidates}")
    print(f"  suspect keys not among the candidates: {unflagged_suspects}")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
