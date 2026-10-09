#!/usr/bin/env python3
"""Build questions-v2.sqlite and repair the questions whose extracted text lost its markup.

Steps 1.1 and 1.3–1.6 of turkce-benchmark-plan.md:

  init        copy questions.sqlite to questions-v2.sqlite and add the status and repair tables
  transcribe  propose corrected text for the re-transcription candidates from page crops
  sheet       write repair/review.html, where a person checks questions against their pages
  apply       apply the decisions downloaded from the review page to questions-v2.sqlite
  blind       write repair/blind/review.html, where a person answers a random sample of never-reviewed
              questions without seeing the key (the blind key check, plan step 5.2); with --disputed, every
              excluded and suspect question instead, in repair/blind-disputed/review.html
  blind-compare
              compare the downloaded blind answers with the key, and write the second-look page for the
              disagreements

questions.sqlite is never modified, and question IDs are the same in both databases.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures as futures
import difflib
import html
import json
import random
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import audit_questions
import benchmark_ollama as bo

HERE = Path(__file__).resolve().parent
V1 = HERE / "questions.sqlite"
V2 = HERE / "questions-v2.sqlite"
WORK = HERE / "repair"
RESULTS = HERE / "benchmark-results.sqlite"
# The extractor rendered the PDF crop box at 180 DPI, and its bboxes are relative to that box.
DPI = 180
CROP_PADDING = 0.012  # extract_questions_text.crop_question's padding
ANSWER_BAND = 0.16  # bottom share of a page, where a test's answer-key strip is printed
DEFAULT_ENDPOINT = "http://127.0.0.1:8010"  # vLLM in the gemma4-31b docker container
DEFAULT_MODEL = "gemma-4-31B-it"
PRIMARY_METHOD = f"{DEFAULT_MODEL}/thinking"  # the transcription method the review page proposes
ALTERNATIVE_METHOD = f"{DEFAULT_MODEL}/direct"  # the one it shows for comparison
STATUSES = ("verified", "suspect", "excluded")
PRINTED_NUMBER = re.compile(r"^\d{1,3}\s*[.)]\s+")

SCHEMA = """
CREATE TABLE dataset_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE question_status (
    question_id INTEGER PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('verified', 'suspect', 'excluded')),
    note TEXT,
    checked_at TEXT NOT NULL
);
-- One row per changed field: 'stem', 'passage', 'choice:A' …, 'answer', or 'complete' when a
-- question the extractor left incomplete is checked against its page and kept.
CREATE TABLE question_repairs (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    old_text TEXT,
    new_text TEXT,
    state TEXT NOT NULL CHECK (state IN ('proposed', 'applied', 'rejected')),
    method TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE INDEX question_repairs_question ON question_repairs(question_id, state);
-- The vision model's raw answer per question and method, kept for provenance and resuming.
CREATE TABLE repair_transcriptions (
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    method TEXT NOT NULL,
    images_json TEXT NOT NULL,
    proposal_json TEXT,
    warnings_json TEXT NOT NULL,
    error TEXT,
    response_json TEXT,
    seconds REAL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (question_id, method)
);
"""

SYSTEM_PROMPT = """You correct the transcription of one Turkish multiple-choice question from a scanned page crop.
The crop may also show parts of neighbouring questions; use only the question whose text matches the current transcription.

Rules:
- Keep every word exactly as printed. Do not solve, rephrase, translate or correct the Turkish.
- Write each underlined word or phrase in the passage, poem or options as <u>…</u>.
- Do not mark underlining that only emphasizes a word of the question sentence itself, such as "değildir", "yoktur", "yanlıştır" or "söylenemez".
- A Roman numeral or number printed under, over or next to a word or phrase labels it. Write it right after that word or phrase, in parentheses: <u>eserleri</u> (I).
- A numeral may label a punctuation mark, such as an apostrophe or a comma. Write it right after the word that carries the mark: İstanbul’da (II). Match each numeral to the mark or word directly above it, line by line.
- Every numeral printed in the question appears exactly once, in the order printed.
- Sentences numbered as "(I) …" keep the number before the sentence, as printed.
- Remove numerals that the current transcription placed on their own lines or inside words, and put them where the page shows them.
- Rejoin a word split by a line-end hyphen or by a misplaced numeral ("sayfa- lık" -> "sayfalık"). Keep dashes that belong to the text.
- Do not add the printed question number; the stem starts where the current transcription starts.
- Keep the line breaks of poems. Keep the option labels and their order.
- Keep characters as printed, including curly apostrophes and quotes (’ “ ”).
Return only the JSON object."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--v2", type=Path, default=V2, help="repaired question bank (default: questions-v2.sqlite)")
    parser.add_argument("--work", type=Path, default=WORK, help="crops, page images and review page (default: repair/)")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create questions-v2.sqlite from questions.sqlite")
    init.add_argument("--v1", type=Path, default=V1, help="question bank to copy (default: questions.sqlite)")

    transcribe = commands.add_parser("transcribe", help="propose corrected text for the candidates")
    transcribe.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help=f"OpenAI-compatible server (default: {DEFAULT_ENDPOINT})")
    transcribe.add_argument("--model", default=DEFAULT_MODEL, help=f"vision model (default: {DEFAULT_MODEL})")
    transcribe.add_argument("--mode", choices=("thinking", "direct"), default="thinking", help="thinking on or off (default: thinking)")
    transcribe.add_argument("--propose", action="store_true", help="also store the results as proposals to review")
    transcribe.add_argument("--question", type=int, action="append", help="only this question ID (repeatable)")
    transcribe.add_argument("--all", action="store_true", help="every benchmark question, not only the candidates")
    transcribe.add_argument("--limit", type=int, help="only the first N remaining candidates")
    transcribe.add_argument("--concurrency", type=int, default=4, help="parallel requests (default: 4)")
    transcribe.add_argument("--timeout", type=float, default=900.0, help="seconds per request (default: 900)")
    transcribe.add_argument(
        "--max-tokens", type=int, help="output token limit, thinking included (default: 8192 thinking, 2048 direct)"
    )
    transcribe.add_argument("--force", action="store_true", help="redo questions already transcribed with this method")
    transcribe.add_argument(
        "--reparse", action="store_true", help="rebuild proposals from the stored answers without asking the model again"
    )

    sheet = commands.add_parser("sheet", help="write the review page")
    sheet.add_argument("--primary", default=PRIMARY_METHOD, help="method whose proposals are reviewed")
    sheet.add_argument("--alternative", default=ALTERNATIVE_METHOD, help="method shown for comparison")
    sheet.add_argument("--spot-per-unit", type=int, default=5, help="unflagged questions to spot-check per unit (default: 5)")
    sheet.add_argument("--seed", type=int, default=2026, help="seed for the spot-check sample (default: 2026)")
    sheet.add_argument(
        "--question", type=int, action="append",
        help="only these question IDs (repeatable): a disputed key is shown with its answer-key strip, any other as a re-transcription",
    )
    sheet.add_argument(
        "--as-keys", action="store_true",
        help="show every --question as a key to check, with its answer-key strip, disputed or not",
    )
    sheet.add_argument(
        "--reference-data", type=Path, default=V1,
        help="question bank whose GPT-6 Astra, Opus and Sonnet runs dispute keys and show their answers (default: questions.sqlite)",
    )
    sheet.add_argument(
        "--blind-answers", type=Path,
        help="answers file downloaded from the blind page: shows each question's blind answer beside the models'",
    )

    apply = commands.add_parser("apply", help="apply downloaded review decisions")
    apply.add_argument("decisions", type=Path, help="decisions file downloaded from the review page")

    blind = commands.add_parser("blind", help="write the blind key check page")
    blind.add_argument("--count", type=int, default=100, help="questions in the sample (default: 100)")
    blind.add_argument("--seed", type=int, default=2026, help="seed of the sample (default: 2026)")
    blind.add_argument(
        "--disputed", action="store_true",
        help="every excluded and suspect question, for a reviewer who has seen no model's answers, instead of a "
        "random sample (written to repair/blind-disputed)",
    )

    compare = commands.add_parser("blind-compare", help="compare blind answers with the key and write the second look")
    compare.add_argument("answers", type=Path, help="answers file downloaded from the blind page")
    return parser.parse_args()


def connect(path: Path, readonly: bool = False) -> sqlite3.Connection:
    if not path.is_file():
        hint = "; create it with `repair_questions.py init`" if path.name == V2.name else ""
        raise ValueError(f"{path} does not exist{hint}")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True) if readonly else sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# ---------------------------------------------------------------- init


