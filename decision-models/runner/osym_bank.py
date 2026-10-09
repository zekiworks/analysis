#!/usr/bin/env python3
"""Finish a question bank extracted from an ÖSYM exam booklet: one section, boxes and the official key.

Step 3.5 of turkce-benchmark-plan.md. extract_questions.py reads ÖSYM pages well, but:

- it takes the "35 - 36. soruları ... cevaplayınız" instructions, and the passages printed above a
  column's first question, for new section headers;
- it leaves many question boxes empty, and repair_questions.py crops questions by their boxes;
- the booklet prints the answer keys of all its tests together on one page.

This script merges every section into one titled section without a unit number, so the questions
don't count as reading or grammar in the report. It sets each question's and passage's box from where
its number or instruction is printed, and stores the answers from the key page by printed number.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')
INSTRUCTION = re.compile(r"(\d{1,3})\s*-\s*\d{1,3}\.\s*soruları")
Word = tuple[float, float, float, float, str]  # left, top, right, bottom in points, and the text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bank", type=Path, help="question bank written by extract_questions.py")
    parser.add_argument("--title", required=True, help='title of the merged section, such as "2026-TYT Türkçe Testi"')
    parser.add_argument("--key-page", type=int, required=True, help="PDF page of the answer key")
    parser.add_argument("--test", required=True, help='first word of the test\'s heading on the key page, such as "TÜRKÇE"')
    return parser.parse_args()


def page_words(pdf: Path, page: int) -> tuple[float, float, list[Word]]:
    """A page's width and height and its words, from the PDF text layer."""
    output = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), "-bbox", str(pdf), "-"], capture_output=True, check=True
    ).stdout.decode("utf-8", "replace")
    size = re.search(r'<page width="([\d.]+)" height="([\d.]+)"', output)
    if size is None:
        raise ValueError(f"page {page} has no text layer")
    words = [(float(x0), float(y0), float(x1), float(y1), html.unescape(text)) for x0, y0, x1, y1, text in WORD.findall(output)]
    return float(size.group(1)), float(size.group(2)), words


def lines(words: list[Word]) -> list[list[Word]]:
    """Words grouped into lines, top to bottom, each line left to right."""
    grouped: list[list[Word]] = []
    for word in sorted(words, key=lambda word: (word[1], word[0])):
        if grouped and abs(word[1] - grouped[-1][0][1]) <= 2:
            grouped[-1].append(word)
        else:
            grouped.append([word])
    return [sorted(line, key=lambda word: word[0]) for line in grouped]


def answer_key(pdf: Path, page: int, test: str) -> dict[int, str]:
    """The answers printed in one test's column of the key page, by question number.

    The key page prints one column per test, headed "TÜRKÇE TESTİ", "SOSYAL BİLİMLER TESTİ" and so on.
    Words are read with their positions because the page's watermark scrambles plain text extraction.
    """
    _, _, words = page_words(pdf, page)
    heading_lines = [line for line in lines(words) if any(word[4] == test for word in line)]
    if not heading_lines:
        raise ValueError(f"no {test!r} heading on page {page}")
    # The test's name can also appear in the page title ("TEMEL YETERLİLİK TESTİ"); the column headings
    # share one line with several "TESTİ".
    line = max(heading_lines, key=lambda line: sum(word[4].upper() == "TESTİ" for word in line))
    heading = next(word for word in line if word[4] == test)
    # Each heading ends with "TESTİ"; the next heading starts with the word after it.
    starts = [line[0][0]] + [after[0] for before, after in zip(line, line[1:]) if before[4].upper() == "TESTİ"]
    index = max(position for position, start in enumerate(starts) if start <= heading[0])
    # A column runs from halfway after the previous heading (its numbers sit a little left of the
    # heading) to the next heading.
    left = (starts[index - 1] + starts[index]) / 2 if index else 0.0
    right = starts[index + 1] if index + 1 < len(starts) else float("inf")
    column = [word for word in words if left <= word[0] < right and word[1] > heading[3]]
    letters = [word for word in column if re.fullmatch(r"[A-E]", word[4])]
    key: dict[int, str] = {}
    for x0, y0, x1, y1, text in column:
        if not re.fullmatch(r"\d{1,3}\.", text):
            continue
        number = int(text[:-1])
        middle = (y0 + y1) / 2
        same_line = [letter for letter in letters if abs((letter[1] + letter[3]) / 2 - middle) < 2.5 and letter[0] > x1]
        if number in key or len(same_line) != 1:
            raise ValueError(f"question {number} on page {page} has no single answer in the {test} column")
        key[number] = same_line[0][4]
    if not key:
        raise ValueError(f"no answers under the {test!r} heading on page {page}")
    return key


