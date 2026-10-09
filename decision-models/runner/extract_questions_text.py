#!/usr/bin/env python3
"""Text-first PDF question extractor with selective question-crop vision fallback."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import extract_questions as core
import vision_ocr

LOG = logging.getLogger("question_extractor_text")

QUESTION_NUMBER = re.compile(r"^(\d{1,3})\.$")
RANGE_QUESTION_CUE = re.compile(
    r"\b(\d{1,3})\.?\s*[-–]\s*(\d{1,3})\.?\s+sorular", re.IGNORECASE
)
VISUAL_CUES = re.compile(
    r"\b(?:altı çizili|numaralanmış\s+(?:söz\w*|sözcük\w*|ifade\w*)|"
    r"şekil|görsel|grafik|tablo|harita|resim|karikatür|diyagram|"
    r"aşağıdaki model|yukarıdaki model|anlam\s+kullanım)\b",
    re.IGNORECASE,
)

TEXT_SYSTEM_PROMPT = r"""
You structure positioned Turkish question-bank text into JSON for an LLM benchmark. The PDF text
layer is the transcription authority. Never solve questions. Preserve Turkish spelling,
punctuation, formulas, Roman numerals, parenthetical explanations, and choice order.

Input contains deterministic question candidates with normalized bounding boxes. Column order and
question boundaries are already resolved. Join words split only by visual line wrapping, including
end-of-line hyphenation. Do not merge separate questions. A candidate can start or end with a
continuation fragment; use the carried context when available.

Tables are represented through positioned lines. Preserve a table as Markdown inside the question
stem when row/column relationships matter. If underlining, a diagram, a table, or other formatting
cannot be recovered confidently from text, list the question in `vision_review`; do not guess.

Copyright pages, prefaces, tables of contents, indexes, publisher marks, page numbers, and answer
strip decorations are not questions. `section_events` must be emitted when the detected page header
differs from the carried current section.
`page_types` contains only types that actually apply. Never copy every allowed value from the
schema example. A page with deterministic question candidates is not `front_matter`.

Return exactly one JSON object with this shape:
{
  "page_number": 1,
  "page_types": ["questions"],
  "section_events": [{
    "local_ref": "section_1", "unit_number": "1", "unit_title": "...",
    "title": "...", "subsection": null, "test_type": "KAVRAYALIM",
    "test_number": "1"
  }],
  "passages": [{
    "local_ref": "passage_1", "section_ref": "current", "text": "...",
    "markdown": null, "description": null, "visual_refs": [], "bbox": null
  }],
  "visuals": [],
  "questions": [{
    "section_ref": "current", "number": "1", "stem": "...",
    "question_type": "multiple_choice", "passage_ref": null, "visual_refs": [],
    "choices": [{"label": "A", "text": "...", "visual_refs": [], "bbox": null}],
    "complete": true, "continuation": false,
    "bbox": [0.0, 0.0, 1.0, 1.0], "confidence": 0.99
  }],
  "answers": [],
  "vision_review": [{"question_number": "1", "reason": "underlining is meaningful"}],
  "warnings": []
}

Use the exact candidate bbox for each question. Use empty arrays and null optional values. Do not
invent visual objects from textual references alone; request vision review instead.
""".strip()

QUESTION_TEXT_SYSTEM_PROMPT = r"""
You convert exactly one positioned Turkish multiple-choice question candidate into structured JSON.
Never solve it. Preserve every sentence, Turkish character, parenthetical explanation, Roman
numeral, and answer choice. Join words split only by line wrapping. Return all printed choices in
order; this book normally has A through E.

Text may contain a shared passage or instruction applying to a numbered range. Put shared content
in `passage`; keep the question-specific prompt in `question.stem`. If meaningful underlining,
table alignment, a diagram, or visual choices cannot be represented confidently from positioned
text, request `vision_review` rather than guessing.

Return exactly:
{
  "question": {
    "number": "1", "stem": "complete question-specific text",
    "question_type": "multiple_choice", "passage_ref": null, "visual_refs": [],
    "choices": [
      {"label": "A", "text": "complete choice", "visual_refs": [], "bbox": null}
    ],
    "complete": true, "continuation": false, "bbox": [0,0,1,1], "confidence": 0.99
  },
  "passage": null,
  "vision_review": [],
  "warnings": []
}

Do not emit page metadata, section events, answers, other questions, or prose outside the JSON.
""".strip()

VISION_SYSTEM_PROMPT = r"""
You verify only the supplied cropped Turkish multiple-choice questions. Never solve them. Compare
the crop with the text-first JSON and correct transcription, underlining-dependent meaning, Roman
numerals, tables, diagrams, and visual choices. Ignore red answer-strip smudges and publisher art.