def add_status_to_view(view_sql: str) -> str:
    """The benchmark_questions view with each question's review status."""
    columns_end = "    q.answer_confidence\nFROM questions q"
    if columns_end not in view_sql or "LEFT JOIN question_status" in view_sql:
        raise ValueError("benchmark_questions has an unexpected definition")
    view_sql = view_sql.replace(
        columns_end, "    q.answer_confidence,\n    qs.status,\n    qs.note AS status_note\nFROM questions q"
    )
    return view_sql.rstrip().rstrip(";") + "\nLEFT JOIN question_status qs ON qs.question_id = q.id"


def init(args: argparse.Namespace) -> int:
    if args.v2.exists():
        raise ValueError(f"{args.v2} already exists; remove it to start over")
    source = connect(args.v1, readonly=True)
    target = sqlite3.connect(args.v2)
    try:
        source.backup(target)
        with target:
            target.executescript(SCHEMA)
            view_sql = target.execute(
                "SELECT sql FROM sqlite_master WHERE type='view' AND name='benchmark_questions'"
            ).fetchone()[0]
            target.execute("DROP VIEW benchmark_questions")
            target.execute(add_status_to_view(view_sql))
            target.executemany(
                "INSERT INTO dataset_info (key, value) VALUES (?, ?)",
                [
                    ("version", "2"),
                    ("derived_from", args.v1.name),
                    ("derived_from_sha256", bo.file_sha256(args.v1)),
                    ("created_at", utc_now()),
                ],
            )
    finally:
        source.close()
        target.close()
    v1 = bo.load_questions(args.v1, None, None, None, 0).questions
    v2 = bo.load_questions(args.v2, None, None, None, 0).questions
    same = [(q.question_id, q.prompt, q.answer) for q in v1] == [(q.question_id, q.prompt, q.answer) for q in v2]
    print(f"Created {args.v2}: {len(v2)} benchmark questions, identical to {args.v1.name}: {same}")
    return 0 if same else 1


# ---------------------------------------------------------------- pages and crops


def source_pdf(connection: sqlite3.Connection, database: Path) -> Path:
    """The extracted PDF, found next to the database and checked against the stored hash."""
    row = connection.execute("SELECT path, sha256 FROM sources").fetchone()
    pdf = database.parent / Path(row["path"]).name
    if not pdf.is_file() or bo.file_sha256(pdf) != row["sha256"]:
        raise ValueError(f"{pdf.name} is missing or differs from the extracted PDF")
    return pdf


def pdftoppm(pdf: Path, page: int, prefix: Path, *options: str) -> None:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    command = ["pdftoppm", "-f", str(page), "-l", str(page), "-cropbox", "-r", str(DPI), "-singlefile", *options, str(pdf), str(prefix)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"pdftoppm failed on page {page}: {result.stderr.strip()}")


def page_pixels(pdf: Path, page: int, cache: dict[int, tuple[int, int]]) -> tuple[int, int]:
    if page not in cache:
        output = subprocess.run(
            ["pdfinfo", "-f", str(page), "-l", str(page), str(pdf)], capture_output=True, text=True, check=True
        ).stdout
        match = re.search(rf"Page\s+{page}\s+size:\s+([\d.]+) x ([\d.]+) pts", output)
        if match is None:
            raise RuntimeError(f"pdfinfo reported no size for page {page}")
        cache[page] = (round(float(match.group(1)) * DPI / 72), round(float(match.group(2)) * DPI / 72))
    return cache[page]


def render_region(pdf: Path, page: int, box: list[float], out: Path, cache: dict[int, tuple[int, int]]) -> Path:
    """Render a normalized [left, top, right, bottom] region of a page to PNG, padded like the extractor."""
    if not out.exists():
        width, height = page_pixels(pdf, page, cache)
        left = max(0.0, box[0] - CROP_PADDING) * width
        top = max(0.0, box[1] - CROP_PADDING) * height
        right = min(1.0, box[2] + CROP_PADDING) * width
        bottom = min(1.0, box[3] + CROP_PADDING) * height
        pdftoppm(
            pdf, page, out.with_suffix(""), "-png",
            "-x", str(round(left)), "-y", str(round(top)), "-W", str(round(right - left)), "-H", str(round(bottom - top)),
        )
    return out


def render_page(pdf: Path, page: int, work: Path) -> Path:
    out = work / "pages" / f"page-{page:04d}.jpg"
    if not out.exists():
        pdftoppm(pdf, page, out.with_suffix(""), "-jpeg", "-jpegopt", "quality=92")
    return out


def question_images(connection: sqlite3.Connection, pdf: Path, work: Path, question_id: int, cache: dict) -> list[tuple[str, Path]]:
    """Crops of a question and of its shared passage, if it has one."""
    row = connection.execute(
        """
        SELECT q.source_page_start, q.bbox_json, p.source_page AS passage_page, p.bbox_json AS passage_bbox
        FROM questions q LEFT JOIN passages p ON p.id = q.passage_id WHERE q.id = ?
        """,
        (question_id,),
    ).fetchone()
    images = []
    if row["passage_bbox"]:
        images.append(("Passage crop", render_region(
            pdf, row["passage_page"], json.loads(row["passage_bbox"]), work / "crops" / f"q{question_id}-passage.png", cache
        )))
    images.append(("Question crop", render_region(
        pdf, row["source_page_start"], json.loads(row["bbox_json"]), work / "crops" / f"q{question_id}.png", cache
    )))
    return images


def answer_band(pdf: Path, page: int, work: Path, cache: dict) -> Path:
    return render_region(pdf, page, [0.0, 1.0 - ANSWER_BAND, 1.0, 1.0], work / "bands" / f"p{page:04d}.png", cache)


# ---------------------------------------------------------------- question text


def current_text(connection: sqlite3.Connection, question_id: int) -> dict[str, str | None]:
    """A question's editable fields: 'passage' (if shared), 'stem' and 'choice:A' …"""
    row = connection.execute(
        "SELECT q.stem, p.text AS passage FROM questions q LEFT JOIN passages p ON p.id = q.passage_id WHERE q.id = ?",
        (question_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"question {question_id} does not exist")
    fields: dict[str, str | None] = {}
    if row["passage"] is not None:
        fields["passage"] = row["passage"]
    fields["stem"] = row["stem"]
    for choice in connection.execute("SELECT label, text FROM choices WHERE question_id = ? ORDER BY id", (question_id,)):
        fields[f"choice:{choice['label']}"] = choice["text"]
    return fields


def write_field(connection: sqlite3.Connection, question_id: int, field: str, text: str) -> None:
    if field == "stem":
        connection.execute("UPDATE questions SET stem = ? WHERE id = ?", (text, question_id))
    elif field == "passage":
        connection.execute(
            "UPDATE passages SET text = ? WHERE id = (SELECT passage_id FROM questions WHERE id = ?)", (text, question_id)
        )
    elif field.startswith("choice:"):
        connection.execute(
            "UPDATE choices SET text = ? WHERE question_id = ? AND label = ?", (text, question_id, field.split(":", 1)[1])
        )
    else:
        raise ValueError(f"unknown field {field!r}")


QUOTE_STYLES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})
ROMAN = r"(?:VIII|VII|VI|IV|IX|X|V|III|II|I)"  # longest first
LABEL_NUMERAL = re.compile(rf"\((?:{ROMAN}|10|[1-9])\)")
GLUED_NUMERAL = re.compile(rf"(?<=[a-zçğıöşü]){ROMAN}\b")
LOOSE_NUMERAL = re.compile(rf"(?<![\w']){ROMAN}(?![\w'.])")
HYPHENS = ("-", "‐")
# Particles that Turkish spelling writes as separate words; joining or splitting them is what spelling
# questions test, so such a rejoin is a change, not just a repaired word break.
PARTICLE = re.compile(r"^(?:de|da|ki|m[iıuü]\w*)$")


def comparable_tokens(text: str | None, drop_numerals: bool) -> list[str]:
    """A field's words and punctuation marks, without markup, line breaks or quote styles.

    Repairs move the numerals that label words, so `drop_numerals` removes them (for passages and stems).
    """
    text = re.sub(r"</?u>", "", text or "", flags=re.IGNORECASE)  # markup may sit inside a word
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE).replace("…", "...").translate(QUOTE_STYLES)
    if drop_numerals:
        text = LABEL_NUMERAL.sub(" ", text)
        text = GLUED_NUMERAL.sub("", text)
        text = LOOSE_NUMERAL.sub(" ", text)
    return re.findall(r"\w+|[^\w\s]", text)