def set_boxes(connection: sqlite3.Connection, pdf: Path) -> None:
    """Set each question's and shared passage's normalized box from the PDF text layer.

    Pages have two columns. A question's number starts a line at its column's margin; an instruction
    such as "35 - 36. soruları …" starts the passage of questions 35 and 36. Each block runs to the next
    one in its column, or to the page footer.
    """
    questions = connection.execute("SELECT id, printed_number, source_page_start, passage_id FROM questions").fetchall()
    missing = {question_id for question_id, _, _, _ in questions}
    for page in sorted({start for _, _, start, _ in questions}):
        width, height, words = page_words(pdf, page)
        on_page = {number: (question_id, passage_id) for question_id, number, start, passage_id in questions if start == page}
        footer = min((word[1] for word in words if word[1] > 0.85 * height), default=height)
        for left, right in ((0.0, width / 2), (width / 2, width)):
            column = [word for word in words if left <= word[0] < right and word[1] < footer]
            if not column:
                continue
            column_lines = lines(column)
            # The watermark's letters are scattered over both columns, so the margin comes from the lines
            # that start with one of the page's question numbers, not from every word.
            numbered = [line[0] for line in column_lines if re.fullmatch(r"\d{1,3}\.", line[0][4]) and line[0][4][:-1] in on_page]
            margin = min((word[0] for word in numbered), default=min(word[0] for word in column))
            blocks = []
            for line in column_lines:
                first, text = line[0], " ".join(word[4] for word in line)
                instruction = INSTRUCTION.match(text)
                if instruction and instruction.group(1) in on_page:
                    blocks.append((first[1], "passage", instruction.group(1)))
                elif first in numbered and first[0] - margin < 8:
                    blocks.append((first[1], "question", first[4][:-1]))
            right_edge = min(max(word[2] for word in column), right)
            for index, (top, kind, number) in enumerate(blocks):
                bottom = blocks[index + 1][0] if index + 1 < len(blocks) else footer
                box = json.dumps([round(margin / width, 4), round(top / height, 4), round(right_edge / width, 4), round(bottom / height, 4)])
                question_id, passage_id = on_page[number]
                if kind == "question":
                    connection.execute("UPDATE questions SET bbox_json = ? WHERE id = ?", (box, question_id))
                    missing.discard(question_id)
                elif passage_id is not None:
                    connection.execute("UPDATE passages SET bbox_json = ? WHERE id = ?", (box, passage_id))
    if missing:
        numbers = sorted(int(number) for question_id, number, _, _ in questions if question_id in missing)
        raise ValueError(f"no printed number found for questions {numbers}")


def merge_sections(connection: sqlite3.Connection, title: str) -> tuple[int, int]:
    """Move every question, passage and visual into the earliest section; returns its ID and the merged count."""
    sections = [row[0] for row in connection.execute("SELECT id FROM sections ORDER BY source_page_start, id")]
    keep, others = sections[0], sections[1:]
    numbers = [row[0] for row in connection.execute("SELECT printed_number FROM questions")]
    if len(numbers) != len(set(numbers)):
        raise ValueError("printed question numbers repeat, so the sections can't be merged")
    for other in others:
        for table, column in (
            ("questions", "section_id"),
            ("passages", "section_id"),
            ("visuals", "section_id"),
            ("answer_observations", "section_id"),
            ("page_section_events", "section_id"),
            ("pages", "active_section_before_id"),
            ("pages", "active_section_after_id"),
        ):
            connection.execute(f"UPDATE {table} SET {column} = ? WHERE {column} = ?", (keep, other))
        connection.execute("DELETE FROM sections WHERE id = ?", (other,))
    last_page = connection.execute("SELECT max(source_page_end) FROM questions").fetchone()[0]
    connection.execute(
        "UPDATE sections SET title = ?, unit_title = ?, unit_number = NULL, source_page_end = ? WHERE id = ?",
        (title, title, last_page, keep),
    )
    return keep, len(others)


def store_answers(connection: sqlite3.Connection, section: int, key: dict[int, str], page: int) -> None:
    questions = {int(number): (question_id, source) for question_id, number, source in connection.execute(
        "SELECT id, printed_number, source_id FROM questions"
    )}
    if set(questions) != set(key):
        raise ValueError(
            f"the key covers questions {sorted(set(key) - set(questions))} that the bank lacks "
            f"and lacks questions {sorted(set(questions) - set(key))}"
        )
    for number, answer in sorted(key.items()):
        question_id, source = questions[number]
        connection.execute(
            """
            INSERT OR REPLACE INTO answer_observations
                (source_id, section_id, question_id, source_page, printed_number, answer, confidence, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, 1.0, ?)
            """,
            (source, section, question_id, page, str(number), answer, json.dumps({"source": "official answer key page"})),
        )
        connection.execute(
            "UPDATE questions SET answer = ?, answer_source_page = ?, answer_confidence = 1.0 WHERE id = ?",
            (answer, page, question_id),
        )


def main() -> int:
    args = parse_args()
    try:
        connection = sqlite3.connect(args.bank)
        try:
            path = connection.execute("SELECT path FROM sources").fetchone()[0]
            pdf = args.bank.resolve().parent / Path(path).name
            key = answer_key(pdf, args.key_page, args.test)
            with connection:
                section, merged = merge_sections(connection, args.title)
                set_boxes(connection, pdf)
                store_answers(connection, section, key, args.key_page)
        finally:
            connection.close()
    except (OSError, ValueError, sqlite3.Error, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"Merged {merged} extra section(s) into {args.title!r}; set every question's box; "
        f"stored {len(key)} answers: {''.join(key[number] for number in sorted(key))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