Return exactly one JSON object:
{
  "question_updates": [{
    "number": "1", "stem": "complete corrected stem", "choices": [
      {"label": "A", "text": "choice or null", "visual_refs": [], "bbox": null}
    ], "visual_refs": [], "complete": true, "confidence": 0.99
  }],
  "visuals": [{
    "local_ref": "visual_1", "question_number": "1", "kind": "diagram",
    "description": "literal neutral description", "markdown": null, "dot": null,
    "bbox": null
  }],
  "warnings": []
}
Do not change questions that were not supplied. Do not infer unmarked relationships.
""".strip()


@dataclass(frozen=True)
class Word:
    text: str
    left: float
    top: float
    width: float
    height: float
    par: int
    block: int
    line: int
    word: int

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height


@dataclass(frozen=True)
class PositionedLine:
    text: str
    left: float
    top: float
    right: float
    bottom: float

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2


@dataclass(frozen=True)
class QuestionCandidate:
    number: str
    bbox: tuple[float, float, float, float]
    lines: tuple[PositionedLine, ...]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


@dataclass(frozen=True)
class PositionedPage:
    width: float
    height: float
    words: tuple[Word, ...]
    lines: tuple[PositionedLine, ...]
    candidates: tuple[QuestionCandidate, ...]
    answer_key_top: float | None


def run_tsv_extraction(pdf_path: Path, page_number: int) -> str:
    command = [
        core.require_binary("pdftotext"),
        "-f",
        str(page_number),
        "-l",
        str(page_number),
        "-cropbox",
        "-tsv",
        str(pdf_path),
        "-",
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    diagnostics = result.stderr.strip()
    if diagnostics:
        LOG.debug(
            "pdftotext TSV page %d diagnostics: %s",
            page_number,
            diagnostics.replace("\n", " | "),
        )
    if not result.stdout.strip():
        raise RuntimeError(
            f"No positioned text extracted for page {page_number}; Poppler exit {result.returncode}"
        )
    return result.stdout


def parse_positioned_page(tsv_text: str) -> PositionedPage:
    rows = list(csv.DictReader(tsv_text.splitlines(), delimiter="\t"))
    page_row = next((row for row in rows if row.get("text") == "###PAGE###"), None)
    if page_row is None:
        raise ValueError("TSV has no page geometry row")
    width = float(page_row["width"])
    height = float(page_row["height"])
    words: list[Word] = []
    for row in rows:
        if row.get("level") != "5" or not row.get("text"):
            continue
        words.append(
            Word(
                text=row["text"],
                left=float(row["left"]),
                top=float(row["top"]),
                width=float(row["width"]),
                height=float(row["height"]),
                par=int(row["par_num"]),
                block=int(row["block_num"]),
                line=int(row["line_num"]),
                word=int(row["word_num"]),
            )
        )

    grouped: dict[tuple[int, int, int], list[Word]] = {}
    for word in words:
        grouped.setdefault((word.par, word.block, word.line), []).append(word)
    lines: list[PositionedLine] = []
    for line_words in grouped.values():
        ordered = sorted(line_words, key=lambda item: (item.left, item.word))
        lines.append(
            PositionedLine(
                text=" ".join(item.text for item in ordered),
                left=min(item.left for item in ordered),
                top=min(item.top for item in ordered),
                right=max(item.right for item in ordered),
                bottom=max(item.bottom for item in ordered),
            )
        )
    lines.sort(key=lambda item: (item.top, item.left))

    horizontal_words: dict[float, list[Word]] = {}
    for word in words:
        horizontal_words.setdefault(round(word.top, 1), []).append(word)
    answer_tops = []
    for top, row_words in horizontal_words.items():
        row_text = " ".join(
            word.text for word in sorted(row_words, key=lambda item: item.left)
        )
        if len(core.ANSWER_KEY_PAIR.findall(row_text.upper())) >= 3:
            answer_tops.append(top)
    answer_key_top = min(answer_tops) if answer_tops else None
    content_bottom = min(answer_key_top or height * 0.95, height * 0.95)

    range_header_rows = {
        (
            0 if line.left < width / 2 else 1,
            round(line.top, 1),
        )
        for line in lines
        if RANGE_QUESTION_CUE.search(line.text)
    }
    anchors: list[tuple[str, int, float]] = []
    weak_anchors: set[tuple[str, int, float]] = set()
    strong_anchors: set[tuple[str, int, float]] = set()
    for word in words:
        exact_match = QUESTION_NUMBER.fullmatch(word.text)
        line_match = re.match(r"^(\d{1,3})\.\s+\S", word.text)
        match = exact_match or line_match
        if not match or word.top < height * 0.07 or word.top >= content_bottom:
            continue
        same_line_words = grouped[(word.par, word.block, word.line)]
        if any(
            other.word < word.word and other.text.strip()
            for other in same_line_words
        ):
            continue
        following_words = sorted(
            (
                other
                for other in same_line_words
                if other.word > word.word and other.text.strip()
            ),
            key=lambda other: other.word,
        )
        first_following = (
            following_words[0].text.lstrip("\"'“”‘’([{")
            if following_words
            else ""
        )
        weak_anchor = bool(
            first_following
            and first_following[0].isalpha()
            and first_following[0].islower()
        )
        column = 0 if word.left < width * 0.45 else 1
        if (column, round(word.top, 1)) in range_header_rows:
            continue
        column_left = 0.0 if column == 0 else width / 2
        if word.left - column_left > width * 0.10:
            continue
        anchor = (match.group(1), column, word.top)
        anchors.append(anchor)
        if weak_anchor:
            weak_anchors.add(anchor)
        if line_match or (exact_match and following_words):
            strong_anchors.add(anchor)
    unique_numbers = sorted({int(number) for number, _, _ in anchors})
    runs: list[list[int]] = []
    for number in unique_numbers:
        if runs and number == runs[-1][-1] + 1:
            runs[-1].append(number)
        else:
            runs.append([number])
    if len(strong_anchors) >= 2:
        supplemental = [
            anchor
            for anchor in anchors
            if anchor not in strong_anchors
            and not any(
                strong[1] == anchor[1]
                and abs(strong[2] - anchor[2]) < height * 0.015
                for strong in strong_anchors
            )
        ]
        anchors = list(strong_anchors) + supplemental
    elif runs:
        longest_run = max(runs, key=lambda run: (len(run), -run[0]))
        if len(longest_run) >= 2:
            allowed_numbers = {str(number) for number in longest_run}
            anchors = [
                anchor for anchor in anchors if anchor[0] in allowed_numbers
            ]
    duplicate_numbers = {
        number
        for number, _, _ in anchors
        if sum(anchor[0] == number for anchor in anchors) > 1
    }
    anchors = [
        anchor
        for anchor in anchors
        if anchor[0] not in duplicate_numbers
        or anchor not in weak_anchors
        or not any(
            other[0] == anchor[0] and other not in weak_anchors
            for other in anchors
        )
    ]

    deduplicated: list[tuple[str, int, float]] = []
    for anchor in sorted(anchors, key=lambda item: (item[1], item[2])):
        number, column, top = anchor
        conflict_index = next(
            (
                index
                for index, (_, existing_column, existing_top) in enumerate(deduplicated)
                if existing_column == column
                and abs(existing_top - top) < height * 0.015
            ),
            None,
        )
        if conflict_index is None:
            deduplicated.append(anchor)
        elif (
            anchor in strong_anchors
            and deduplicated[conflict_index] not in strong_anchors
        ):
            deduplicated[conflict_index] = anchor

    candidates: list[QuestionCandidate] = []
    for index, (number, column, top) in enumerate(deduplicated):
        later = [
            other_top
            for _, other_column, other_top in deduplicated[index + 1 :]
            if other_column == column and other_top > top
        ]
        bottom = (
            min(later) - max(1.0, height * 0.01)
            if later
            else content_bottom
        )
        left = 0.0 if column == 0 else width / 2
        right = width / 2 if column == 0 else width
        selected = tuple(
            line
            for line in lines
            if top - 2.0 <= line.top < bottom
            and left <= line.center_x < right
        )
        candidates.append(
            QuestionCandidate(
                number=number,
                bbox=(left / width, max(0.0, top - 2.0) / height, right / width, bottom / height),
                lines=selected,
            )
        )
    candidates.sort(key=lambda item: (item.bbox[1], item.bbox[0]))
    return PositionedPage(
        width=width,
        height=height,
        words=tuple(words),
        lines=tuple(lines),
        candidates=tuple(candidates),
        answer_key_top=answer_key_top,
    )


def format_positioned_page(
    page: PositionedPage,
    page_number: int,
    plain_text: str,
    context: dict[str, Any],
) -> str:
    blocks: list[str] = []
    for candidate in page.candidates:
        bbox = [round(value, 5) for value in candidate.bbox]
        blocks.append(
            f'<question_candidate number="{candidate.number}" bbox="{json.dumps(bbox)}">\n'
            f"{candidate.text}\n</question_candidate>"
        )
    candidate_ranges = [(item.bbox[1] * page.height, item.bbox[3] * page.height) for item in page.candidates]
    unassigned = [
        line
        for line in page.lines
        if line.top < page.height * 0.12
        or not any(start <= line.top < end for start, end in candidate_ranges)
    ]
    unassigned_text = "\n".join(
        f"[{line.left:.1f},{line.top:.1f}] {line.text}" for line in unassigned
    )
    return (
        f"Structure PDF page {page_number}.\n"
        f"Page geometry: width={page.width:.2f}, height={page.height:.2f}.\n"
        "Deterministic header and carried state:\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
        + "\nUnassigned header, continuation, footer, and answer-key lines:\n"
        + unassigned_text
        + "\nQuestion candidates:\n"
        + "\n\n".join(blocks)
        + "\nPlain text fallback:\n<plain_text>\n"
        + plain_text
        + "\n</plain_text>"
    )


def candidate_map(page: PositionedPage) -> dict[str, QuestionCandidate]:
    return {candidate.number: candidate for candidate in page.candidates}

def detect_chapter_header(plain_text: str) -> dict[str, str] | None:
    first_question = re.search(r"(?m)^\s*\d{1,3}\.\s+\S", plain_text)
    header_text = plain_text[: first_question.start()] if first_question else plain_text
    lines = [" ".join(line.split()) for line in header_text.splitlines()]
    if not any("BÖLÜM" in line.upper() for line in lines):
        return None
    detected = core.detect_page_section_header(plain_text)
    unit_number: str | None = None
    unit_titles: list[str] = []
    for line in lines:
        upper = line.upper()
        if not line or line.startswith("@") or "BÖLÜM" in upper:
            continue
        if unit_number is None and "TEST" in upper:
            number_match = re.match(r"^(\d{1,3})\b", line)
            if number_match:
                unit_number = number_match.group(1)
        if (
            line.isupper()
            and any(character.isalpha() for character in line)
            and "TEST" not in upper
            and upper not in core.TEST_TYPE_NAMES
            and "PARAF YAYINLARI" not in upper
        ):
            unit_titles.append(line)
    unit_title = max(unit_titles, key=len) if unit_titles else None
    title = detected.get("title") or unit_title
    return {
        key: value
        for key, value in {
            "unit_number": unit_number,
            "unit_title": unit_title,
            "title": title,
            "test_type": detected.get("test_type"),
            "test_number": detected.get("test_number"),
        }.items()
        if value
    }


def turkish_fold(value: str) -> str:
    return value.translate(str.maketrans({"I": "ı", "İ": "i"})).casefold()


def stabilize_detected_header(
    plain_text: str, context: dict[str, Any]
) -> dict[str, str]:
    detected = detect_chapter_header(plain_text) or core.detect_page_section_header(
        plain_text
    )
    current = context.get("current_section")
    if not detected or not isinstance(current, dict):
        return detected
    current_title = str(current.get("title") or "").strip()
    current_test = str(current.get("test_number") or "").strip()
    detected_test = str(detected.get("test_number") or "").strip()
    top_text = turkish_fold(" ".join(plain_text.splitlines()[:12]))
    if (
        current_title
        and not current_title.lower().startswith("unknown")
        and turkish_fold(current_title) in top_text
        and current_test
        and current_test == detected_test
    ):
        return {
            key: str(current[key])
            for key in (
                "unit_number",
                "unit_title",
                "title",
                "subsection",
                "test_type",
                "test_number",
            )
            if current.get(key) is not None
        }
    return detected


def detect_pegem_header(
    page: PositionedPage,
    page_number: int,
    context: dict[str, Any],
) -> dict[str, str]:
    test_number = ""
    for line in page.lines:
        match = re.search(r"\bTEST\s*[-–]\s*(\d{1,3})\b", line.text, re.IGNORECASE)
        if match:
            test_number = match.group(1)
            break
    if not test_number:
        current = context.get("current_section")
        return dict(current) if isinstance(current, dict) else {}

    title_candidates = [
        line.text.strip()
        for line in page.lines
        if line.top < page.height * 0.09
        and not re.search(r"\b(?:PEGEM|AKADEMİ|ALES|TEST)\b", line.text, re.IGNORECASE)
        and not re.fullmatch(r"\d+", line.text.strip())
    ]
    title = title_candidates[0] if title_candidates else "Bilinmeyen Konu"
    import extract_pegem as pegem

    return {
        **pegem.section_metadata(pegem.page_scope(page_number)),
        "title": title,
        "test_number": test_number,
    }


def repair_continuation_numbers(
    page: PositionedPage, context: dict[str, Any]
) -> PositionedPage:
    current = context.get("current_section")
    detected = context.get("detected_page_header")
    if not isinstance(current, dict) or not isinstance(detected, dict):
        return page
    if not core.header_matches_section(detected, current):
        return page
    existing = {
        int(value)
        for value in context.get("unanswered_question_numbers", [])
        if str(value).isdigit()
    }
    if context.get("incomplete_questions") or not existing:
        return page
    last_existing = max(existing)
    ordered = sorted(
        page.candidates,
        key=lambda candidate: (candidate.bbox[0], candidate.bbox[1]),
    )
    original_ordered = ordered
    observed = [
        int(candidate.number) if candidate.number.isdigit() else -1
        for candidate in ordered
    ]
    contiguous: set[int] = set()
    next_number = last_existing + 1
    while next_number in observed:
        contiguous.add(next_number)
        next_number += 1
    dropped = False
    if len(contiguous) >= 2 and len(contiguous) >= len(ordered) - 1:
        kept_ids = {
            id(candidate)
            for candidate in ordered
            if candidate.number.isdigit() and int(candidate.number) in contiguous
        }
        rebuilt: list[QuestionCandidate] = []
        for candidate in original_ordered:
            if id(candidate) in kept_ids:
                rebuilt.append(candidate)
                continue
            previous_index = next(
                (
                    index
                    for index in range(len(rebuilt) - 1, -1, -1)
                    if rebuilt[index].bbox[0] == candidate.bbox[0]
                ),
                None,
            )
            if previous_index is not None:
                previous = rebuilt[previous_index]
                merged_lines = previous.lines + tuple(
                    line
                    for line in candidate.lines
                    if line.text.strip() != f"{candidate.number}."
                )
                rebuilt[previous_index] = replace(
                    previous,
                    lines=tuple(
                        sorted(merged_lines, key=lambda line: (line.top, line.left))
                    ),
                    bbox=(
                        previous.bbox[0],
                        previous.bbox[1],
                        previous.bbox[2],
                        max(previous.bbox[3], candidate.bbox[3]),
                    ),
                )
        ordered = rebuilt
        observed = [int(candidate.number) for candidate in ordered]
        dropped = len(ordered) != len(page.candidates)
    expected = list(range(last_existing + 1, last_existing + len(ordered) + 1))
    matching = sum(actual == wanted for actual, wanted in zip(observed, expected))
    if matching < max(1, len(ordered) // 2):
        return page
    if not dropped and observed == expected:
        return page
    return replace(
        page,
        candidates=tuple(
            replace(candidate, number=str(number))
            for candidate, number in zip(ordered, expected)
        ),
    )


def previous_active_section(
    connection: sqlite3.Connection, source_id: int, page_number: int
) -> int | None:
    row = connection.execute(
        """
        SELECT active_section_after_id
        FROM pages
        WHERE source_id=? AND page_number<?
          AND status IN ('complete', 'incomplete')
          AND active_section_after_id IS NOT NULL
        ORDER BY page_number DESC
        LIMIT 1
        """,
        (source_id, page_number),
    ).fetchone()
    return int(row["active_section_after_id"]) if row else None


def relink_answer_observations(
    connection: sqlite3.Connection, source_id: int
) -> int:
    connection.execute(
        """
        UPDATE answer_observations AS observation
        SET question_id = (
            SELECT question.id
            FROM questions AS question
            WHERE question.source_id = observation.source_id
              AND question.section_id = observation.section_id
              AND question.printed_number = observation.printed_number
        )
        WHERE observation.source_id = ?
          AND observation.question_id IS NULL
          AND EXISTS (
            SELECT 1
            FROM questions AS question
            WHERE question.source_id = observation.source_id
              AND question.section_id = observation.section_id
              AND question.printed_number = observation.printed_number
          )
        """,
        (source_id,),
    )
    question_rows = connection.execute(
        """
        SELECT DISTINCT question_id
        FROM answer_observations
        WHERE source_id=? AND question_id IS NOT NULL
        """,
        (source_id,),
    ).fetchall()
    for row in question_rows:
        core.recompute_question_answer(connection, int(row["question_id"]))
    return len(question_rows)


def normalize_wrapped_text(parts: list[str]) -> str:
    text = "\n".join(part.strip() for part in parts if part.strip())
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def deterministic_positioned_question(
    candidate: QuestionCandidate,
) -> dict[str, Any] | None:
    line_height = max(
        (line.bottom - line.top for line in candidate.lines),
        default=4.0,
    )
    tolerance = max(3.0, line_height)
    anchors: dict[str, tuple[PositionedLine, str]] = {}
    for line in candidate.lines:
        match = re.match(r"^\s*([A-Ea-e])\)\s*(.*)$", line.text.strip())
        if not match:
            continue
        label = match.group(1).upper()
        text = match.group(2).strip()
        if label in anchors:
            prior_line, prior_text = anchors[label]
            if (
                abs(prior_line.top - line.top) > tolerance * 1.5
                or abs(prior_line.left - line.left) > tolerance * 3
            ):
                return None
            if len(text) > len(prior_text):
                anchors[label] = (line, text)
            continue
        anchors[label] = (line, text)
    if set(anchors) != set("ABCDE"):
        return None

    first_choice_top = min(line.top for line, _ in anchors.values())
    stem_parts: list[str] = []
    for line in candidate.lines:
        if line.top >= first_choice_top - tolerance:
            continue
        text = line.text.strip()
        if not text or text == "PARAF YAYINLARI":
            continue
        text = re.sub(rf"^{re.escape(candidate.number)}\.\s*", "", text)
        if text:
            stem_parts.append(text)
    stem = normalize_wrapped_text(stem_parts)
    if len(stem) < 10:
        return None

    choice_parts = {label: [text] if text else [] for label, (_, text) in anchors.items()}
    anchor_line_ids = {id(line) for line, _ in anchors.values()}
    for line in sorted(candidate.lines, key=lambda item: (item.top, item.left)):
        if id(line) in anchor_line_ids or line.top < first_choice_top - tolerance:
            continue
        text = line.text.strip()
        if (
            not text
            or re.match(r"^\d{1,3}\.\s*", text)
            or re.match(r"^[A-Ea-e]\)\s*", text)
        ):
            continue
        eligible = [
            (label, anchor)
            for label, (anchor, _) in anchors.items()
            if anchor.top <= line.top + tolerance
        ]
        if not eligible:
            continue
        latest_top = max(anchor.top for _, anchor in eligible)
        same_row = [
            (label, anchor)
            for label, anchor in eligible
            if abs(anchor.top - latest_top) <= tolerance
        ]
        preceding = [
            (label, anchor)
            for label, anchor in same_row
            if anchor.left <= line.left + tolerance
        ]
        label, _ = max(
            preceding or same_row,
            key=lambda item: item[1].left if preceding else -abs(item[1].left - line.left),
        )
        choice_parts[label].append(text)

    choices: list[dict[str, Any]] = []
    for label in "ABCDE":
        text = normalize_wrapped_text(choice_parts[label])
        if re.fullmatch(r"[Ilıİ|!]+", text):
            text = re.sub(r"[Ilıİ|!]", "I", text)
        if not text:
            return None
        choices.append(
            {
                "label": label,
                "text": text,
                "visual_refs": [],
                "bbox": None,
            }
        )
    return {
        "section_ref": "current",
        "number": candidate.number,
        "stem": stem,
        "question_type": "multiple_choice",
        "passage_ref": None,
        "visual_refs": [],
        "choices": choices,
        "complete": True,
        "continuation": False,
        "bbox": list(candidate.bbox),
        "confidence": 0.96,
    }


def deterministic_question(candidate: QuestionCandidate) -> dict[str, Any] | None:
    if RANGE_QUESTION_CUE.search(candidate.text):
        return None
    kept_lines: list[str] = []
    for raw_line in candidate.text.splitlines():
        line = raw_line.strip()
        if not line or line == f"{candidate.number}." or line == "PARAF YAYINLARI":
            continue
        line = re.sub(rf"^{re.escape(candidate.number)}\.\s*", "", line)
        if line:
            kept_lines.append(line)
    joined = "\n".join(kept_lines)
    joined = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", joined)
    joined = re.sub(r"\s*\n\s*", " ", joined)
    joined = re.sub(r"\s+", " ", joined).strip()
    matches = list(re.finditer(r"(?:^|\s)([A-E])\)\s*", joined))
    if [match.group(1) for match in matches] != list("ABCDE"):
        return deterministic_positioned_question(candidate)
    stem = joined[: matches[0].start()].strip()
    if len(stem) < 10:
        return None
    choices: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(joined)
        text = joined[match.end() : end].strip()
        if not text:
            return None
        choices.append(
            {
                "label": match.group(1),
                "text": text,
                "visual_refs": [],
                "bbox": None,
            }
        )
    return {
        "section_ref": "current",
        "number": candidate.number,
        "stem": stem,
        "question_type": "multiple_choice",
        "passage_ref": None,
        "visual_refs": [],
        "choices": choices,
        "complete": True,
        "continuation": False,
        "bbox": list(candidate.bbox),
        "confidence": 0.98,
    }


def deterministic_range_passages(
    page: PositionedPage,
) -> list[tuple[dict[str, Any], set[str]]]:
    passages: list[tuple[dict[str, Any], set[str]]] = []
    for index, header in enumerate(
        line for line in page.lines if RANGE_QUESTION_CUE.search(line.text)
    ):
        match = RANGE_QUESTION_CUE.search(header.text)
        assert match is not None
        first_number = int(match.group(1))
        last_number = int(match.group(2))
        column = 0 if header.center_x < page.width / 2 else 1
        column_left = 0.0 if column == 0 else page.width / 2
        column_right = page.width / 2 if column == 0 else page.width
        next_question_tops = [
            candidate.bbox[1] * page.height
            for candidate in page.candidates
            if candidate.bbox[0] < (0.5 if column == 0 else 1.0)
            and candidate.bbox[2] > (0.0 if column == 0 else 0.5)
            and candidate.bbox[1] * page.height > header.top
            and first_number <= int(candidate.number) <= last_number
        ]
        if not next_question_tops:
            continue
        passage_bottom = min(next_question_tops)
        body_lines = [
            line
            for line in page.lines
            if header.bottom <= line.top < passage_bottom - 1.0
            and column_left <= line.center_x < column_right
            and line.text.strip() != "PARAF YAYINLARI"
        ]
        if not body_lines:
            continue
        text = "\n".join(line.text.strip() for line in body_lines if line.text.strip())
        text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)


        text = re.sub(r"\s*\n\s*", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        local_ref = f"passage_{first_number}_{last_number}_{index + 1}"
        bbox = [
            column_left / page.width,
            header.top / page.height,
            column_right / page.width,
            passage_bottom / page.height,
        ]
        passages.append(
            (
                {
                    "local_ref": local_ref,
                    "section_ref": "current",
                    "text": text,
                    "markdown": None,
                    "description": None,
                    "visual_refs": [],
                    "bbox": bbox,
                },
                {str(number) for number in range(first_number, last_number + 1)},
            )
        )
    return passages
def detect_continuation_candidate(
    page: PositionedPage, context: dict[str, Any]
) -> QuestionCandidate | None:
    incomplete = context.get("incomplete_questions") or []
    eligible: dict[str, Any] | None = None
    for item in reversed(incomplete):
        if not isinstance(item, dict):
            continue
        try:
            raw = json.loads(str(item.get("raw_json") or "{}"))
        except json.JSONDecodeError:
            raw = {}
        if len(raw.get("choices") or []) < 5:
            eligible = item
            break
    if eligible is None:
        return None
    prefix_lines: list[PositionedLine] = []
    for column in (0, 1):
        column_left = 0.0 if column == 0 else page.width / 2
        column_right = page.width / 2 if column == 0 else page.width
        first_question_top = min(
            (
                candidate.bbox[1] * page.height
                for candidate in page.candidates
                if column_left / page.width <= candidate.bbox[0] < column_right / page.width
            ),
            default=(page.answer_key_top or page.height * 0.95),
        )
        prefix_lines.extend(
            line
            for line in page.lines
            if page.height * 0.09 <= line.top < first_question_top - 1.0
            and column_left <= line.center_x < column_right
            and not RANGE_QUESTION_CUE.search(line.text)
        )
    prefix_lines.sort(key=lambda line: (line.top, line.left))
    continuation_text = "\n".join(line.text for line in prefix_lines)
    if not re.search(r"(?:^|\s)[A-E]\)", continuation_text):
        return None
    prior_json = str(eligible.get("raw_json") or "{}")
    text = (
        "Previously stored incomplete question JSON:\n"
        + prior_json
        + "\nContinuation printed at the top of this page:\n"
        + continuation_text
    )
    bbox = (
        0.0,
        page.height * 0.09 / page.height,
        1.0,
        max((line.bottom for line in prefix_lines), default=page.height * 0.09)
        / page.height,
    )
    combined_line = PositionedLine(
        text=text,
        left=0.0,
        top=bbox[1] * page.height,
        right=page.width,
        bottom=bbox[3] * page.height,
    )
    return QuestionCandidate(
        number=str(eligible["printed_number"]),
        bbox=bbox,
        lines=(combined_line,),
    )


def deterministic_vision_reviews(page: PositionedPage) -> dict[str, str]:
    return {
        candidate.number: "text indicates meaningful layout, underlining, table, or visual content"
        for candidate in page.candidates
        if VISUAL_CUES.search(candidate.text)
    }


def make_text_payload(model: str, prompt: str, temperature: float) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": TEXT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }


def ollama_native_endpoint(endpoint: str) -> str | None:
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.port != 11434:
        return None
    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, "/api/chat", "", "", "")
    )


def make_ollama_native_payload(
    payload: dict[str, Any], image_paths: list[Path]
) -> tuple[dict[str, Any], dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    last_user = max(
        (
            index
            for index, message in enumerate(payload.get("messages", []))
            if message.get("role") == "user"
        ),
        default=-1,
    )
    for index, message in enumerate(payload.get("messages", [])):
        content = message.get("content", "")
        if isinstance(content, list):
            text = "\n".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        else:
            text = str(content)
        native_message: dict[str, Any] = {
            "role": str(message.get("role", "user")),
            "content": text,
        }
        if index == last_user and image_paths:
            native_message["images"] = [
                base64.b64encode(path.read_bytes()).decode("ascii")
                for path in image_paths
            ]
        messages.append(native_message)
    options: dict[str, Any] = {"temperature": float(payload.get("temperature", 0.0))}
    if payload.get("max_tokens") is not None:
        options["num_predict"] = int(payload["max_tokens"])
    native = {
        "model": payload["model"],
        "messages": messages,
        "stream": False,
        "format": "json",
        "think": False,
        "keep_alive": "10m",
        "options": options,
    }
    sanitized = json.loads(json.dumps(native))
    for message in sanitized["messages"]:
        if "images" in message:
            message["images"] = [
                {
                    "path": str(path),
                    "sha256": core.file_sha256(path),
                    "bytes": path.stat().st_size,
                }
                for path in image_paths
            ]
    return native, sanitized


def call_model(
    *,
    endpoint: str,
    api_key: str | None,
    payload: dict[str, Any],
    page_number: int,
    stage: str,
    timeout: float,
    max_retries: int,
    interaction_logger: core.InteractionLogger,
    image_paths: list[Path] | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any], float]:
    paths = image_paths or []
    native_endpoint = ollama_native_endpoint(endpoint) if paths else None
    include_response_format = True
    started = time.monotonic()
    last_error: Exception | None = None
    raw_response = ""
    sanitized: dict[str, Any] = {}
    for attempt in range(1, max_retries + 2):
        request_payload = dict(payload)
        if native_endpoint is not None:
            actual_payload, sanitized = make_ollama_native_payload(
                request_payload, paths
            )
            actual_endpoint = native_endpoint
        else:
            if not include_response_format:
                request_payload.pop("response_format", None)
            actual_payload = request_payload
            actual_endpoint = endpoint
            sanitized = core.sanitized_payload(request_payload, paths)
        interaction_logger.write(
            {
                "event": "request",
                "stage": stage,
                "page": page_number,
                "attempt": attempt,
                "endpoint": actual_endpoint,
                "payload": sanitized,
            }
        )
        LOG.debug(
            "Page %d %s attempt %d: %s with %d image(s)",
            page_number,
            stage,
            attempt,
            actual_endpoint,
            len(paths),
        )
        try:
            response, raw_response = core.post_chat_completion(
                actual_endpoint, api_key, actual_payload, timeout
            )
            if native_endpoint is not None:
                content = str(response.get("message", {}).get("content", ""))
            else:
                content = core.extract_message_content(response)
            parsed = core.parse_model_json(content)
            interaction_logger.write(
                {
                    "event": "response",
                    "stage": stage,
                    "page": page_number,
                    "attempt": attempt,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "response": response,
                    "message_content": content,
                }
            )
            return parsed, raw_response, sanitized, time.monotonic() - started
        except Exception as exc:
            last_error = exc
            error_event: dict[str, Any] = {
                "event": "error",
                "stage": stage,
                "page": page_number,
                "attempt": attempt,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            if raw_response:
                try:
                    error_event["raw_response"] = json.loads(raw_response)
                except json.JSONDecodeError:
                    error_event["raw_response"] = raw_response
            interaction_logger.write(error_event)
            LOG.warning("Page %d %s attempt %d failed: %s", page_number, stage, attempt, exc)
            if isinstance(exc, TimeoutError):
                break
            if (
                native_endpoint is None
                and include_response_format
                and re.search(r"HTTP (?:400|422)\b", str(exc))
            ):
                include_response_format = False
            if attempt <= max_retries:
                time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError(f"Page {page_number} {stage} extraction failed: {last_error}")


def make_question_payload(
    model: str,
    page_number: int,
    candidate: QuestionCandidate,
    context: dict[str, Any],
    temperature: float,
) -> dict[str, Any]:
    compact_context = {
        "current_section": context.get("current_section"),
        "detected_page_header": context.get("detected_page_header"),
        "incomplete_questions": context.get("incomplete_questions", []),
    }
    prompt = (
        f"PDF page {page_number}; expected question number {candidate.number}.\\n"
        f"Use this exact normalized bbox: {json.dumps(candidate.bbox)}\\n"
        f"Context: {json.dumps(compact_context, ensure_ascii=False)}\\n"
        "<question_candidate>\\n"
        f"{candidate.text}\\n"
        "</question_candidate>"
    )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": QUESTION_TEXT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "max_tokens": 4096,
        "reasoning_effort": "low",
    }


def normalize_candidate_result(
    candidate: QuestionCandidate, response: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, str]], list[str]]:
    question = response.get("question")
    if not isinstance(question, dict):
        questions = response.get("questions") or []
        question = questions[0] if questions and isinstance(questions[0], dict) else None
    if not isinstance(question, dict):
        raise ValueError(f"Question {candidate.number} response has no question object")
    question["number"] = candidate.number
    question["bbox"] = list(candidate.bbox)
    question.setdefault("section_ref", "current")
    question.setdefault("question_type", "multiple_choice")
    question.setdefault("passage_ref", None)
    question.setdefault("visual_refs", [])
    question.setdefault("choices", [])
    question.setdefault("complete", True)
    question.setdefault("continuation", False)
    question.setdefault("confidence", 0.9)
    if not str(question.get("stem") or "").strip():
        raise ValueError(f"Question {candidate.number} has an empty stem")
    labels = [
        str(choice.get("label") or "").upper()
        for choice in question.get("choices", [])
        if isinstance(choice, dict)
    ]
    vision_review = [
        item
        for item in response.get("vision_review", [])
        if isinstance(item, dict)
    ]
    if len(set(labels)) < 2:
        vision_review.append(
            {
                "question_number": candidate.number,
                "reason": "text model returned fewer than two distinct choices",
            }
        )
        question["complete"] = False
    passage = response.get("passage")
    if passage is not None and not isinstance(passage, dict):
        passage = None
    warnings = [str(item) for item in response.get("warnings", [])]
    return question, passage, vision_review, warnings


def deferred_vision_question(
    candidate: QuestionCandidate, reason: str
) -> tuple[dict[str, Any], None, list[dict[str, str]], list[str]]:
    return (
        {
            "section_ref": "current",
            "number": candidate.number,
            "stem": candidate.text,
            "question_type": "multiple_choice",
            "passage_ref": None,
            "visual_refs": [],
            "choices": [],
            "complete": False,
            "continuation": False,
            "bbox": list(candidate.bbox),
            "confidence": 0.0,
        },
        None,
        [{"question_number": candidate.number, "reason": reason}],
        [],
    )


def extract_questions_individually(
    *,
    endpoint: str,
    api_key: str | None,
    model: str,
    page_number: int,
    page: PositionedPage,
    plain_text: str,
    context: dict[str, Any],
    temperature: float,
    timeout: float,
    max_retries: int,
    interaction_logger: core.InteractionLogger,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], float]:
    continuation_candidate = detect_continuation_candidate(page, context)
    result: dict[str, Any] = {
        "page_number": page_number,
        "page_types": ["questions"] if page.candidates or continuation_candidate else [],
        "section_events": [],
        "passages": [],
        "visuals": [],
        "questions": [],
        "answers": [],
        "vision_review": [],
        "warnings": [],
    }
    if core.has_embedded_answer_key(plain_text):
        result["page_types"].append("answer_key")
    elif not page.candidates and continuation_candidate is None:
        result["page_types"].append("front_matter")
    raw_responses: dict[str, Any] = {}
    requests: dict[str, Any] = {}
    started = time.monotonic()
    passage_fingerprints: dict[str, str] = {}
    range_passage_refs: dict[str, str] = {}
    for range_passage, question_numbers in deterministic_range_passages(page):
        passage_text = str(range_passage["text"])
        fingerprint = hashlib.sha256(passage_text.encode("utf-8")).hexdigest()[:16]
        passage_fingerprints[fingerprint] = str(range_passage["local_ref"])
        result["passages"].append(range_passage)
        for number in question_numbers:
            range_passage_refs[number] = str(range_passage["local_ref"])
    candidates = (
        (continuation_candidate, *page.candidates)
        if continuation_candidate is not None
        else page.candidates
    )
    for candidate in candidates:
        question = deterministic_question(candidate)
        if question is not None:
            passage = None
            reviews: list[dict[str, str]] = []
            warnings: list[str] = []
        elif context.get("profile") == "pegem":
            question, passage, reviews, warnings = deferred_vision_question(
                candidate,
                "OCR could not deterministically recover all question text and choices",
            )
        else:
            try:
                response, raw, request, _ = call_model(
                    endpoint=endpoint,
                    api_key=api_key,
                    payload=make_question_payload(
                        model, page_number, candidate, context, temperature
                    ),
                    page_number=page_number,
                    stage=f"text-q-{candidate.number}",
                    timeout=timeout,
                    max_retries=max_retries,
                    interaction_logger=interaction_logger,
                )
                question, passage, reviews, warnings = normalize_candidate_result(
                    candidate, response
                )
                raw_responses[candidate.number] = json.loads(raw)
                requests[candidate.number] = request
            except Exception as exc:
                if not VISUAL_CUES.search(candidate.text):
                    raise
                LOG.warning(
                    "Page %d question %s text extraction deferred to vision: %s",
                    page_number,
                    candidate.number,
                    exc,
                )
                question, passage, reviews, warnings = deferred_vision_question(
                    candidate,
                    f"text extraction failed; vision required: {exc}",
                )
        if candidate is continuation_candidate:
            question["continuation"] = True
        if passage:
            passage_text = str(
                passage.get("text")
                or passage.get("markdown")
                or passage.get("description")
                or ""
            ).strip()
            if passage_text:
                fingerprint = hashlib.sha256(
                    passage_text.encode("utf-8")
                ).hexdigest()[:16]
                local_ref = passage_fingerprints.get(fingerprint)
                if local_ref is None:
                    local_ref = f"passage_q{candidate.number}"
                    passage_fingerprints[fingerprint] = local_ref
                    passage.update(
                        {
                            "local_ref": local_ref,
                            "section_ref": question.get("section_ref", "current"),
                        }
                    )
                    passage.setdefault("text", passage_text)
                    passage.setdefault("markdown", None)
                    passage.setdefault("description", None)
                    passage.setdefault("visual_refs", [])
                    passage.setdefault("bbox", None)
                    result["passages"].append(passage)
                question["passage_ref"] = local_ref
        if not question.get("passage_ref") and candidate.number in range_passage_refs:
            question["passage_ref"] = range_passage_refs[candidate.number]
        result["questions"].append(question)
        result["vision_review"].extend(reviews)
        result["warnings"].extend(warnings)
    return result, raw_responses, requests, time.monotonic() - started


def crop_question(
    full_image: Path,
    output_path: Path,
    bbox: tuple[float, float, float, float],
    padding: float = 0.012,
) -> Path:
    left = max(0.0, bbox[0] - padding)
    top = max(0.0, bbox[1] - padding)
    right = min(1.0, bbox[2] + padding)
    bottom = min(1.0, bbox[3] + padding)
    width = max(0.01, right - left)
    height = max(0.01, bottom - top)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = core.require_binary("ffmpeg")
    crop_filter = (
        f"crop=trunc(iw*{width}/2)*2:trunc(ih*{height}/2)*2:"
        f"trunc(iw*{left}/2)*2:trunc(ih*{top}/2)*2"
    )
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(full_image),
            "-vf",
            crop_filter,
            "-q:v",
            "2",
            str(output_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode or not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Could not crop {output_path.name}: {result.stderr.strip()}")
    return output_path


def collect_vision_reviews(
    result: dict[str, Any], page: PositionedPage, _limit: int
) -> list[tuple[str, str]]:
    reviews = deterministic_vision_reviews(page)
    for item in result.get("vision_review", []):
        if not isinstance(item, dict):
            continue
        number = str(item.get("question_number") or "")
        if number:
            reviews[number] = str(item.get("reason") or "model requested visual verification")
    for question in result.get("questions", []):
        if not isinstance(question, dict):
            continue
        number = str(question.get("number") or "")
        choices = question.get("choices") or []
        confidence = question.get("confidence")
        if number and (len(choices) < 2 or (confidence is not None and float(confidence) < 0.8)):
            reviews[number] = "incomplete choices or low text confidence"
    available = candidate_map(page)
    return [
        (number, reason)
        for number, reason in reviews.items()
        if number in available
    ]


def make_vision_payload(
    model: str,
    page_number: int,
    result: dict[str, Any],
    reviews: list[tuple[str, str]],
    crops: list[Path],
    temperature: float,
) -> dict[str, Any]:
    existing = {
        str(question.get("number")): question
        for question in result.get("questions", [])
        if isinstance(question, dict)
        and str(question.get("number")) in {number for number, _ in reviews}
    }
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"Verify selected questions from PDF page {page_number}.\n"
                f"Reasons: {json.dumps(dict(reviews), ensure_ascii=False)}\n"
                f"Text-first questions: {json.dumps(existing, ensure_ascii=False)}"
            ),
        }
    ]
    for (number, reason), crop in zip(reviews, crops):
        content.extend(
            [
                {"type": "text", "text": f"Question {number} crop; review reason: {reason}"},
                {
                    "type": "image_url",
                    "image_url": {"url": core.data_url(crop), "detail": "high"},
                },
            ]
        )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }


def apply_vision_result(
    result: dict[str, Any], vision_result: dict[str, Any]
) -> dict[str, Any]:
    questions = {
        str(question.get("number")): question
        for question in result.get("questions", [])
        if isinstance(question, dict)
    }
    visual_refs_by_question: dict[str, list[str]] = {}
    visuals = result.setdefault("visuals", [])
    existing_visual_refs = {
        str(item.get("local_ref")) for item in visuals if isinstance(item, dict)
    }
    for index, visual in enumerate(vision_result.get("visuals", [])):
        if not isinstance(visual, dict) or not visual.get("description"):
            continue
        number = str(visual.pop("question_number", ""))
        local_ref = str(visual.get("local_ref") or f"vision_visual_{index + 1}")
        while local_ref in existing_visual_refs:
            local_ref += "_v"
        existing_visual_refs.add(local_ref)
        visual["local_ref"] = local_ref
        question = questions.get(number)
        visual["section_ref"] = (
            question.get("section_ref", "current") if question else "current"
        )
        visuals.append(visual)
        visual_refs_by_question.setdefault(number, []).append(local_ref)
    for number, refs in visual_refs_by_question.items():
        question = questions.get(number)
        if question is not None:
            existing_refs = list(question.get("visual_refs") or [])
            existing_refs.extend(refs)
            question["visual_refs"] = list(dict.fromkeys(existing_refs))

    for update in vision_result.get("question_updates", []):
        if not isinstance(update, dict):
            continue
        number = str(update.get("number") or "")
        question = questions.get(number)
        if question is None:
            continue
        for key in ("stem", "choices", "complete", "confidence"):
            if key in update and update[key] is not None:
                question[key] = update[key]
        refs = list(update.get("visual_refs") or [])
        refs.extend(visual_refs_by_question.get(number, []))
        if refs:
            question["visual_refs"] = list(dict.fromkeys(refs))
    result.setdefault("warnings", []).extend(
        str(item) for item in vision_result.get("warnings", [])
    )
    result["vision_refinement"] = {
        "questions_updated": len(vision_result.get("question_updates", [])),
        "visuals_added": len(vision_result.get("visuals", [])),
    }
    return result


def mark_unreviewed_incomplete(
    result: dict[str, Any], reviews: list[tuple[str, str]], reason: str
) -> None:
    numbers = {number for number, _ in reviews}
    for question in result.get("questions", []):
        if isinstance(question, dict) and str(question.get("number")) in numbers:
            question["complete"] = False
            current = question.get("confidence")
            question["confidence"] = min(float(current or 0.75), 0.75)
    result.setdefault("warnings", []).append(reason)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Text-first question extraction with selective vision refinement."
    )
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--db", type=Path, default=Path("questions-text.sqlite"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1"),
    )
    parser.add_argument(
        "--text-model", default=os.environ.get("LOCAL_TEXT_MODEL", "gpt-oss:120b")
    )
    parser.add_argument(
        "--vision-model", default=os.environ.get("LOCAL_VISION_MODEL", "qwen3.6:27b")
    )
    parser.add_argument("--api-key", default=os.environ.get("LOCAL_LLM_API_KEY"))
    parser.add_argument("--pages", default="9-")
    parser.add_argument(
        "--ocr-backend",
        choices=("embedded", "vision"),
        default="embedded",
        help="positioned text source (default: embedded PDF text)",
    )
    parser.add_argument(
        "--profile",
        choices=("paraf", "pegem"),
        default="paraf",
        help="book-specific section and page conventions",
    )
    parser.add_argument("--text-timeout", type=float, default=180.0)
    parser.add_argument("--vision-timeout", type=float, default=600.0)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--max-vision-questions", type=int, default=6)
    model_mode = parser.add_mutually_exclusive_group()
    model_mode.add_argument("--no-vision", action="store_true")
    model_mode.add_argument(
        "--vision-only",
        action="store_true",
        help="reuse stored incomplete page JSON and run only selective vision",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--render-dir", type=Path)
    parser.add_argument("--interaction-log", type=Path)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.vision_only and args.force:
        parser.error("--vision-only cannot be combined with --force")
    core.configure_logging(args.verbose)
    pdf_path = args.pdf.resolve()
    db_path = args.db.resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    page_count = core.pdf_page_count(pdf_path)
    pages = core.parse_pages(args.pages, page_count)
    pdf_hash = core.file_sha256(pdf_path)
    render_dir = (
        args.render_dir.resolve()
        if args.render_dir
        else db_path.with_suffix(db_path.suffix + ".assets") / pdf_hash[:16]
    )
    interaction_logger = core.InteractionLogger(
        args.interaction_log.resolve() if args.interaction_log else None
    )
    connection = core.initialize_database(db_path)
    source_id = core.ensure_source(connection, pdf_path, pdf_hash, page_count)
    endpoint = core.endpoint_url(args.base_url)
    config = {
        "pipeline": "text-first",
        "pages": args.pages,
        "text_model": None if args.vision_only else args.text_model,
        "vision_model": None if args.no_vision else args.vision_model,
        "dpi": args.dpi,
        "max_vision_questions": args.max_vision_questions,
        "render_dir": str(render_dir),
        "ocr_backend": args.ocr_backend,
        "profile": args.profile,
    }
    cursor = connection.execute(
        """
        INSERT INTO extraction_runs(source_id, model, endpoint, config_json, started_at, status)
        VALUES (?, ?, ?, ?, ?, 'running')
        """,
        (
            source_id,
            f"text={'reused' if args.vision_only else args.text_model};"
            f"vision={'off' if args.no_vision else args.vision_model}",
            endpoint,
            core.json_compact(config),
            core.utc_now(),
        ),
    )
    run_id = int(cursor.lastrowid)
    connection.commit()

    try:
        for page_number in pages:
            existing = connection.execute(
                "SELECT * FROM pages WHERE source_id=? AND page_number=?",
                (source_id, page_number),
            ).fetchone()
            if existing and existing["status"] == "complete" and not args.force:
                LOG.info("Page %d already complete; skipping", page_number)
                continue
            stored_result: dict[str, Any] | None = None
            if args.vision_only:
                stored_json = existing["parsed_json"] if existing else None
                if not stored_json:
                    LOG.info(
                        "Page %d has no stored extraction to refine; skipping",
                        page_number,
                    )
                    continue
                parsed_stored_result = json.loads(str(stored_json))
                if not isinstance(parsed_stored_result, dict):
                    raise ValueError(
                        f"Page {page_number} stored parsed_json is not an object"
                    )
                parsed_stored_result["warnings"] = [
                    warning
                    for warning in parsed_stored_result.get("warnings", [])
                    if not (
                        str(warning).startswith(
                            "Selective vision was disabled for questions"
                        )
                        or str(warning).startswith(
                            f"Selective vision failed for page {page_number}"
                        )
                        or "deferred by --max-vision-questions" in str(warning)
                    )
                ]
                stored_result = parsed_stored_result
            if existing and not args.vision_only:
                with connection:
                    core.cleanup_page_data(connection, source_id, page_number)
            started = time.monotonic()
            current_section_id = previous_active_section(
                connection, source_id, page_number
            )
            full_image: Path | None = None
            answer_band: Path | None = None
            if args.ocr_backend == "vision":
                full_image, answer_band = core.render_page(
                    pdf_path,
                    page_number,
                    render_dir,
                    args.dpi,
                    0.05,
                    args.force,
                )
                width, height, observations = vision_ocr.recognize(
                    full_image, render_dir / ".tools"
                )
                plain_text = vision_ocr.plain_text(width, observations)
                positioned = parse_positioned_page(
                    vision_ocr.positioned_tsv(width, height, observations)
                )
            else:
                plain_text = core.extract_page_text(pdf_path, page_number)
                positioned = parse_positioned_page(
                    run_tsv_extraction(pdf_path, page_number)
                )
            context = core.build_page_context(connection, source_id, current_section_id)
            if args.profile == "pegem":
                context["profile"] = "pegem"
                context["detected_page_header"] = detect_pegem_header(
                    positioned, page_number, context
                )
                positioned = repair_continuation_numbers(positioned, context)
            else:
                context["detected_page_header"] = stabilize_detected_header(
                    plain_text, context
                )

            connection.execute(
                """
                INSERT INTO pages(
                    source_id, page_number, run_id, status, pdf_text,
                    active_section_before_id
                ) VALUES (?, ?, ?, 'processing', ?, ?)
                ON CONFLICT(source_id, page_number) DO UPDATE SET
                    run_id=excluded.run_id, status='processing', pdf_text=excluded.pdf_text,
                    active_section_before_id=excluded.active_section_before_id, error=NULL
                """,
                (source_id, page_number, run_id, plain_text, current_section_id),
            )
            page_row = connection.execute(
                "SELECT id FROM pages WHERE source_id=? AND page_number=?",
                (source_id, page_number),
            ).fetchone()
            assert page_row is not None
            page_id = int(page_row["id"])
            connection.commit()

            raw_responses: dict[str, Any] = {}
            requests: dict[str, Any] = {}
            try:
                if stored_result is not None:
                    result = stored_result
                    text_elapsed = 0.0
                else:
                    text_result, raw_text, text_request, text_elapsed = (
                        extract_questions_individually(
                            endpoint=endpoint,
                            api_key=args.api_key,
                            model=args.text_model,
                            page_number=page_number,
                            page=positioned,
                            plain_text=plain_text,
                            context=context,
                            temperature=args.temperature,
                            timeout=args.text_timeout,
                            max_retries=args.max_retries,
                            interaction_logger=interaction_logger,
                        )
                    )
                    raw_responses["text_questions"] = raw_text
                    requests["text_questions"] = text_request
                    result = core.ensure_detected_section_transition(
                        text_result, context
                    )
                    result = core.merge_embedded_answer_key(
                        result, plain_text, context
                    )
                if args.profile == "pegem":
                    import extract_pegem as pegem

                    result = pegem.normalize_question_page(result, page_number)
                result = core.validate_page_result(result, page_number)

                all_reviews = collect_vision_reviews(
                    result, positioned, args.max_vision_questions
                )
                if args.profile == "pegem" and 6 <= page_number <= 239:
                    reviewed_numbers = {number for number, _ in all_reviews}
                    all_reviews.extend(
                        (
                            candidate.number,
                            "mathematical notation requires image-faithful verification",
                        )
                        for candidate in positioned.candidates
                        if candidate.number not in reviewed_numbers
                    )
                if args.profile == "pegem":
                    reviews = all_reviews
                    deferred_reviews: list[tuple[str, str]] = []
                else:
                    reviews = all_reviews[: args.max_vision_questions]
                    deferred_reviews = all_reviews[args.max_vision_questions :]
                if deferred_reviews:
                    mark_unreviewed_incomplete(
                        result,
                        deferred_reviews,
                        f"Page {page_number} has {len(deferred_reviews)} visual review(s) "
                        "deferred by --max-vision-questions.",
                    )
                if reviews and not args.no_vision:
                    if full_image is None:
                        full_image, answer_band = core.render_page(
                            pdf_path,
                            page_number,
                            render_dir,
                            args.dpi,
                            0.16,
                            args.force,
                        )
                    cmap = candidate_map(positioned)
                    crops = {
                        number: crop_question(
                            full_image,
                            render_dir / "crops" / f"page-{page_number:04d}-q-{number}.jpg",
                            cmap[number].bbox,
                        )
                        for number, _ in reviews
                    }
                    raw_responses["vision"] = {}
                    requests["vision"] = {}
                    vision_started = time.monotonic()
                    completed_reviews = 0
                    review_batches = (
                        [reviews]
                        if args.profile == "pegem"
                        else [[review] for review in reviews]
                    )
                    for review_batch in review_batches:
                        numbers = [number for number, _ in review_batch]
                        batch_crops = [crops[number] for number in numbers]
                        vision_payload = make_vision_payload(
                            args.vision_model,
                            page_number,
                            result,
                            review_batch,
                            batch_crops,
                            args.temperature,
                        )
                        key = ",".join(numbers)
                        try:
                            vision_result, raw_vision, vision_request, _ = call_model(
                                endpoint=endpoint,
                                api_key=args.api_key,
                                payload=vision_payload,
                                page_number=page_number,
                                stage=f"vision-q-{key}",
                                timeout=args.vision_timeout,
                                max_retries=0,
                                interaction_logger=interaction_logger,
                                image_paths=batch_crops,
                            )
                            raw_responses["vision"][key] = json.loads(raw_vision)
                            requests["vision"][key] = vision_request
                            result = apply_vision_result(result, vision_result)
                            completed_reviews += len(review_batch)
                        except Exception as exc:
                            mark_unreviewed_incomplete(
                                result,
                                review_batch,
                                f"Selective vision failed for page {page_number}, "
                                f"questions {key}: {exc}",
                            )
                            LOG.warning(
                                "Page %d questions %s selective vision failed: %s",
                                page_number,
                                key,
                                exc,
                            )
                    LOG.info(
                        "Page %d selective vision reviewed %d/%d question(s) in %.2fs",
                        page_number,
                        completed_reviews,
                        len(reviews),
                        time.monotonic() - vision_started,
                    )
                elif reviews:
                    mark_unreviewed_incomplete(
                        result,
                        reviews,
                        "Selective vision was disabled for questions requiring visual review.",
                    )

                result = core.validate_page_result(result, page_number)
                page_status = (
                    "complete"
                    if all(
                        bool(question.get("complete", True))
                        for question in result.get("questions", [])
                        if isinstance(question, dict)
                    )
                    else "incomplete"
                )
                elapsed = time.monotonic() - started
                with connection:
                    core.cleanup_page_data(connection, source_id, page_number)
                    active_after, _ = core.ingest_page_result(
                        connection,
                        source_id,
                        run_id,
                        page_number,
                        page_id,
                        current_section_id,
                        result,
                    )
                    relink_answer_observations(connection, source_id)
                    connection.execute(
                        """
                        UPDATE pages SET status=?, rendered_image=?, rendered_sha256=?,
                            answer_band_image=?, active_section_after_id=?, request_json=?,
                            raw_response=?, parsed_json=?, error=NULL, elapsed_seconds=?,
                            extracted_at=? WHERE id=?
                        """,
                        (
                            page_status,
                            str(full_image) if full_image else None,
                            core.file_sha256(full_image) if full_image else None,
                            str(answer_band) if answer_band else None,
                            active_after,
                            core.json_compact(requests),
                            core.json_compact(raw_responses),
                            core.json_compact(result),
                            elapsed,
                            core.utc_now(),
                            page_id,
                        ),
                    )
                    if active_after is not None:
                        connection.execute(
                            """
                            UPDATE sections
                            SET source_page_end=MAX(COALESCE(source_page_end, ?), ?)
                            WHERE id=?
                            """,
                            (page_number, page_number, active_after),
                        )
                LOG.info(
                    "Page %d %s in %.2fs (text %.2fs, candidates %d, vision %d): %s",
                    page_number,
                    page_status,
                    elapsed,
                    text_elapsed,
                    len(positioned.candidates),
                    len(reviews) if not args.no_vision else 0,
                    core.counts_for_page(result),
                )
            except Exception as exc:
                connection.execute(
                    "UPDATE pages SET status='failed', error=?, extracted_at=? WHERE id=?",
                    (str(exc), core.utc_now(), page_id),
                )
                connection.commit()
                raise

        connection.execute(
            "UPDATE extraction_runs SET status='complete', finished_at=? WHERE id=?",
            (core.utc_now(), run_id),
        )
        connection.commit()
    except Exception as exc:
        connection.execute(
            """
            UPDATE extraction_runs SET status='failed', finished_at=?, error=? WHERE id=?
            """,
            (core.utc_now(), str(exc), run_id),
        )
        connection.commit()
        raise
    finally:
        connection.close()

    print(f"Text-first extraction complete: {db_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        LOG.error("%s", exc)
        if LOG.isEnabledFor(logging.DEBUG):
            raise
        raise SystemExit(1)