def shown(tokens: list[str], limit: int = 50) -> str:
    text = re.sub(r" (?=[.,;:!?)'\"])|(?<=\() ", "", " ".join(tokens))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def text_changes(field: str, old: str | None, new: str) -> list[str]:
    """What a proposal changes besides markup and numeral placement, as notes for the reviewer.

    Notes starting with "rejoins" only join or split words without changing letters. Every other note
    changes letters, punctuation or the spacing of a particle, which must be checked against the page.
    """
    drop = field in ("stem", "passage")
    before_tokens, after_tokens = comparable_tokens(old, drop), comparable_tokens(new, drop)
    rejoined, changed = [], []
    matcher = difflib.SequenceMatcher(None, before_tokens, after_tokens, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        before, after = before_tokens[i1:i2], after_tokens[j1:j2]
        has_words = any(token[0].isalnum() for token in before) and any(token[0].isalnum() for token in after)
        letters_before = "".join(token for token in before if token not in HYPHENS)
        letters_after = "".join(token for token in after if token not in HYPHENS)
        if has_words and letters_before == letters_after:
            # A hyphen marks a line-end break; particles written apart never carry one.
            hyphenated = any(token in HYPHENS for token in before + after)
            if not hyphenated and any(PARTICLE.match(token) for token in before[1:] + after[1:]):
                changed.append(f"spacing “{shown(before)}” → “{shown(after)}”")
            else:
                rejoined.append(f"“{shown(before)}” → “{shown(after)}”")
        elif not before:
            changed.append(f"adds “{shown(after)}”")
        elif not after:
            changed.append(f"drops “{shown(before)}”")
        else:
            changed.append(f"“{shown(before)}” → “{shown(after)}”")
    label = {"stem": "the question", "passage": "the passage"}.get(field, f"option {field.split(':', 1)[-1]}")
    notes = []
    for kind, items in (("changes", changed), ("rejoins", rejoined)):
        if items:
            more = f" (and {len(items) - 3} more)" if len(items) > 3 else ""
            notes.append(f"{kind} in {label}: " + "; ".join(items[:3]) + more)
    return notes


# ---------------------------------------------------------------- transcribe


def transcription_request(
    model: str, mode: str, max_tokens: int, current: dict[str, str | None], images: list[tuple[str, Path]]
) -> dict[str, Any]:
    choices = [{"label": field.split(":", 1)[1], "text": text} for field, text in current.items() if field.startswith("choice:")]
    shown = {key: current[key] for key in ("passage", "stem") if key in current} | {"choices": choices}
    properties: dict[str, Any] = {"passage": {"type": "string"}} if "passage" in current else {}
    properties |= {
        "stem": {"type": "string"},
        "choices": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "text": {"type": "string"}},
                "required": ["label", "text"],
                "additionalProperties": False,
            },
        },
    }
    content: list[dict[str, Any]] = [
        {"type": "text", "text": "Current transcription:\n" + json.dumps(shown, ensure_ascii=False, indent=1)}
    ]
    for label, path in images:
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        content += [{"type": "text", "text": f"{label}:"}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}]
    return {
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "question",
                "schema": {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False},
                "strict": True,
            },
        },
        "chat_template_kwargs": {"enable_thinking": mode == "thinking"},
    }


def parse_proposal(result: dict[str, Any], current: dict[str, str | None]) -> tuple[dict[str, str] | None, list[str], str | None]:
    """The proposed fields, warnings for the reviewer, and an error when nothing usable came back."""
    choice = result["choices"][0]
    if choice.get("finish_reason") == "length":
        return None, [], "the model ran out of tokens"
    try:
        data = json.loads(choice["message"]["content"])
    except (TypeError, json.JSONDecodeError) as exc:
        return None, [], f"invalid JSON: {exc}"
    labels = [field.split(":", 1)[1] for field in current if field.startswith("choice:")]
    returned = [str(item.get("label", "")).strip().rstrip(")") for item in data.get("choices", [])]
    if returned != labels:
        return None, [], f"option labels changed from {labels} to {returned}"
    proposal = {"passage": str(data["passage"]).strip()} if "passage" in current else {}
    stem = str(data["stem"]).strip()
    # The crop shows the printed question number; drop it if the model copied it into the stem.
    if not PRINTED_NUMBER.match(current["stem"] or ""):
        stem = PRINTED_NUMBER.sub("", stem, count=1)
    proposal["stem"] = stem
    for label, item in zip(labels, data["choices"]):
        proposal[f"choice:{label}"] = str(item["text"]).strip()
    # The book prints curly apostrophes and a one-character ellipsis; the model tends to write "'" and
    # "...". Restore the book's characters wherever the current text doesn't use the model's.
    for field, text in proposal.items():
        old = current[field] or ""
        if "'" in text and "'" not in old:
            text = text.replace("'", "’")
        if "..." in text and "..." not in old and "…" in old:
            text = text.replace("...", "…")
        proposal[field] = text
    warnings = [note for field, text in proposal.items() for note in text_changes(field, current[field], text)]
    return proposal, warnings, None


def store_proposals(
    connection: sqlite3.Connection, question_id: int, method: str, current: dict[str, str | None], proposal: dict[str, str]
) -> None:
    """Replace a question's pending proposals with the fields this proposal changes."""
    connection.execute("DELETE FROM question_repairs WHERE question_id = ? AND state = 'proposed'", (question_id,))
    connection.executemany(
        """
        INSERT INTO question_repairs (question_id, field, old_text, new_text, state, method, created_at)
        VALUES (?, ?, ?, ?, 'proposed', ?, ?)
        """,
        [
            (question_id, field, current[field], text, method, utc_now())
            for field, text in proposal.items()
            if text != (current[field] or "")
        ],
    )


def reparse(args: argparse.Namespace, connection: sqlite3.Connection, method: str, candidates: list[int]) -> int:
    """Rebuild proposals from the stored answers with the current parsing rules, without asking the model again."""
    wanted = set(candidates)
    stored = connection.execute(
        "SELECT question_id, response_json FROM repair_transcriptions WHERE method = ? AND response_json IS NOT NULL", (method,)
    ).fetchall()
    count = failures = 0
    with connection:
        for row in stored:
            if row["question_id"] not in wanted:
                continue
            current = current_text(connection, row["question_id"])
            proposal, warnings, error = parse_proposal(json.loads(row["response_json"]), current)
            connection.execute(
                "UPDATE repair_transcriptions SET proposal_json = ?, warnings_json = ?, error = ? WHERE question_id = ? AND method = ?",
                (
                    json.dumps(proposal, ensure_ascii=False) if proposal else None,
                    json.dumps(warnings, ensure_ascii=False),
                    error,
                    row["question_id"],
                    method,
                ),
            )
            if args.propose and proposal:
                store_proposals(connection, row["question_id"], method, current, proposal)
            count += 1
            failures += error is not None
    print(f"{method}: re-parsed {count} stored answers, {failures} unusable")
    return 0


def transcribe(args: argparse.Namespace) -> int:
    method = f"{args.model}/{args.mode}"
    connection = connect(args.v2)
    pdf = source_pdf(connection, args.v2)
    rows = audit_questions.audit(args.v2, RESULTS, V1)
    candidates = [row["question_id"] for row in rows if row["candidate"] or args.all]
    if args.question:
        unknown = sorted(set(args.question) - {row["question_id"] for row in rows})
        if unknown:
            raise ValueError(f"not benchmark questions: {unknown}")
        candidates = list(args.question)
    if args.reparse:
        return reparse(args, connection, method, candidates)
    done = {row[0] for row in connection.execute("SELECT question_id FROM repair_transcriptions WHERE method = ?", (method,))}
    pending = [question_id for question_id in candidates if args.force or question_id not in done]
    if args.limit is not None:
        pending = pending[: args.limit]
    print(f"{method}: {len(candidates)} candidates, {len(pending)} to transcribe", flush=True)
    cache: dict[int, tuple[int, int]] = {}
    jobs = []
    for question_id in pending:
        images = question_images(connection, pdf, args.work, question_id, cache)
        current = current_text(connection, question_id)
        max_tokens = args.max_tokens or (8192 if args.mode == "thinking" else 2048)
        jobs.append((question_id, images, current, transcription_request(args.model, args.mode, max_tokens, current, images)))

    def run(job: tuple) -> tuple[int, list, dict, dict | None, str | None, float]:
        question_id, images, current, payload = job
        started = time.monotonic()
        try:
            result, _ = bo.post_json(
                f"{args.endpoint.rstrip('/')}/v1/chat/completions",
                payload,
                {"Content-Type": "application/json"},
                args.timeout,
                None,
                "vision server",
            )
            return question_id, images, current, result, None, time.monotonic() - started
        except RuntimeError as exc:
            return question_id, images, current, None, str(exc), time.monotonic() - started

    failures = 0
    with futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for count, future in enumerate(futures.as_completed([pool.submit(run, job) for job in jobs]), 1):
            question_id, images, current, result, error, seconds = future.result()
            proposal, warnings = None, []
            if result is not None:
                proposal, warnings, error = parse_proposal(result, current)
            failures += error is not None
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO repair_transcriptions
                        (question_id, method, images_json, proposal_json, warnings_json, error, response_json, seconds, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        question_id,
                        method,
                        json.dumps([str(path.relative_to(args.work)) for _, path in images]),
                        json.dumps(proposal, ensure_ascii=False) if proposal else None,
                        json.dumps(warnings, ensure_ascii=False),
                        error,
                        json.dumps(result, ensure_ascii=False) if result is not None else None,
                        round(seconds, 2),
                        utc_now(),
                    ),
                )
                if args.propose and proposal:
                    store_proposals(connection, question_id, method, current, proposal)
            note = f"error: {error}" if error else (f"{len(warnings)} warning(s)" if warnings else "ok")
            print(f"[{count}/{len(jobs)}] question {question_id}: {note} ({seconds:.0f} s)", flush=True)
    print(f"Done: {len(jobs) - failures} transcribed, {failures} failed", flush=True)
    return 1 if failures else 0


# ---------------------------------------------------------------- review sheet


def excluded_questions(connection: sqlite3.Connection, eligible: set[int]) -> dict[int, str]:
    reasons = {}
    for row in connection.execute("SELECT question_id, complete, answer FROM benchmark_questions"):
        question_id = int(row["question_id"])
        if question_id in eligible:
            continue
        reasons[question_id] = (
            "incomplete" if not row["complete"] else "no answer key" if not str(row["answer"] or "").strip() else "malformed options"
        )
    return reasons


def sheet(args: argparse.Namespace) -> int:
    connection = connect(args.v2, readonly=True)
    pdf = source_pdf(connection, args.v2)
    reference_data = args.reference_data.resolve()
    rows = audit_questions.audit(args.v2, RESULTS, reference_data)
    by_id = {row["question_id"]: row for row in rows}
    reference = (
        audit_questions.reference_answers(RESULTS, reference_data) if audit_questions.shares_questions(args.v2, reference_data) else {}
    )
    transcriptions: dict[tuple[int, str], sqlite3.Row] = {
        (row["question_id"], row["method"]): row for row in connection.execute("SELECT * FROM repair_transcriptions")
    }
    meta = {
        int(row["question_id"]): row
        for row in connection.execute(
            """
            SELECT b.question_id, b.unit_number, b.unit_title, b.question_number, b.source_page_start, b.answer,
                   b.status, b.status_note, q.answer_source_page, s.source_page_end AS section_end
            FROM benchmark_questions b
            JOIN questions q ON q.id = b.question_id
            JOIN sections s ON s.id = q.section_id
            """
        )
    }
    # Every question transcribed for review is checked, whether or not the audit flags it.
    transcribed = {question_id for question_id, method in transcriptions if method in (args.primary, args.alternative)}
    candidates = [row["question_id"] for row in rows if row["candidate"] or row["question_id"] in transcribed]
    reviewed = set(candidates)
    keys = [row["question_id"] for row in rows if row["suspect_key"] and row["question_id"] not in reviewed]
    rng = random.Random(args.seed)
    units: dict[str, list[int]] = {}
    for row in rows:
        if row["question_id"] not in reviewed and not row["suspect_key"]:
            units.setdefault(row["unit"], []).append(row["question_id"])
    spot = sorted(
        question_id
        for unit_rows in units.values()
        for question_id in rng.sample(unit_rows, min(args.spot_per_unit, len(unit_rows)))
    )
    excluded = excluded_questions(connection, set(by_id))
    blind = blind_choices(args.blind_answers) if args.blind_answers else {}
    cache: dict[int, tuple[int, int]] = {}

    def proposal(question_id: int, method: str) -> tuple[dict | None, list[str], str | None]:
        row = transcriptions.get((question_id, method))
        if row is None:
            return None, [], None
        return (json.loads(row["proposal_json"]) if row["proposal_json"] else None), json.loads(row["warnings_json"]), row["error"]

    items = []
    sections = (("repair", candidates), ("key", keys), ("spot", spot), ("excluded", sorted(excluded)))
    if args.question:
        unknown = sorted(set(args.question) - set(by_id))
        if unknown:
            raise ValueError(f"not benchmark questions: {unknown}")
        sections = (
            ("key", [question for question in args.question if args.as_keys or by_id[question]["suspect_key"]]),
            ("repair", [question for question in args.question if not args.as_keys and not by_id[question]["suspect_key"]]),
        )
    for kind, question_ids in sections:
        for question_id in question_ids:
            info = meta[question_id]
            images = [str(path.relative_to(args.work)) for _, path in question_images(connection, pdf, args.work, question_id, cache)]
            bands = []
            if kind == "key" and info["answer_source_page"]:
                bands = [info["answer_source_page"]]
            elif kind == "excluded":
                bands = sorted({info["answer_source_page"] or info["source_page_start"], info["section_end"]})
            for page in bands:
                images.append(str(answer_band(pdf, page, args.work, cache).relative_to(args.work)))
            render_page(pdf, info["source_page_start"], args.work)
            primary, warnings, error = proposal(question_id, args.primary)
            alternative, alternative_warnings, _ = proposal(question_id, args.alternative)
            if primary is None and alternative is not None:
                # Thinking failed (for example, it ran out of tokens): review the other transcription.
                error = (
                    f"Thinking transcription failed ({error or 'no answer'}): the proposal is the one made without "
                    "thinking, and there is no second transcription to compare it with"
                )
                primary, alternative, warnings = alternative, None, alternative_warnings
            elif error:
                error = f"Transcription failed ({error}): correct the current text by hand"
            row = by_id.get(question_id)
            reference_picks = {
                name: {"answer": answers.get(question_id, (None, None))[0], "confidence": answers.get(question_id, (None, None))[1]}
                for name, answers in reference.items()
            }
            items.append(
                {
                    "id": question_id,
                    "kind": kind,
                    "unit": f"{info['unit_number']}. {info['unit_title']}" if info["unit_number"] else info["unit_title"],
                    "number": info["question_number"],
                    "page": info["source_page_start"],
                    "pageImage": f"pages/page-{info['source_page_start']:04d}.jpg",
                    "key": info["answer"],
                    "answers": (
                        {"Blind answer": {"answer": blind[question_id], "confidence": None}} if question_id in blind else {}
                    ) | reference_picks,
                    "flags": [flag for flag in audit_questions.FLAGS if row and row[flag]],
                    "reason": excluded.get(question_id),
                    "warnings": [warning for warning in warnings if not warning.startswith("rejoins")],
                    "notes": [warning for warning in warnings if warning.startswith("rejoins")],
                    "error": error,
                    "images": images,
                    "current": current_text(connection, question_id),
                    "proposal": primary,
                    "alternative": alternative,
                    "status": info["status"],
                    "statusNote": info["status_note"],
                }
            )

    def priority(item: dict[str, Any]) -> tuple[int, int, int]:
        """Re-transcriptions most likely to need edits come first: failures, then disagreements and warnings."""
        if item["kind"] != "repair":
            return (1, 0, 0)
        if item["error"] or item["proposal"] is None:
            return (0, 0, item["id"])
        doubtful = bool(item["warnings"]) or (item["alternative"] is not None and item["alternative"] != item["proposal"])
        return (0, 1 if doubtful else 2, item["id"])

    items.sort(key=priority)  # stable: the other sections keep their order

    def relative(path: Path) -> str:
        return str(path.relative_to(HERE)) if path.is_relative_to(HERE) else str(path)

    options = "" if (args.v2, args.work) == (V2, WORK) else f" --v2 {relative(args.v2)} --work {relative(args.work)}"
    command = f"./repair_questions.py{options} apply decisions-{args.v2.stem}.json"
    page = (
        REVIEW_HTML.replace("__DATASET__", json.dumps(dataset_label(connection, args.v2)))
        .replace("__APPLY__", html.escape(command))
        .replace("__ITEMS__", json.dumps(items, ensure_ascii=False).replace("</", "<\\/"))
    )
    args.work.mkdir(parents=True, exist_ok=True)
    out = args.work / "review.html"
    out.write_text(page, encoding="utf-8")
    counts = {kind: sum(item["kind"] == kind for item in items) for kind in ("repair", "key", "spot", "excluded")}
    print(f"Wrote {out}: {counts}")
    return 0


# ---------------------------------------------------------------- blind key check

# An answer-key strip entry such as "7-E"; three or more on one row are the page's answer-key strip.
KEY_STRIP_ENTRY = re.compile(r"\d{1,3}-[A-E]")
BLIND_GAP = 0.004  # share of the page height kept under a blind crop's last line, and above an answer-key strip


def page_words(pdf: Path, page: int, cache: dict[int, list[tuple[float, float, float, float, str]]]) -> list[tuple[float, float, float, float, str]]:
    """The words of a page's text layer: left, top, right and bottom as shares of the crop box, and text."""
    if page not in cache:
        layout = subprocess.run(
            ["pdftotext", "-f", str(page), "-l", str(page), "-bbox-layout", "-cropbox", str(pdf), "-"],
            capture_output=True, text=True, check=False,
        )
        if layout.returncode != 0:
            raise RuntimeError(f"pdftotext failed on page {page}: {layout.stderr.strip()}")
        width, height = (float(value) for value in re.search(r'<page width="([\d.]+)" height="([\d.]+)"', layout.stdout).groups())
        cache[page] = [
            (float(left) / width, float(top) / height, float(right) / width, float(bottom) / height, word)
            for left, top, right, bottom, word in re.findall(
                r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', layout.stdout
            )
        ]
    return cache[page]


def key_strip_top(words: list[tuple[float, float, float, float, str]]) -> float | None:
    """Where a page's answer-key strip starts, as a share of the crop box's height; None when the page
    prints no answer key."""
    tops = [top for _, top, _, _, word in words if KEY_STRIP_ENTRY.fullmatch(word)]
    rows: dict[float, int] = {}
    for top in tops:
        rows[round(top, 2)] = rows.get(round(top, 2), 0) + 1
    strip = [top for top in tops if rows[round(top, 2)] >= 3]
    return min(strip) if strip else None


def blind_images(connection: sqlite3.Connection, pdf: Path, work: Path, question_id: int, cache: dict, words: dict) -> list[str]:
    """Crops of a question and of its shared passage that show nothing of an answer-key strip on their page.

    A crop that would reach a strip ends just under the last line of text it holds above the strip, so
    the strip's frame stays out too."""
    row = connection.execute(
        """
        SELECT q.source_page_start, q.bbox_json, p.source_page AS passage_page, p.bbox_json AS passage_bbox
        FROM questions q LEFT JOIN passages p ON p.id = q.passage_id WHERE q.id = ?
        """,
        (question_id,),
    ).fetchone()
    regions = []
    if row["passage_bbox"]:
        regions.append((row["passage_page"], json.loads(row["passage_bbox"]), f"blind-q{question_id}-passage"))
    regions.append((row["source_page_start"], json.loads(row["bbox_json"]), f"blind-q{question_id}"))
    images = []
    for page, box, name in regions:
        on_page = page_words(pdf, page, words)
        strip = key_strip_top(on_page)
        # render_region pads the box by CROP_PADDING on every side.
        if strip is not None and box[3] + CROP_PADDING > strip - BLIND_GAP:
            text_bottom = max(
                (bottom for left, top, right, bottom, _ in on_page if top >= box[1] and bottom <= strip and right > box[0] and left < box[2]),
                default=None,
            )
            if text_bottom is None:
                raise ValueError(f"question {question_id} has no text above the answer-key strip on page {page}")
            box = [box[0], box[1], box[2], min(text_bottom + BLIND_GAP, strip - BLIND_GAP) - CROP_PADDING]
        images.append(str(render_region(pdf, page, box, work / "crops" / f"{name}.png", cache).relative_to(work)))
    return images


def blind_choices(path: Path) -> dict[int, str]:
    """Each question's answer in a file downloaded from the blind page: a letter or 'unsure'."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("kind") != "blind-check":
        raise ValueError(f"{path.name} is not an answers file from the blind page")
    return {int(question): answer["answer"] for question, answer in document.get("answers", {}).items() if answer.get("answer")}


def blind(args: argparse.Namespace) -> int:
    """A random sample of the scored questions no person has reviewed, in proportion to the units' sizes,
    on a page that shows each as printed, without its key or any model's answer. With --disputed, every
    excluded and suspect question instead, for a reviewer who has seen no model's answers."""
    connection = connect(args.v2, readonly=True)
    pdf = source_pdf(connection, args.v2)
    if args.disputed:
        rows = connection.execute(
            """
            SELECT question_id, unit_number, unit_title FROM benchmark_questions WHERE status IN ('excluded', 'suspect')
            ORDER BY CAST(unit_number AS INTEGER), source_page_start, question_id
            """
        ).fetchall()
        if not rows:
            raise ValueError("no question is excluded or suspect")
        chosen = {row["question_id"] for row in rows}
        work, label = args.work / "blind-disputed", "disputed"
        described = f"the {len(rows)} excluded and suspect questions"
    else:
        scored = {question.question_id for question in bo.load_questions(args.v2, None, None, None, 0).questions}
        rows = [
            row
            for row in connection.execute(
                """
                SELECT question_id, unit_number, unit_title FROM benchmark_questions WHERE status IS NULL
                ORDER BY CAST(unit_number AS INTEGER), source_page_start, question_id
                """
            )
            if row["question_id"] in scored
        ]
        if args.count < 1 or args.count > len(rows):
            raise ValueError(f"--count must be between 1 and {len(rows)}, the never-reviewed questions")
        units: dict[str, list[int]] = {}
        for row in rows:
            units.setdefault(f"{row['unit_number']}. {row['unit_title']}", []).append(row["question_id"])
        # Largest-remainder allocation: each unit gets its share of the sample, rounded so they add up.
        quotas = {unit: args.count * len(ids) / len(rows) for unit, ids in units.items()}
        counts = {unit: int(quota) for unit, quota in quotas.items()}
        for unit in sorted(quotas, key=lambda unit: (counts[unit] - quotas[unit], unit))[: args.count - sum(counts.values())]:
            counts[unit] += 1
        rng = random.Random(args.seed)
        chosen = {question for unit, ids in units.items() for question in rng.sample(ids, counts[unit])}
        work, label = args.work / "blind", args.seed
        described = f"{len(chosen)} of the {len(rows)} never-reviewed questions (seed {args.seed})"
    cache: dict[int, tuple[int, int]] = {}
    words: dict[int, list[tuple[float, float, float, float, str]]] = {}
    items = [
        {
            "id": row["question_id"],
            "unit": f"{row['unit_number']}. {row['unit_title']}",
            "images": blind_images(connection, pdf, work, row["question_id"], cache, words),
            "text": current_text(connection, row["question_id"]),
        }
        for row in rows
        if row["question_id"] in chosen
    ]
    options = "" if args.v2 == V2 else f" --v2 {args.v2}"
    options += "" if args.work == WORK else f" --work {args.work}"
    download = f"{work.name}-answers.json"
    sample = {"seed": label, "questions": [item["id"] for item in items]}
    page = (
        BLIND_HTML.replace("__DATASET__", json.dumps(dataset_label(connection, args.v2)))
        .replace("__COMPARE__", html.escape(f"./repair_questions.py{options} blind-compare {download}"))
        .replace("__DOWNLOAD__", json.dumps(download))
        .replace("__SAMPLE__", json.dumps(sample))
        .replace("__ITEMS__", json.dumps(items, ensure_ascii=False).replace("</", "<\\/"))
    )
    work.mkdir(parents=True, exist_ok=True)
    out = work / "review.html"
    out.write_text(page, encoding="utf-8")
    print(f"Wrote {out}: {described}")
    return 0


def blind_compare(args: argparse.Namespace) -> int:
    """Compare the blind answers with the key; the disagreements and the unsure answers get a second look
    on the key-audit page, beside the blind answer."""
    document = json.loads(args.answers.read_text(encoding="utf-8"))
    connection = connect(args.v2, readonly=True)
    label = dataset_label(connection, args.v2)
    if document.get("dataset") != label:
        raise ValueError(f"{args.answers.name} holds answers for {document.get('dataset')}, not {label}")
    choices = blind_choices(args.answers)
    keys = {int(row["question_id"]): row["answer"] for row in connection.execute("SELECT question_id, answer FROM benchmark_questions")}
    groups: dict[str, list[int]] = {"agree with the key": [], "disagree": [], "unsure": [], "unanswered": []}
    for question in document["questions"]:
        choice = choices.get(question)
        if choice is None:
            groups["unanswered"].append(question)
        elif choice == "unsure":
            groups["unsure"].append(question)
        else:
            groups["agree with the key" if choice == keys[question] else "disagree"].append(question)
    print(", ".join(f"{len(questions)} {name}" for name, questions in groups.items()))
    for question in groups["disagree"]:
        print(f"  question {question}: blind answer {choices[question]}, key {keys[question]}")
    if groups["unanswered"]:
        print("Answer every question on the blind page first.", file=sys.stderr)
        return 1
    second = groups["disagree"] + groups["unsure"]
    if not second:
        print("Every blind answer matches the key: nothing needs a second look.")
        return 0
    return sheet(
        argparse.Namespace(
            v2=args.v2, work=args.work / ("blind-disputed" if document.get("seed") == "disputed" else "blind") / "second-look",
            primary=PRIMARY_METHOD, alternative=ALTERNATIVE_METHOD,
            spot_per_unit=0, seed=0, question=second, as_keys=True, reference_data=V1, blind_answers=args.answers,
        )
    )


# ---------------------------------------------------------------- apply


def dataset_label(connection: sqlite3.Connection, path: Path) -> str:
    """The bank's name and creation time; the review page stores decisions under it and writes it into them."""
    created = connection.execute("SELECT value FROM dataset_info WHERE key = 'created_at'").fetchone()[0]
    return f"{path.name}@{created}"


def apply(args: argparse.Namespace) -> int:
    decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
    items = decisions.get("items", {})
    connection = connect(args.v2)
    if decisions.get("dataset") != dataset_label(connection, args.v2):
        raise ValueError(
            f"{args.decisions.name} holds decisions for {decisions.get('dataset')}, not {dataset_label(connection, args.v2)}"
        )
    now = utc_now()
    summary = {"statuses": 0, "fields": 0, "keys": 0, "completed": 0, "skipped": 0}
    passages: dict[int, tuple[int, str]] = {}
    with connection:
        for question_key, decision in items.items():
            question_id = int(question_key)
            status = decision.get("status")
            if status not in STATUSES:
                summary["skipped"] += 1
                continue
            current = current_text(connection, question_id)
            proposals = {
                row["field"]: row
                for row in connection.execute(
                    "SELECT id, field, new_text FROM question_repairs WHERE question_id = ? AND state = 'proposed'", (question_id,)
                ).fetchall()
            }
            for field, text in (decision.get("fields") or {}).items():
                if field not in current:
                    raise ValueError(f"question {question_id} has no field {field!r}")
                text = text.replace("\r\n", "\n").strip()
                if field == "passage":
                    passage_id = connection.execute("SELECT passage_id FROM questions WHERE id = ?", (question_id,)).fetchone()[0]
                    earlier = passages.get(passage_id)
                    if earlier and earlier[1] != text:
                        raise ValueError(f"questions {earlier[0]} and {question_id} disagree on their shared passage")
                    passages[passage_id] = (question_id, text)
                if text == (current[field] or ""):
                    continue
                write_field(connection, question_id, field, text)
                proposed = proposals.pop(field, None)
                if proposed is not None and proposed["new_text"] == text:
                    connection.execute(
                        "UPDATE question_repairs SET state = 'applied', decided_at = ? WHERE id = ?", (now, proposed["id"])
                    )
                else:
                    if proposed is not None:
                        connection.execute(
                            "UPDATE question_repairs SET state = 'rejected', decided_at = ? WHERE id = ?", (now, proposed["id"])
                        )
                    connection.execute(
                        """
                        INSERT INTO question_repairs (question_id, field, old_text, new_text, state, method, created_at, decided_at)
                        VALUES (?, ?, ?, ?, 'applied', 'review', ?, ?)
                        """,
                        (question_id, field, current[field], text, now, now),
                    )
                summary["fields"] += 1
            key = str(decision.get("key") or "").strip().upper()
            old_key = connection.execute("SELECT answer FROM questions WHERE id = ?", (question_id,)).fetchone()[0]
            if key and key != (old_key or ""):
                labels = [field.split(":", 1)[1] for field in current if field.startswith("choice:")]
                if key not in labels:
                    raise ValueError(f"question {question_id}: key {key!r} is not one of {labels}")
                connection.execute("UPDATE questions SET answer = ? WHERE id = ?", (key, question_id))
                connection.execute(
                    """
                    INSERT INTO question_repairs (question_id, field, old_text, new_text, state, method, created_at, decided_at)
                    VALUES (?, 'answer', ?, ?, 'applied', 'review', ?, ?)
                    """,
                    (question_id, old_key, key, now, now),
                )
                summary["keys"] += 1
            # Proposals left over were not written now: kept if the text already matches (a shared
            # passage written through another question), otherwise rejected.
            final = current_text(connection, question_id)
            for field, proposed in proposals.items():
                state = "applied" if final.get(field) == proposed["new_text"] else "rejected"
                connection.execute("UPDATE question_repairs SET state = ?, decided_at = ? WHERE id = ?", (state, now, proposed["id"]))
            # A question checked against its page and kept is complete, whatever the extractor decided.
            if status != "excluded" and not connection.execute("SELECT complete FROM questions WHERE id = ?", (question_id,)).fetchone()[0]:
                connection.execute("UPDATE questions SET complete = 1 WHERE id = ?", (question_id,))
                connection.execute(
                    """
                    INSERT INTO question_repairs (question_id, field, old_text, new_text, state, method, created_at, decided_at)
                    VALUES (?, 'complete', '0', '1', 'applied', 'review', ?, ?)
                    """,
                    (question_id, now, now),
                )
                summary["completed"] += 1
            connection.execute(
                """
                INSERT INTO question_status (question_id, status, note, checked_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(question_id) DO UPDATE SET status = excluded.status, note = excluded.note, checked_at = excluded.checked_at
                """,
                (question_id, status, (decision.get("note") or "").strip() or None, now),
            )
            summary["statuses"] += 1
    counts = dict(connection.execute("SELECT status, count(*) FROM question_status GROUP BY status").fetchall())
    print(
        f"Applied {summary['statuses']} decisions: {summary['fields']} text fields and {summary['keys']} keys changed, "
        f"{summary['completed']} incomplete questions marked complete; {summary['skipped']} items without a status skipped. "
        f"Statuses now: {counts}"
    )
    return 0


REVIEW_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>Question review</title>
<style>
body { font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; background: #f5f5f4; color: #1c1917; }
header { position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
  padding: 10px 16px; background: #fff; border-bottom: 1px solid #d6d3d1; }
header .progress { color: #57534e; }
main { max-width: 1500px; margin: 0 auto; padding: 16px; }
.help { background: #fff; border: 1px solid #d6d3d1; border-radius: 8px; padding: 8px 16px; margin-bottom: 16px; }
.card { background: #fff; border: 1px solid #d6d3d1; border-left: 6px solid #f59e0b; border-radius: 8px; margin: 0 0 16px; padding: 12px 16px; }
.card.decided { border-left-color: #16a34a; }
.card h2 { font-size: 16px; margin: 0 0 4px; }
.meta { color: #57534e; font-size: 13px; }
.chips span { display: inline-block; border-radius: 4px; padding: 0 6px; margin: 2px 4px 2px 0; font-size: 12px; background: #e7e5e4; }
.chips .warn { background: #fee2e2; color: #991b1b; }
.columns { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); gap: 16px; margin-top: 8px; }
.images img { display: block; max-width: 100%; border: 1px solid #e7e5e4; margin-bottom: 8px; }
.field { margin-bottom: 10px; }
.field > label { font-weight: 600; font-size: 13px; }
textarea { width: 100%; box-sizing: border-box; font: 14px/1.4 ui-monospace, Menlo, monospace; padding: 6px; }
.preview { font-size: 14px; padding: 4px 6px; background: #fafaf9; border-radius: 4px; }
.preview u { text-decoration: underline 2px; background: #fef9c3; }
.diff { font-size: 13px; color: #44403c; padding: 2px 6px; }
.diff del { background: #fecaca; } .diff ins { background: #bbf7d0; text-decoration: none; }
.controls { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; margin-top: 8px; padding-top: 8px; border-top: 1px solid #e7e5e4; }
.controls input[type=text] { min-width: 320px; }
button { font: inherit; padding: 2px 10px; }
.hidden { display: none; }
</style>
</head>
<body>
<header>
  <strong>Question review</strong>
  <label>Show <select id="kind">
    <option value="">everything</option>
    <option value="repair">re-transcriptions</option>
    <option value="key">suspect keys</option>
    <option value="spot">spot check</option>
    <option value="excluded">excluded questions</option>
  </select></label>
  <label><input type="checkbox" id="undecided"> only undecided</label>
  <span class="progress" id="progress"></span>
  <button id="download">Download decisions</button>
  <label>Load decisions <input type="file" id="load" accept="application/json"></label>
</header>
<main>
  <div class="help">
    Compare each question with its page crop. Edit the text until it matches the page, using <code>&lt;u&gt;…&lt;/u&gt;</code>
    for underlining and <code>(I)</code> right after a numbered word. The boxes start with the model's proposal; the
    <b>Reset</b> buttons put the proposal, the other transcription or the current text back in every box, replacing your
    edits, and ask first. Then choose a status:
    <b>verified</b> (text and key are right), <b>suspect</b> (kept, but something is doubtful: say what in the note) or
    <b>excluded</b> (not scored). Decisions are kept in this browser; download them and run
    <code>__APPLY__</code> with the downloaded file.
  </div>
  <div id="items"></div>
</main>
<script id="data" type="application/json">__ITEMS__</script>
<script>
const DATASET = __DATASET__;
const ITEMS = JSON.parse(document.getElementById('data').textContent);
const STORE = 'question-review:' + DATASET;
const KINDS = {repair: 'Re-transcription', key: 'Suspect key', spot: 'Spot check', excluded: 'Excluded question'};
// Audit flags: the label shown on a card, and the explanation shown on hover.
const FLAGS = {
  underline_missing: ['underlines missing', 'The question refers to underlined words, but the current text marks none.'],
  numbering_missing: ['numbers missing', 'The question refers to numbered words, marks or sentences, but the current text has no numerals next to them.'],
  numeral_in_word: ['numeral inside a word', 'A Roman numeral is stuck to a word in the current text, as in "sayfaII".'],
  hyphen_space: ['"word- word" split', 'A word is split as "word- word": a line-end break, or a dash the question means.'],
  suspect_key: ['key disputed', 'GPT-6 Astra (low), Opus 5.5 (low) and Sonnet 5.5 (high) all chose the same option, and it is not the key.'],
};
let decisions = JSON.parse(localStorage.getItem(STORE) || '{}');

const escapeHtml = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const preview = s => escapeHtml(s).replace(/&lt;u&gt;/g, '<u>').replace(/&lt;\/u&gt;/g, '</u>').replace(/\n/g, '<br>');

function diff(a, b) {
  const x = String(a ?? '').split(/(\s+)/), y = String(b ?? '').split(/(\s+)/);
  if (x.length * y.length > 250000) return '<em>too long to compare</em>';
  const dp = Array.from({length: x.length + 1}, () => new Uint32Array(y.length + 1));
  for (let i = x.length - 1; i >= 0; i--)
    for (let j = y.length - 1; j >= 0; j--)
      dp[i][j] = x[i] === y[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  let i = 0, j = 0, out = '';
  while (i < x.length && j < y.length) {
    if (x[i] === y[j]) { out += escapeHtml(x[i]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) out += '<del>' + escapeHtml(x[i++]) + '</del>';
    else out += '<ins>' + escapeHtml(y[j++]) + '</ins>';
  }
  while (i < x.length) out += '<del>' + escapeHtml(x[i++]) + '</del>';
  while (j < y.length) out += '<ins>' + escapeHtml(y[j++]) + '</ins>';
  return out.replace(/\n/g, '<br>');
}

const fieldLabel = f => f === 'stem' ? 'Question' : f === 'passage' ? 'Shared passage' : 'Option ' + f.split(':')[1];
// A question that already has a status in the database shows its applied text, not the proposal.
const initial = item => Object.fromEntries(Object.keys(item.current).map(f =>
  [f, ((item.status ? null : item.proposal) ?? item.current)[f] ?? '']));
const statusOf = item => decisions[item.id]?.status ?? item.status;

function save() {
  localStorage.setItem(STORE, JSON.stringify(decisions));
  const decided = ITEMS.filter(statusOf).length;
  document.getElementById('progress').textContent = `${decided} of ${ITEMS.length} decided`;
}

function record(card, item) {
  const fields = {};
  card.querySelectorAll('textarea[data-field]').forEach(t => { fields[t.dataset.field] = t.value; });
  const status = card.querySelector('input[type=radio]:checked')?.value ?? null;
  decisions[item.id] = {status, note: card.querySelector('.note').value, key: card.querySelector('.key').value, fields};
  card.classList.toggle('decided', Boolean(status));
  save();
}

function refreshField(card, item, field) {
  const text = card.querySelector(`textarea[data-field="${field}"]`).value;
  card.querySelector(`.preview[data-field="${field}"]`).innerHTML = preview(text);
  const changed = text !== (item.current[field] ?? '');
  card.querySelector(`.diff[data-field="${field}"]`).innerHTML = changed ? 'Change from the current text: ' + diff(item.current[field], text) : '';
}

function fill(card, item, source) {
  Object.keys(item.current).forEach(f => {
    card.querySelector(`textarea[data-field="${f}"]`).value = source[f] ?? '';
    refreshField(card, item, f);
  });
  record(card, item);
}

// The boxes hold edits when they match none of the texts the reset buttons put back.
function edited(card, item) {
  const values = Object.fromEntries([...card.querySelectorAll('textarea[data-field]')].map(t => [t.dataset.field, t.value]));
  return ![item.proposal, item.alternative, item.current].some(source =>
    source && Object.keys(item.current).every(f => (source[f] ?? '') === values[f]));
}

function render(item) {
  const saved = decisions[item.id] ?? (item.status ? {status: item.status, note: item.statusNote ?? ''} : {});
  const values = {...initial(item), ...(saved.fields ?? {})};
  const answers = Object.entries(item.answers).map(([name, a]) =>
    `${name}: ${a.answer ?? '–'}${a.confidence == null ? '' : ' (' + a.confidence.toFixed(2) + ')'}`).join(' · ');
  const chips = [...item.flags.map(f => `<span title="${escapeHtml(FLAGS[f]?.[1] ?? '')}">${escapeHtml(FLAGS[f]?.[0] ?? f)}</span>`),
    ...item.notes.map(n => `<span>${escapeHtml(n)}</span>`),
    ...item.warnings.map(w => `<span class="warn">${escapeHtml(w)}</span>`),
    ...(item.error ? [`<span class="warn">${escapeHtml(item.error)}</span>`] : []),
    ...(item.alternative && JSON.stringify(item.alternative) !== JSON.stringify(item.proposal)
      ? ['<span class="warn" title="“Reset to other transcription” puts the other one in the boxes.">the transcriptions with and without thinking differ</span>'] : []),
    ...(item.reason ? [`<span class="warn">${escapeHtml(item.reason)}</span>`] : [])].join('');
  const card = document.createElement('section');
  card.className = 'card' + (saved.status ? ' decided' : '');
  card.dataset.kind = item.kind;
  card.innerHTML = `
    <h2>${KINDS[item.kind]} · question ${item.id}</h2>
    <div class="meta">${escapeHtml(item.unit)} · page ${item.page}, question ${escapeHtml(item.number)} · key ${item.key ?? '–'} ·
      <a href="${item.pageImage}" target="_blank">full page</a><br>${escapeHtml(answers)}</div>
    <div class="chips">${chips}</div>
    <div class="columns">
      <div class="images">${item.images.map(src => `<a href="${src}" target="_blank"><img src="${src}" loading="lazy"></a>`).join('')}</div>
      <div>
        ${Object.keys(item.current).map(f => `
          <div class="field">
            <label>${fieldLabel(f)}</label>
            <textarea data-field="${f}" rows="${Math.min(12, Math.max(1, Math.ceil((values[f] ?? '').length / 90) + (values[f] ?? '').split('\n').length - 1))}">${escapeHtml(values[f])}</textarea>
            <div class="preview" data-field="${f}"></div>
            <div class="diff" data-field="${f}"></div>
          </div>`).join('')}
        <div class="resets">
          ${item.proposal ? '<button data-use="proposal" title="Replace the text in every box with the model\'s proposal">Reset to proposal</button>' : ''}
          ${item.alternative ? '<button data-use="alternative" title="Replace the text in every box with the transcription made without thinking">Reset to other transcription</button>' : ''}
          <button data-use="current" title="Replace the text in every box with the text the question bank has now">Reset to current text</button>
          <span class="meta">Edit the boxes directly; their text is what gets saved with the status.</span>
        </div>
      </div>
    </div>
    <div class="controls">
      ${['verified', 'suspect', 'excluded'].map(s =>
        `<label><input type="radio" name="status-${item.id}" value="${s}" ${saved.status === s ? 'checked' : ''}> ${s}</label>`).join('')}
      <label>Key <select class="key">${['', ...Object.keys(item.current).filter(f => f.startsWith('choice:')).map(f => f.split(':')[1])]
        .map(k => `<option value="${k}" ${(saved.key ?? item.key ?? '') === k ? 'selected' : ''}>${k || '–'}</option>`).join('')}</select></label>
      <label>Note <input type="text" class="note" value="${escapeHtml(saved.note ?? '')}"></label>
    </div>`;
  Object.keys(item.current).forEach(f => refreshField(card, item, f));
  card.addEventListener('input', event => {
    if (event.target.dataset.field) refreshField(card, item, event.target.dataset.field);
    record(card, item);
  });
  card.addEventListener('change', () => record(card, item));
  card.querySelectorAll('button[data-use]').forEach(button => button.addEventListener('click', () => {
    if (edited(card, item) && !confirm(`Replace your edits to question ${item.id}? They will be lost.`)) return;
    fill(card, item, button.dataset.use === 'current' ? item.current : item[button.dataset.use]);
  }));
  return card;
}

function applyFilter() {
  const kind = document.getElementById('kind').value, undecided = document.getElementById('undecided').checked;
  document.querySelectorAll('.card').forEach((card, index) => {
    const item = ITEMS[index];
    card.classList.toggle('hidden', (kind && item.kind !== kind) || (undecided && Boolean(statusOf(item))));
  });
}

const container = document.getElementById('items');
ITEMS.forEach(item => container.appendChild(render(item)));
document.getElementById('kind').addEventListener('change', applyFilter);
document.getElementById('undecided').addEventListener('change', applyFilter);
document.getElementById('download').addEventListener('click', () => {
  const blob = new Blob([JSON.stringify({version: 1, dataset: DATASET, exported_at: new Date().toISOString(), items: decisions}, null, 1)],
    {type: 'application/json'});
  const bank = DATASET.split('@')[0].replace(/\.sqlite$/, '');
  const link = Object.assign(document.createElement('a'), {href: URL.createObjectURL(blob), download: `decisions-${bank}.json`});
  link.click();
  URL.revokeObjectURL(link.href);
});
document.getElementById('load').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  const loaded = JSON.parse(await file.text());
  event.target.value = '';
  if (loaded.dataset !== DATASET) {
    alert(`${file.name} holds decisions for ${loaded.dataset}, not for this page (${DATASET}).`);
    return;
  }
  decisions = {...decisions, ...loaded.items};
  save();
  container.replaceChildren(...ITEMS.map(render));
  applyFilter();
});
save();
</script>
</body>
</html>
"""

BLIND_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>Blind key check</title>
<style>
body { font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; background: #f5f5f4; color: #1c1917; }
header { position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
  padding: 10px 16px; background: #fff; border-bottom: 1px solid #d6d3d1; }
header .progress { color: #57534e; }
main { max-width: 1000px; margin: 0 auto; padding: 16px; }
.help { background: #fff; border: 1px solid #d6d3d1; border-radius: 8px; padding: 8px 16px; margin-bottom: 16px; }
.card { background: #fff; border: 1px solid #d6d3d1; border-left: 6px solid #f59e0b; border-radius: 8px; margin: 0 0 16px; padding: 12px 16px; }
.card.answered { border-left-color: #16a34a; }
.card h2 { font-size: 16px; margin: 0 0 8px; }
.meta { color: #57534e; font-size: 13px; font-weight: normal; }
.images img { display: block; max-width: 100%; border: 1px solid #e7e5e4; margin-bottom: 8px; }
details { margin: 0 0 8px; font-size: 14px; color: #44403c; }
.text p { margin: 4px 0; }
.text u { text-decoration: underline 2px; background: #fef9c3; }
.choices { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; padding-top: 8px; border-top: 1px solid #e7e5e4; }
.choices label { cursor: pointer; }
.choices input[type=text] { min-width: 300px; }
button { font: inherit; padding: 2px 10px; }
.hidden { display: none; }
</style>
</head>
<body>
<header>
  <strong>Blind key check</strong>
  <label><input type="checkbox" id="unanswered"> only unanswered</label>
  <span class="progress" id="progress"></span>
  <button id="download">Download answers</button>
  <label>Load answers <input type="file" id="load" accept="application/json"></label>
</header>
<main>
  <div class="help">
    Answer each question as in the exam. The book's answer key and the models' answers are not shown; the pictures stop
    above the answer-key strip that some pages print. Choose an option, or <b>unsure</b> if you cannot decide, and use the
    note if a question or its picture looks wrong. Your answers stay in this browser, so you can stop and come back
    later. When every question has an answer, download them and run <code>__COMPARE__</code> with the file.
  </div>
  <div id="items"></div>
</main>
<script id="data" type="application/json">__ITEMS__</script>
<script>
const DATASET = __DATASET__;
const SAMPLE = __SAMPLE__;
const ITEMS = JSON.parse(document.getElementById('data').textContent);
const STORE = `blind-check:${DATASET}:${SAMPLE.seed}:${SAMPLE.questions.join(',')}`;
let answers = JSON.parse(localStorage.getItem(STORE) || '{}');

const escapeHtml = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const preview = s => escapeHtml(s).replace(/&lt;u&gt;/g, '<u>').replace(/&lt;\/u&gt;/g, '</u>').replace(/\n/g, '<br>');
const fieldLabel = f => f === 'stem' ? 'Question' : f === 'passage' ? 'Passage' : f.split(':')[1] + ')';
const answered = item => Boolean(answers[item.id]?.answer);

function save() {
  localStorage.setItem(STORE, JSON.stringify(answers));
  document.getElementById('progress').textContent = `${ITEMS.filter(answered).length} of ${ITEMS.length} answered`;
}

function render(item, index) {
  const saved = answers[item.id] ?? {};
  const options = Object.keys(item.text).filter(f => f.startsWith('choice:')).map(f => f.split(':')[1]);
  const card = document.createElement('section');
  card.className = 'card' + (saved.answer ? ' answered' : '');
  card.innerHTML = `
    <h2>Question ${index + 1} of ${ITEMS.length} <span class="meta">· ${escapeHtml(item.unit)}</span></h2>
    <div class="images">${item.images.map(src => `<img src="${src}" alt="The question as printed">`).join('')}</div>
    <details><summary>The text the models read</summary><div class="text">
      ${Object.entries(item.text).filter(([, text]) => text).map(([f, text]) => `<p><b>${fieldLabel(f)}</b> ${preview(text)}</p>`).join('')}
    </div></details>
    <div class="choices">
      ${[...options, 'unsure'].map(o =>
        `<label><input type="radio" name="answer-${item.id}" value="${o}" ${saved.answer === o ? 'checked' : ''}> ${o}</label>`).join('')}
      <label>Note <input type="text" class="note" value="${escapeHtml(saved.note ?? '')}"></label>
    </div>`;
  const record = () => {
    const answer = card.querySelector('input[type=radio]:checked')?.value ?? null;
    answers[item.id] = {answer, note: card.querySelector('.note').value};
    card.classList.toggle('answered', Boolean(answer));
    save();
  };
  card.addEventListener('change', record);
  card.addEventListener('input', record);
  return card;
}

function applyFilter() {
  const only = document.getElementById('unanswered').checked;
  document.querySelectorAll('.card').forEach((card, index) => card.classList.toggle('hidden', only && answered(ITEMS[index])));
}

const container = document.getElementById('items');
ITEMS.forEach((item, index) => container.appendChild(render(item, index)));
document.getElementById('unanswered').addEventListener('change', applyFilter);
document.getElementById('download').addEventListener('click', () => {
  const missing = ITEMS.length - ITEMS.filter(answered).length;
  if (missing && !confirm(`${missing} questions have no answer yet. Download anyway?`)) return;
  const document_ = {version: 1, kind: 'blind-check', dataset: DATASET, seed: SAMPLE.seed, questions: SAMPLE.questions,
    exported_at: new Date().toISOString(), answers};
  const blob = new Blob([JSON.stringify(document_, null, 1)], {type: 'application/json'});
  const link = Object.assign(document.createElement('a'), {href: URL.createObjectURL(blob), download: __DOWNLOAD__});
  link.click();
  URL.revokeObjectURL(link.href);
});
document.getElementById('load').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  const loaded = JSON.parse(await file.text());
  event.target.value = '';
  if (loaded.kind !== 'blind-check' || loaded.dataset !== DATASET || loaded.questions?.join(',') !== SAMPLE.questions.join(',')) {
    alert(`${file.name} holds answers for another sample, not for this page.`);
    return;
  }
  answers = {...answers, ...loaded.answers};
  save();
  container.replaceChildren(...ITEMS.map(render));
  applyFilter();
});
save();
</script>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    args.v2 = args.v2.resolve()
    args.work = args.work.resolve()
    commands = {"init": init, "transcribe": transcribe, "sheet": sheet, "apply": apply, "blind": blind, "blind-compare": blind_compare}
    try:
        return commands[args.command](args)
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
