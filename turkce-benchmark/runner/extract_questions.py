#!/usr/bin/env python3
"""Extract a PDF question bank into SQLite with an OpenAI-compatible vision LLM."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import mimetypes
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
LOG = logging.getLogger("question_extractor")

SCHEMA_SQL = r"""
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    page_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extraction_runs (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    model TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    config_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    section_key TEXT NOT NULL,
    unit_number TEXT,
    unit_title TEXT,
    title TEXT,
    subsection TEXT,
    test_type TEXT,
    test_number TEXT,
    source_page_start INTEGER NOT NULL,
    source_page_end INTEGER,
    raw_json TEXT NOT NULL,
    created_run_id INTEGER REFERENCES extraction_runs(id),
    UNIQUE(source_id, section_key)
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    page_number INTEGER NOT NULL,
    run_id INTEGER REFERENCES extraction_runs(id),
    status TEXT NOT NULL,
    rendered_image TEXT,
    rendered_sha256 TEXT,
    answer_band_image TEXT,
    pdf_text TEXT,
    active_section_before_id INTEGER REFERENCES sections(id),
    active_section_after_id INTEGER REFERENCES sections(id),
    request_json TEXT,
    raw_response TEXT,
    parsed_json TEXT,
    error TEXT,
    elapsed_seconds REAL,
    extracted_at TEXT,
    UNIQUE(source_id, page_number)
);

CREATE TABLE IF NOT EXISTS page_section_events (
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    event_order INTEGER NOT NULL,
    section_id INTEGER NOT NULL REFERENCES sections(id),
    local_ref TEXT NOT NULL,
    PRIMARY KEY(page_id, event_order)
);

CREATE TABLE IF NOT EXISTS passages (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    section_id INTEGER REFERENCES sections(id),
    source_page INTEGER NOT NULL,
    local_ref TEXT NOT NULL,
    text TEXT,
    markdown TEXT,
    description TEXT,
    bbox_json TEXT,
    raw_json TEXT NOT NULL,
    UNIQUE(source_id, source_page, local_ref)
);

CREATE TABLE IF NOT EXISTS visuals (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    section_id INTEGER REFERENCES sections(id),
    source_page INTEGER NOT NULL,
    local_ref TEXT NOT NULL,
    kind TEXT NOT NULL,
    description TEXT NOT NULL,
    markdown TEXT,
    dot TEXT,
    bbox_json TEXT,
    raw_json TEXT NOT NULL,
    UNIQUE(source_id, source_page, local_ref)
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    section_id INTEGER NOT NULL REFERENCES sections(id),
    source_page_start INTEGER NOT NULL,
    source_page_end INTEGER NOT NULL,
    printed_number TEXT NOT NULL,
    stem TEXT NOT NULL,
    question_type TEXT,
    passage_id INTEGER REFERENCES passages(id),
    complete INTEGER NOT NULL DEFAULT 1,
    bbox_json TEXT,
    confidence REAL,
    answer TEXT,
    answer_source_page INTEGER,
    answer_confidence REAL,
    raw_json TEXT NOT NULL,
    UNIQUE(source_id, section_id, printed_number)
);

CREATE TABLE IF NOT EXISTS choices (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    text TEXT,
    bbox_json TEXT,
    raw_json TEXT NOT NULL,
    UNIQUE(question_id, label)
);

CREATE TABLE IF NOT EXISTS question_visuals (
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    visual_id INTEGER NOT NULL REFERENCES visuals(id),
    PRIMARY KEY(question_id, visual_id)
);

CREATE TABLE IF NOT EXISTS choice_visuals (
    choice_id INTEGER NOT NULL REFERENCES choices(id) ON DELETE CASCADE,
    visual_id INTEGER NOT NULL REFERENCES visuals(id),
    PRIMARY KEY(choice_id, visual_id)
);

CREATE TABLE IF NOT EXISTS passage_visuals (
    passage_id INTEGER NOT NULL REFERENCES passages(id) ON DELETE CASCADE,
    visual_id INTEGER NOT NULL REFERENCES visuals(id),
    PRIMARY KEY(passage_id, visual_id)
);

CREATE TABLE IF NOT EXISTS answer_observations (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    section_id INTEGER NOT NULL REFERENCES sections(id),
    question_id INTEGER REFERENCES questions(id) ON DELETE SET NULL,
    source_page INTEGER NOT NULL,
    printed_number TEXT NOT NULL,
    answer TEXT NOT NULL,
    confidence REAL,
    raw_json TEXT NOT NULL,
    UNIQUE(source_id, section_id, source_page, printed_number)
);

CREATE TABLE IF NOT EXISTS extraction_issues (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    page_number INTEGER NOT NULL,
    issue_type TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_questions_section_number
    ON questions(section_id, printed_number);
CREATE INDEX IF NOT EXISTS idx_answers_unmatched
    ON answer_observations(section_id, printed_number, question_id);
CREATE INDEX IF NOT EXISTS idx_passages_section
    ON passages(section_id, source_page);
CREATE INDEX IF NOT EXISTS idx_visuals_section
    ON visuals(section_id, source_page);

DROP VIEW IF EXISTS benchmark_questions;
CREATE VIEW benchmark_questions AS
SELECT
    q.id AS question_id,
    s.unit_number,
    s.unit_title,
    s.title AS section_title,
    s.subsection,
    s.test_type,
    s.test_number,
    q.printed_number AS question_number,
    p.text AS passage_text,
    p.markdown AS passage_markdown,
    p.description AS passage_description,
    q.stem AS question,
    (
        SELECT json_group_array(json_object(
            'label', c.label,
            'text', c.text,
            'visuals', COALESCE((
                SELECT json_group_array(json_object(
                    'kind', v.kind,
                    'description', v.description,
                    'markdown', v.markdown,
                    'dot', v.dot
                ))
                FROM choice_visuals cv
                JOIN visuals v ON v.id = cv.visual_id
                WHERE cv.choice_id = c.id
            ), json('[]'))
        ))
        FROM choices c
        WHERE c.question_id = q.id
        ORDER BY c.id
    ) AS choices_json,
    (
        SELECT json_group_array(json_object(
            'kind', v.kind,
            'description', v.description,
            'markdown', v.markdown,
            'dot', v.dot
        ))
        FROM question_visuals qv
        JOIN visuals v ON v.id = qv.visual_id
        WHERE qv.question_id = q.id
    ) AS visuals_json,
    q.answer,
    q.source_page_start,
    q.source_page_end,
    q.complete,
    COALESCE(CAST(json_extract(q.raw_json, '$.requires_image') AS INTEGER), 0)
        AS requires_image,
    q.bbox_json AS question_bbox_json,
    (
        SELECT pg.rendered_image
        FROM pages pg
        WHERE pg.source_id = q.source_id
          AND pg.page_number = q.source_page_start
    ) AS image_path,
    q.confidence,
    q.answer_confidence
FROM questions q
JOIN sections s ON s.id = q.section_id
LEFT JOIN passages p ON p.id = q.passage_id;
"""

SYSTEM_PROMPT = r"""
You are transcribing a Turkish multiple-choice question bank page for an LLM benchmark.
Return exactly one JSON object and no prose or Markdown fences. Never solve questions. Preserve
Turkish spelling, punctuation, emphasis meaning, formulas, labels, and option order faithfully.
Do not infer facts that are not explicitly printed or drawn.

A page can contain front matter, one or more section transitions, ordinary questions, a shared
passage, visual material, and/or an answer key. Answer keys are commonly printed upside-down at
the bottom. You receive both the full page and, when available, the lower page band rotated 180°.
Inspect that rotated band carefully. Do not mistake ordinary option labels for an answer key.
When an answer-key line is present, return every printed number-answer pair on that line, including
answers for questions shown on earlier pages. The carried `unanswered_question_numbers` exists to
help confirm those earlier question numbers.
Red smudges or broad red marks near the bottom are source-PDF occlusions over the printed answer
strip, not diagrams and not question content. Ignore them. Use the embedded text for any answer-key
pairs that remain recoverable.

Copyright pages, prefaces, tables of contents, introductory prose, and chapter indexes are
`front_matter`, not questions. Numbers and A/B/C labels in a table of contents are never question
numbers or choices. For a front-matter page, return only `page_types: [\"front_matter\"]`; keep
`section_events`, `passages`, `visuals`, `questions`, and `answers` empty.

Visuals must be textualized. Use a literal neutral `description` for every meaningful diagram,
chart, table, map, drawing, or choice image. Add `markdown` when a table/layout/equation is clearer
that way. Add Graphviz `dot` only for graph/network/tree relationships. Record only marked or
visible relationships; do not derive the answer. Decorative publisher art is not a visual.

`section_events` declares each section/test starting on this page. `local_ref` values are arbitrary
unique strings such as `section_1`. A question or answer belonging to the section active before
this page uses section_ref `current`. One belonging to a section started on this page uses that
event's local_ref. If an answer key belongs to the prior section while a new section begins on the
same page, use `current` for the answers and the new local_ref for new questions.
The carried `detected_page_header` comes from the PDF text layer. If its test number, test type, or
topic differs from `current_section`, this page starts a new section and needs a `section_events`
entry even when the visual header is split across columns.

Shared passages and visuals have page-local refs. Context may list earlier database objects as
`db:<integer>`; use those refs when a question continues to use them. If a question continues from
the prior page, set `continuation` true and return the complete reconstructed question using the
provided incomplete-question context. Otherwise set it false.

Output schema:
{
  "page_number": 1,
  "page_types": ["questions", "answer_key", "section_transition", "front_matter"],
  "section_events": [
    {
      "local_ref": "section_1",
      "unit_number": "1",
      "unit_title": "SÖZCÜKTE VE SÖZ ÖBEKLERİNDE ANLAM",
      "title": "Sözcüklerde Çok Anlamlılık",
      "subsection": null,
      "test_type": "KAVRAYALIM",
      "test_number": "1"
    }
  ],
  "passages": [
    {
      "local_ref": "passage_1",
      "section_ref": "section_1",
      "text": "plain transcription",
      "markdown": null,
      "description": null,
      "visual_refs": [],
      "bbox": [0.0, 0.0, 1.0, 1.0]
    }
  ],
  "visuals": [
    {
      "local_ref": "visual_1",
      "section_ref": "section_1",
      "kind": "diagram|table|chart|map|drawing|formula|other",
      "description": "literal description",
      "markdown": null,
      "dot": null,
      "bbox": [0.0, 0.0, 1.0, 1.0]
    }
  ],
  "questions": [
    {
      "section_ref": "section_1",
      "number": "1",
      "stem": "question text without answer choices; include question-specific setup",
      "question_type": "multiple_choice",
      "passage_ref": null,
      "visual_refs": [],
      "choices": [
        {
          "label": "A",
          "text": "choice text or null when purely visual",
          "visual_refs": [],
          "bbox": null
        }
      ],
      "complete": true,
      "continuation": false,
      "bbox": [0.0, 0.0, 1.0, 1.0],
      "confidence": 0.99
    }
  ],
  "answers": [
    {
      "section_ref": "current",
      "number": "1",
      "answer": "C",
      "confidence": 0.99
    }
  ],
  "warnings": ["uncertain or illegible details only"]
}

Use empty arrays for absent collections and null for absent optional values. Bounding boxes are
optional normalized [left, top, right, bottom] page coordinates. Do not omit a visible question
merely because part of it is uncertain; transcribe it and lower confidence/add a warning.
""".strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_command(
    args: list[str], *, capture: bool = True, check: bool = True
) -> subprocess.CompletedProcess[str]:
    LOG.debug("Running command: %s", " ".join(args))
    return subprocess.run(
        args,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
    )


def require_binary(name: str) -> str:
    result = shutil.which(name)
    if not result:
        raise RuntimeError(f"Required executable not found on PATH: {name}")
    return result


def pdf_page_count(pdf_path: Path) -> int:
    result = run_command([require_binary("pdfinfo"), str(pdf_path)])
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
    if not match:
        raise RuntimeError("Could not determine PDF page count from pdfinfo")
    return int(match.group(1))


def extract_page_text(pdf_path: Path, page_number: int) -> str:
    result = run_command(
        [
            require_binary("pdftotext"),
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-layout",
            str(pdf_path),
            "-",
        ],
        check=False,
    )
    diagnostics = result.stderr.strip()
    if diagnostics:
        if result.returncode:
            LOG.warning(
                "pdftotext page %d returned %d; continuing with its available text. "
                "Poppler diagnostics: %s",
                page_number,
                result.returncode,
                diagnostics.replace("\n", " | "),
            )
        else:
            LOG.debug(
                "pdftotext page %d emitted non-fatal Poppler diagnostics: %s",
                page_number,
                diagnostics.replace("\n", " | "),
            )
    return result.stdout.strip()


def parse_pages(spec: str, page_count: int) -> list[int]:
    pages: set[int] = set()
    for raw_part in spec.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text) if start_text else 1
            end = int(end_text) if end_text else page_count
            if start > end:
                raise ValueError(f"Invalid descending page range: {part}")
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))
    invalid = sorted(p for p in pages if p < 1 or p > page_count)
    if invalid:
        raise ValueError(f"Pages outside 1..{page_count}: {invalid}")
    if not pages:
        raise ValueError("Page selection is empty")
    return sorted(pages)


def initialize_database(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_SQL)
    row = connection.execute("SELECT MAX(version) AS version FROM schema_info").fetchone()
    version = row["version"] if row else None
    if version is None:
        connection.execute(
            "INSERT INTO schema_info(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, utc_now()),
        )
    elif version != SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is not supported; expected {SCHEMA_VERSION}"
        )
    page_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(pages)").fetchall()
    }
    if "pdf_text" not in page_columns:
        connection.execute("ALTER TABLE pages ADD COLUMN pdf_text TEXT")
    connection.commit()
    return connection


def ensure_source(
    connection: sqlite3.Connection, pdf_path: Path, sha256: str, page_count: int
) -> int:
    connection.execute(
        """
        INSERT INTO sources(path, sha256, page_count, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(sha256) DO UPDATE SET path=excluded.path, page_count=excluded.page_count
        """,
        (str(pdf_path.resolve()), sha256, page_count, utc_now()),
    )
    row = connection.execute("SELECT id FROM sources WHERE sha256 = ?", (sha256,)).fetchone()
    assert row is not None
    connection.commit()
    return int(row["id"])


def endpoint_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return value + "/chat/completions"
    return value + "/v1/chat/completions"


def render_page(
    pdf_path: Path,
    page_number: int,
    output_dir: Path,
    dpi: int,
    answer_band_fraction: float,
    force: bool,
) -> tuple[Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    full_path = output_dir / f"page-{page_number:04d}.jpg"
    band_path = output_dir / f"page-{page_number:04d}-answer-band.jpg"
    if force or not full_path.exists():
        prefix = full_path.with_suffix("")
        command = [
            require_binary("pdftoppm"),
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-singlefile",
            "-jpeg",
            "-jpegopt",
            "quality=92",
            "-cropbox",
            "-r",
            str(dpi),
            str(pdf_path),
            str(prefix),
        ]
        result = run_command(command, check=False)
        if not full_path.is_file() or full_path.stat().st_size == 0:
            diagnostics = result.stderr.strip() or "no diagnostics"
            raise RuntimeError(
                f"pdftoppm failed to render page {page_number} "
                f"(exit {result.returncode}): {diagnostics}"
            )
        diagnostics = result.stderr.strip()
        if diagnostics:
            if result.returncode:
                LOG.warning(
                    "pdftoppm page %d returned %d but produced a valid image; "
                    "continuing. Poppler diagnostics: %s",
                    page_number,
                    result.returncode,
                    diagnostics.replace("\n", " | "),
                )
            else:
                LOG.debug(
                    "pdftoppm page %d emitted non-fatal Poppler diagnostics: %s",
                    page_number,
                    diagnostics.replace("\n", " | "),
                )
    if force or not band_path.exists():
        if not create_rotated_answer_band(full_path, band_path, answer_band_fraction):
            return full_path, None
    return full_path, band_path if band_path.exists() else None


def create_rotated_answer_band(source: Path, output: Path, fraction: float) -> bool:
    try:
        from PIL import Image  # type: ignore

        with Image.open(source) as image:
            height = image.height
            top = max(0, height - round(height * fraction))
            image.crop((0, top, image.width, height)).rotate(180).save(
                output, format="JPEG", quality=92
            )
        return True
    except ImportError:
        pass
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        filter_expression = (
            f"crop=iw:round(ih*{fraction}):0:ih-round(ih*{fraction}),hflip,vflip"
        )
        run_command(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-vf",
                filter_expression,
                "-q:v",
                "2",
                str(output),
            ]
        )
        return True

    magick = shutil.which("magick") or shutil.which("convert")
    if magick:
        geometry = f"100%x{max(1, round(fraction * 100))}%+0+0"
        args = [
            magick,
            str(source),
            "-gravity",
            "south",
            "-crop",
            geometry,
            "+repage",
            "-rotate",
            "180",
            str(output),
        ]
        run_command(args)
        return True

    sips = shutil.which("sips")
    if sips:
        dimensions = run_command(
            [sips, "-g", "pixelWidth", "-g", "pixelHeight", str(source)]
        ).stdout
        width_match = re.search(r"pixelWidth:\s*(\d+)", dimensions)
        height_match = re.search(r"pixelHeight:\s*(\d+)", dimensions)
        if width_match and height_match:
            width = int(width_match.group(1))
            height = int(height_match.group(1))
            crop_height = max(1, round(height * fraction))
            # sips crop offsets are relative to the centered crop position.
            bottom_offset = max(0, (height - crop_height) // 2)
            with tempfile.TemporaryDirectory(prefix="answer-band-") as temp_dir:
                cropped = Path(temp_dir) / "cropped.jpg"
                run_command(
                    [
                        sips,
                        "--cropOffset",
                        str(bottom_offset),
                        "0",
                        "-c",
                        str(crop_height),
                        str(width),
                        str(source),
                        "--out",
                        str(cropped),
                    ]
                )
                run_command([sips, "-r", "180", str(cropped), "--out", str(output)])
            return True

    LOG.warning(
        "No Pillow, ffmpeg, ImageMagick, or sips found; page will be sent without a rotated answer band"
    )
    return False


def data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def build_page_context(
    connection: sqlite3.Connection, source_id: int, section_id: int | None
) -> dict[str, Any]:
    if section_id is None:
        return {
            "current_section": None,
            "unanswered_question_numbers": [],
            "incomplete_questions": [],
            "recent_passages": [],
            "recent_visuals": [],
        }
    section = connection.execute(
        """
        SELECT id, unit_number, unit_title, title, subsection, test_type, test_number
        FROM sections WHERE id = ?
        """,
        (section_id,),
    ).fetchone()
    unanswered = connection.execute(
        """
        SELECT printed_number FROM questions
        WHERE source_id = ? AND section_id = ? AND answer IS NULL
        ORDER BY id
        """,
        (source_id, section_id),
    ).fetchall()
    incomplete = connection.execute(
        """
        SELECT id, printed_number, stem, raw_json FROM questions
        WHERE source_id = ? AND section_id = ? AND complete = 0
        ORDER BY id DESC LIMIT 5
        """,
        (source_id, section_id),
    ).fetchall()
    passages = connection.execute(
        """
        SELECT id, text, markdown, description FROM passages
        WHERE source_id = ? AND section_id = ? ORDER BY id DESC LIMIT 5
        """,
        (source_id, section_id),
    ).fetchall()
    visuals = connection.execute(
        """
        SELECT id, kind, description, markdown, dot FROM visuals
        WHERE source_id = ? AND section_id = ? ORDER BY id DESC LIMIT 5
        """,
        (source_id, section_id),
    ).fetchall()
    return {
        "current_section": row_dict(section),
        "unanswered_question_numbers": [r["printed_number"] for r in unanswered],
        "incomplete_questions": [dict(r) for r in reversed(incomplete)],
        "recent_passages": [
            {"ref": f"db:{r['id']}", **dict(r)} for r in reversed(passages)
        ],
        "recent_visuals": [
            {"ref": f"db:{r['id']}", **dict(r)} for r in reversed(visuals)
        ],
    }


def make_request_payload(
    model: str,
    page_number: int,
    full_image: Path,
    answer_band: Path | None,
    embedded_text: str,
    context: dict[str, Any],
    temperature: float,
    include_response_format: bool,
) -> dict[str, Any]:
    text = (
        f"Extract PDF page {page_number}. The page number in your JSON must be {page_number}.\n"
        "The PDF's embedded text layer is included below as a transcription aid. Its reading "
        "order may be interleaved across columns, but it can expose rotated answer-key text. "
        "Use the images for layout, emphasis, and visuals.\n"
        f"<embedded_pdf_text>\n{embedded_text}\n</embedded_pdf_text>\n"
        "State carried from earlier pages follows:\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
    )
    content: list[dict[str, Any]] = [
        {"type": "text", "text": text},
        {
            "type": "image_url",
            "image_url": {"url": data_url(full_image), "detail": "high"},
        },
    ]
    if answer_band is not None and not has_embedded_answer_key(embedded_text):
        content.extend(
            [
                {
                    "type": "text",
                    "text": "The next image is the bottom band of this page rotated 180 degrees. Use it only to read a possible upside-down answer key.",
                },
                {
                    "type": "image_url",
                    "image_url": {"url": data_url(answer_band), "detail": "high"},
                },
            ]
        )
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": temperature,
    }
    if include_response_format:
        payload["response_format"] = {"type": "json_object"}
    return payload


def sanitized_payload(payload: dict[str, Any], image_paths: Iterable[Path]) -> dict[str, Any]:
    sanitized = json.loads(json.dumps(payload))
    path_iter = iter(image_paths)
    for message in sanitized.get("messages", []):
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if item.get("type") != "image_url":
                continue
            try:
                path = next(path_iter)
                descriptor = {
                    "path": str(path),
                    "sha256": file_sha256(path),
                    "bytes": path.stat().st_size,
                }
            except StopIteration:
                descriptor = {"path": "unknown"}
            item["image_url"]["url"] = descriptor
    return sanitized


class InteractionLogger:
    def __init__(self, path: Path | None):
        self.path = path
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: dict[str, Any]) -> None:
        if not self.path:
            return
        enriched = {"timestamp": utc_now(), **event}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json_compact(enriched) + "\n")


def post_chat_completion(
    url: str,
    api_key: str | None,
    payload: dict[str, Any],
    timeout: float,
) -> tuple[dict[str, Any], str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach LLM endpoint {url}: {exc.reason}") from exc
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM endpoint returned non-JSON: {raw[:1000]}") from exc
    return decoded, raw


def extract_message_content(response: dict[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Missing choices[0].message.content: {response}") from exc
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in ("text", "output_text"):
                parts.append(str(item.get("text", "")))
        return "".join(parts)
    raise ValueError(f"Unsupported message content type: {type(content).__name__}")


def parse_model_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model response contains no JSON object")
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in model response: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Model response must be a JSON object")
    return value


def require_list(value: dict[str, Any], key: str) -> list[Any]:
    result = value.get(key, [])
    if result is None:
        return []
    if not isinstance(result, list):
        raise ValueError(f"{key} must be an array")
    return result


def has_embedded_answer_key(embedded_text: str) -> bool:
    return any(
        len(ANSWER_KEY_PAIR.findall(line.upper())) >= 3
        for line in embedded_text.splitlines()
    )


ANSWER_KEY_PAIR = re.compile(r"(?<!\d)(\d{1,3})\s*[-–—]\s*([A-E])\b")

TEST_TYPE_NAMES = (
    "KAVRAYALIM",
    "PEKİŞTİRELİM",
    "SINAV PROVASI",
    "HATIRLAYALIM",
)


def detect_page_section_header(embedded_text: str) -> dict[str, str]:
    first_question = re.search(r"(?m)^\s*\d{1,3}\.\s+\S", embedded_text)
    header = embedded_text[: first_question.start()] if first_question else embedded_text[:2000]
    test_type = next((name for name in TEST_TYPE_NAMES if name in header.upper()), None)
    direct_number = re.search(r"(?i)\bTest\s*[·.:\-]?\s*(\d{1,3})\b", header)
    numbered_title = re.search(
        r"(?m)^\s*(\d{1,3})\s+([^\n]+?)\s*$", header
    )
    if direct_number:
        test_number = direct_number.group(1)
    elif numbered_title and "TEST" not in numbered_title.group(2).upper():
        test_number = numbered_title.group(1)
    else:
        standalone_numbers = re.findall(r"(?m)^\s*(\d{1,3})\s*$", header)
        test_number = standalone_numbers[-1] if standalone_numbers else None

    title_candidates: list[str] = []
    for raw_line in header.splitlines():
        line = " ".join(raw_line.split())
        line = re.sub(r"^\d{1,3}\s+", "", line)
        upper = line.upper()
        if not line or line.startswith("@") or line.isdigit():
            continue
        if "TEST" in upper or "BÖLÜM" in upper:
            continue
        if any(name in upper for name in TEST_TYPE_NAMES):
            continue
        if line.isupper():
            continue
        title_candidates.append(line)
    title = max(title_candidates, key=len) if title_candidates else None
    return {
        key: value
        for key, value in {
            "test_type": test_type,
            "test_number": test_number,
            "title": title,
        }.items()
        if value
    }


def header_matches_section(
    header: dict[str, str], section: dict[str, Any] | None
) -> bool:
    if not section:
        return False
    for key in ("test_type", "test_number", "title"):
        detected = header.get(key)
        existing = section.get(key)
        if detected and existing and str(detected).casefold() != str(existing).casefold():
            return False
    return bool(header.get("test_number") or header.get("title"))


def reassign_new_section_records(result: dict[str, Any], local_ref: str) -> None:
    question_numbers: set[str] = set()
    for key in ("passages", "visuals", "questions"):
        for record in result.get(key, []):
            if not isinstance(record, dict):
                continue
            if str(record.get("section_ref") or "current") == "current":
                record["section_ref"] = local_ref
            if key == "questions":
                question_numbers.add(str(record.get("number") or ""))
    for answer in result.get("answers", []):
        if not isinstance(answer, dict):
            continue
        if (
            str(answer.get("section_ref") or "current") == "current"
            and str(answer.get("number") or "") in question_numbers
        ):
            answer["section_ref"] = local_ref


def ensure_detected_section_transition(
    result: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    header = context.get("detected_page_header") or {}
    if not header or "front_matter" in result.get("page_types", []):
        return result
    current = context.get("current_section")
    current_matches = header_matches_section(header, current)
    matching_event: dict[str, Any] | None = None
    for event in result.get("section_events", []):
        if header_matches_section(header, event):
            matching_event = event
            break
    if matching_event is not None:
        if not current_matches:
            local_ref = str(matching_event.get("local_ref") or "detected_section")
            matching_event["local_ref"] = local_ref
            reassign_new_section_records(result, local_ref)
        return result
    if current_matches:
        return result

    local_ref = "detected_" + re.sub(
        r"[^a-z0-9]+",
        "_",
        f"{header.get('test_type', 'section')}_{header.get('test_number', 'new')}".casefold(),
    ).strip("_")
    event = {
        "local_ref": local_ref,
        "unit_number": header.get("unit_number")
        or (current.get("unit_number") if current else None),
        "unit_title": header.get("unit_title")
        or (current.get("unit_title") if current else None),
        "title": header.get("title") or (current.get("title") if current else None),
        "subsection": current.get("subsection") if current else None,
        "test_type": header.get("test_type")
        or (current.get("test_type") if current else None),
        "test_number": header.get("test_number"),
        "detected_from_embedded_text": True,
    }
    result.setdefault("section_events", []).insert(0, event)
    reassign_new_section_records(result, local_ref)
    result["section_transition_recovery"] = {
        "local_ref": local_ref,
        "detected_header": header,
    }
    return result


def merge_embedded_answer_key(
    result: dict[str, Any], embedded_text: str, context: dict[str, Any]
) -> dict[str, Any]:
    pairs: list[tuple[str, str]] = []
    source_lines: list[str] = []
    for line in embedded_text.splitlines():
        line_pairs = ANSWER_KEY_PAIR.findall(line.upper())
        if len(line_pairs) < 3:
            continue
        pairs.extend(line_pairs)
        source_lines.append(line.strip())
    if not pairs:
        return result

    unique_pairs: dict[str, str] = {}
    for number, answer in pairs:
        unique_pairs[str(int(number))] = answer
    key_numbers = set(unique_pairs)
    unanswered = {
        str(number) for number in context.get("unanswered_question_numbers", [])
    }
    current_available = context.get("current_section") is not None

    section_ref: str | None = None
    ref_counts: dict[str, int] = {}
    for question in result.get("questions", []):
        if str(question.get("number", "")) not in key_numbers:
            continue
        ref = str(question.get("section_ref") or "current")
        ref_counts[ref] = ref_counts.get(ref, 0) + 1
    if ref_counts:
        section_ref = max(ref_counts, key=ref_counts.get)
    elif current_available and key_numbers.intersection(unanswered):
        section_ref = "current"
    elif len(result.get("section_events", [])) == 1:
        section_ref = str(
            result["section_events"][0].get("local_ref") or "section_1"
        )
    elif current_available:
        section_ref = "current"
    if section_ref is None:
        result.setdefault("warnings", []).append(
            "Found an embedded answer-key line but could not identify its section."
        )
        return result

    answers = result.setdefault("answers", [])
    existing: dict[tuple[str, str], dict[str, Any]] = {}
    for item in answers:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("section_ref") or "current"),
            str(item.get("number") or ""),
        )
        existing[key] = item

    added = 0
    corrected = 0
    for number, answer in unique_pairs.items():
        key = (section_ref, number)
        item = existing.get(key)
        if item is None:
            answers.append(
                {
                    "section_ref": section_ref,
                    "number": number,
                    "answer": answer,
                    "confidence": 1.0,
                    "source": "embedded_answer_key",
                }
            )
            added += 1
        elif str(item.get("answer") or "").upper() != answer:
            previous = item.get("answer")
            item.update(
                {
                    "answer": answer,
                    "confidence": 1.0,
                    "source": "embedded_answer_key",
                }
            )
            corrected += 1
            result.setdefault("warnings", []).append(
                f"Embedded answer key corrected question {number} from "
                f"{previous!r} to {answer!r}."
            )
    result["answer_key_recovery"] = {
        "section_ref": section_ref,
        "pairs_found": len(unique_pairs),
        "answers_added": added,
        "answers_corrected": corrected,
        "source_lines": source_lines,
    }
    return result


def validate_page_result(result: dict[str, Any], expected_page: int) -> dict[str, Any]:
    if int(result.get("page_number", -1)) != expected_page:
        raise ValueError(
            f"Response page_number {result.get('page_number')!r} does not match {expected_page}"
        )
    for key in (
        "page_types",
        "section_events",
        "passages",
        "visuals",
        "questions",
        "answers",
        "warnings",
    ):
        require_list(result, key)
    page_types = {str(value) for value in result["page_types"]}
    if "front_matter" in page_types:
        record_keys = ("section_events", "passages", "visuals", "questions", "answers")
        discarded = {
            key: len(result[key]) for key in record_keys if len(result[key]) > 0
        }
        for key in record_keys:
            result[key] = []
        if discarded:
            result["warnings"].append(
                "Discarded records returned for a front-matter page: "
                + json_compact(discarded)
            )
    for question in result["questions"]:
        if not isinstance(question, dict):
            raise ValueError("Every question must be an object")
        if not str(question.get("number", "")).strip():
            raise ValueError("Every question needs a printed number")
        if not str(question.get("stem", "")).strip():
            raise ValueError(f"Question {question.get('number')} has an empty stem")
        labels: set[str] = set()
        for choice in require_list(question, "choices"):
            if not isinstance(choice, dict):
                raise ValueError("Every choice must be an object")
            label = str(choice.get("label", "")).strip().upper()
            if not label:
                raise ValueError(f"Question {question.get('number')} has an unlabeled choice")
            if label in labels:
                raise ValueError(
                    f"Question {question.get('number')} repeats choice label {label}"
                )
            labels.add(label)
    return result


def section_key(event: dict[str, Any], page_number: int, local_ref: str) -> str:
    identity_keys = (
        ("subsection", "test_type", "test_number")
        if event.get("test_type") == "PEGEM ALES"
        else (
            "unit_number",
            "unit_title",
            "title",
            "subsection",
            "test_type",
            "test_number",
        )
    )
    identity = {key: event.get(key) for key in identity_keys}
    if any(value not in (None, "") for value in identity.values()):
        canonical = json_compact(identity)
    else:
        canonical = f"page:{page_number}:ref:{local_ref}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def record_issue(
    connection: sqlite3.Connection,
    source_id: int,
    page_number: int,
    issue_type: str,
    details: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO extraction_issues(source_id, page_number, issue_type, details_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (source_id, page_number, issue_type, json_compact(details), utc_now()),
    )
    LOG.warning("Page %d %s: %s", page_number, issue_type, details)


def resolve_section_ref(
    ref: Any,
    current_section_id: int | None,
    local_sections: dict[str, int],
) -> int:
    text = str(ref or "current")
    if text == "current":
        if current_section_id is None:
            raise ValueError("section_ref=current but there is no active section")
        return current_section_id
    if text in local_sections:
        return local_sections[text]
    if text.startswith("db:") and text[3:].isdigit():
        return int(text[3:])
    raise ValueError(f"Unknown section_ref: {text}")


def resolve_object_ref(
    ref: Any, local_objects: dict[str, int], table: str, connection: sqlite3.Connection
) -> int | None:
    if ref in (None, ""):
        return None
    text = str(ref)
    if text in local_objects:
        return local_objects[text]
    if text.startswith("db:") and text[3:].isdigit():
        object_id = int(text[3:])
        row = connection.execute(f"SELECT id FROM {table} WHERE id = ?", (object_id,)).fetchone()
        if row:
            return object_id
    raise ValueError(f"Unknown {table} ref: {text}")


def previous_active_section(
    connection: sqlite3.Connection, source_id: int, page_number: int
) -> int | None:
    row = connection.execute(
        """
        SELECT active_section_after_id FROM pages
        WHERE source_id = ? AND page_number < ? AND status = 'complete'
        ORDER BY page_number DESC LIMIT 1
        """,
        (source_id, page_number),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def cleanup_page_data(
    connection: sqlite3.Connection, source_id: int, page_number: int
) -> None:
    affected = connection.execute(
        """
        SELECT DISTINCT question_id FROM answer_observations
        WHERE source_id = ? AND source_page = ? AND question_id IS NOT NULL
        """,
        (source_id, page_number),
    ).fetchall()
    connection.execute(
        "DELETE FROM answer_observations WHERE source_id = ? AND source_page = ?",
        (source_id, page_number),
    )
    for row in affected:
        recompute_question_answer(connection, int(row["question_id"]))
    connection.execute(
        "DELETE FROM questions WHERE source_id = ? AND source_page_start = ?",
        (source_id, page_number),
    )
    page = connection.execute(
        "SELECT id FROM pages WHERE source_id = ? AND page_number = ?",
        (source_id, page_number),
    ).fetchone()
    if page:
        connection.execute("DELETE FROM page_section_events WHERE page_id = ?", (page["id"],))
    connection.execute(
        "DELETE FROM extraction_issues WHERE source_id = ? AND page_number = ?",
        (source_id, page_number),
    )


def upsert_section(
    connection: sqlite3.Connection,
    source_id: int,
    run_id: int,
    page_number: int,
    event: dict[str, Any],
    local_ref: str,
) -> int:
    key = section_key(event, page_number, local_ref)
    values = (
        source_id,
        key,
        event.get("unit_number"),
        event.get("unit_title"),
        event.get("title"),
        event.get("subsection"),
        event.get("test_type"),
        event.get("test_number"),
        page_number,
        json_compact(event),
        run_id,
    )
    connection.execute(
        """
        INSERT INTO sections(
            source_id, section_key, unit_number, unit_title, title, subsection,
            test_type, test_number, source_page_start, raw_json, created_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id, section_key) DO UPDATE SET
            unit_number=excluded.unit_number,
            unit_title=excluded.unit_title,
            title=excluded.title,
            subsection=excluded.subsection,
            test_type=excluded.test_type,
            test_number=excluded.test_number,
            source_page_start=MIN(sections.source_page_start, excluded.source_page_start),
            raw_json=excluded.raw_json
        """,
        values,
    )
    row = connection.execute(
        "SELECT id FROM sections WHERE source_id = ? AND section_key = ?",
        (source_id, key),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def ensure_synthetic_section(
    connection: sqlite3.Connection, source_id: int, run_id: int, page_number: int
) -> int:
    event = {
        "local_ref": "synthetic",
        "unit_number": None,
        "unit_title": None,
        "title": f"Unknown section before page {page_number}",
        "subsection": None,
        "test_type": None,
        "test_number": None,
    }
    return upsert_section(connection, source_id, run_id, page_number, event, "synthetic")


def recompute_question_answer(connection: sqlite3.Connection, question_id: int) -> None:
    question = connection.execute(
        "SELECT section_id, printed_number FROM questions WHERE id = ?", (question_id,)
    ).fetchone()
    if not question:
        return
    observations = connection.execute(
        """
        SELECT id, answer, source_page, confidence FROM answer_observations
        WHERE section_id = ? AND printed_number = ?
        ORDER BY source_page, id
        """,
        (question["section_id"], question["printed_number"]),
    ).fetchall()
    if not observations:
        connection.execute(
            """
            UPDATE questions SET answer=NULL, answer_source_page=NULL, answer_confidence=NULL
            WHERE id = ?
            """,
            (question_id,),
        )
        return
    latest = observations[-1]
    connection.execute(
        """
        UPDATE questions SET answer=?, answer_source_page=?, answer_confidence=? WHERE id=?
        """,
        (latest["answer"], latest["source_page"], latest["confidence"], question_id),
    )
    connection.execute(
        """
        UPDATE answer_observations SET question_id=?
        WHERE section_id=? AND printed_number=?
        """,
        (question_id, question["section_id"], question["printed_number"]),
    )


def ingest_page_result(
    connection: sqlite3.Connection,
    source_id: int,
    run_id: int,
    page_number: int,
    page_id: int,
    current_section_id: int | None,
    result: dict[str, Any],
    *,
    report_answer_conflicts: bool = True,
) -> tuple[int | None, dict[str, int]]:
    local_sections: dict[str, int] = {}
    active_after = current_section_id
    for index, event in enumerate(require_list(result, "section_events")):
        if not isinstance(event, dict):
            raise ValueError("Every section event must be an object")
        local_ref = str(event.get("local_ref") or f"section_{index + 1}")
        if local_ref in local_sections:
            raise ValueError(f"Duplicate section local_ref: {local_ref}")
        section_id = upsert_section(
            connection, source_id, run_id, page_number, event, local_ref
        )
        local_sections[local_ref] = section_id
        active_after = section_id
        connection.execute(
            """
            INSERT INTO page_section_events(page_id, event_order, section_id, local_ref)
            VALUES (?, ?, ?, ?)
            """,
            (page_id, index, section_id, local_ref),
        )

    has_records = any(
        require_list(result, key)
        for key in ("passages", "visuals", "questions", "answers")
    )
    if active_after is None and has_records:
        active_after = ensure_synthetic_section(
            connection, source_id, run_id, page_number
        )
        local_sections["synthetic"] = active_after
        if current_section_id is None:
            current_section_id = active_after
        record_issue(
            connection,
            source_id,
            page_number,
            "synthetic_section",
            {"reason": "Page contains records but no active or new section"},
        )

    visual_ids: dict[str, int] = {}
    for index, visual in enumerate(require_list(result, "visuals")):
        if not isinstance(visual, dict):
            raise ValueError("Every visual must be an object")
        local_ref = str(visual.get("local_ref") or f"visual_{index + 1}")
        section_id = resolve_section_ref(
            visual.get("section_ref"), current_section_id, local_sections
        )
        description = str(visual.get("description") or "").strip()
        if not description:
            raise ValueError(f"Visual {local_ref} must have a literal description")
        connection.execute(
            """
            INSERT INTO visuals(
                source_id, section_id, source_page, local_ref, kind, description,
                markdown, dot, bbox_json, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, source_page, local_ref) DO UPDATE SET
                section_id=excluded.section_id,
                kind=excluded.kind,
                description=excluded.description,
                markdown=excluded.markdown,
                dot=excluded.dot,
                bbox_json=excluded.bbox_json,
                raw_json=excluded.raw_json
            """,
            (
                source_id,
                section_id,
                page_number,
                local_ref,
                str(visual.get("kind") or "other"),
                description,
                visual.get("markdown"),
                visual.get("dot"),
                json_compact(visual.get("bbox")),
                json_compact(visual),
            ),
        )
        row = connection.execute(
            """
            SELECT id FROM visuals WHERE source_id=? AND source_page=? AND local_ref=?
            """,
            (source_id, page_number, local_ref),
        ).fetchone()
        assert row is not None
        visual_ids[local_ref] = int(row["id"])

    passage_ids: dict[str, int] = {}
    passage_visual_refs: dict[int, list[Any]] = {}
    for index, passage in enumerate(require_list(result, "passages")):
        if not isinstance(passage, dict):
            raise ValueError("Every passage must be an object")
        local_ref = str(passage.get("local_ref") or f"passage_{index + 1}")
        section_id = resolve_section_ref(
            passage.get("section_ref"), current_section_id, local_sections
        )
        if not any(passage.get(key) for key in ("text", "markdown", "description")):
            raise ValueError(f"Passage {local_ref} has no content")
        connection.execute(
            """
            INSERT INTO passages(
                source_id, section_id, source_page, local_ref, text, markdown,
                description, bbox_json, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, source_page, local_ref) DO UPDATE SET
                section_id=excluded.section_id,
                text=excluded.text,
                markdown=excluded.markdown,
                description=excluded.description,
                bbox_json=excluded.bbox_json,
                raw_json=excluded.raw_json
            """,
            (
                source_id,
                section_id,
                page_number,
                local_ref,
                passage.get("text"),
                passage.get("markdown"),
                passage.get("description"),
                json_compact(passage.get("bbox")),
                json_compact(passage),
            ),
        )
        row = connection.execute(
            """
            SELECT id FROM passages WHERE source_id=? AND source_page=? AND local_ref=?
            """,
            (source_id, page_number, local_ref),
        ).fetchone()
        assert row is not None
        passage_id = int(row["id"])
        passage_ids[local_ref] = passage_id
        passage_visual_refs[passage_id] = require_list(passage, "visual_refs")

    for passage_id, refs in passage_visual_refs.items():
        connection.execute("DELETE FROM passage_visuals WHERE passage_id=?", (passage_id,))
        for ref in refs:
            visual_id = resolve_object_ref(ref, visual_ids, "visuals", connection)
            assert visual_id is not None
            connection.execute(
                "INSERT OR IGNORE INTO passage_visuals(passage_id, visual_id) VALUES (?, ?)",
                (passage_id, visual_id),
            )

    inserted_questions: dict[str, int] = {}
    for question in require_list(result, "questions"):
        section_id = resolve_section_ref(
            question.get("section_ref"), current_section_id, local_sections
        )
        number = str(question["number"]).strip()
        existing = connection.execute(
            """
            SELECT id, source_page_start FROM questions
            WHERE source_id=? AND section_id=? AND printed_number=?
            """,
            (source_id, section_id, number),
        ).fetchone()
        continuation = bool(question.get("continuation", False))
        if existing and not continuation and int(existing["source_page_start"]) != page_number:
            raise ValueError(
                f"Question {number} already exists in section {section_id} from page "
                f"{existing['source_page_start']}; refusing to overwrite it. This usually "
                "means a test or section transition was missed."
            )
        source_start = int(existing["source_page_start"]) if existing else page_number
        passage_id = resolve_object_ref(
            question.get("passage_ref"), passage_ids, "passages", connection
        )
        connection.execute(
            """
            INSERT INTO questions(
                source_id, section_id, source_page_start, source_page_end, printed_number,
                stem, question_type, passage_id, complete, bbox_json, confidence, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, section_id, printed_number) DO UPDATE SET
                source_page_end=excluded.source_page_end,
                stem=excluded.stem,
                question_type=excluded.question_type,
                passage_id=excluded.passage_id,
                complete=excluded.complete,
                bbox_json=excluded.bbox_json,
                confidence=excluded.confidence,
                raw_json=excluded.raw_json
            """,
            (
                source_id,
                section_id,
                source_start,
                page_number,
                number,
                str(question["stem"]).strip(),
                question.get("question_type") or "multiple_choice",
                passage_id,
                1 if question.get("complete", True) else 0,
                json_compact(question.get("bbox")),
                question.get("confidence"),
                json_compact(question),
            ),
        )
        row = connection.execute(
            """
            SELECT id FROM questions
            WHERE source_id=? AND section_id=? AND printed_number=?
            """,
            (source_id, section_id, number),
        ).fetchone()
        assert row is not None
        question_id = int(row["id"])
        inserted_questions[number] = question_id
        connection.execute("DELETE FROM choices WHERE question_id=?", (question_id,))
        connection.execute("DELETE FROM question_visuals WHERE question_id=?", (question_id,))
        for ref in require_list(question, "visual_refs"):
            visual_id = resolve_object_ref(ref, visual_ids, "visuals", connection)
            assert visual_id is not None
            connection.execute(
                "INSERT OR IGNORE INTO question_visuals(question_id, visual_id) VALUES (?, ?)",
                (question_id, visual_id),
            )
        for choice in require_list(question, "choices"):
            label = str(choice["label"]).strip().upper()
            cursor = connection.execute(
                """
                INSERT INTO choices(question_id, label, text, bbox_json, raw_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    question_id,
                    label,
                    choice.get("text"),
                    json_compact(choice.get("bbox")),
                    json_compact(choice),
                ),
            )
            choice_id = int(cursor.lastrowid)
            for ref in require_list(choice, "visual_refs"):
                visual_id = resolve_object_ref(ref, visual_ids, "visuals", connection)
                assert visual_id is not None
                connection.execute(
                    "INSERT OR IGNORE INTO choice_visuals(choice_id, visual_id) VALUES (?, ?)",
                    (choice_id, visual_id),
                )
        recompute_question_answer(connection, question_id)

    for answer in require_list(result, "answers"):
        if not isinstance(answer, dict):
            raise ValueError("Every answer must be an object")
        section_id = resolve_section_ref(
            answer.get("section_ref"), current_section_id, local_sections
        )
        number = str(answer.get("number") or "").strip()
        choice_label = str(answer.get("answer") or "").strip().upper()
        if not number or not choice_label:
            raise ValueError("Every answer needs number and answer fields")
        question = connection.execute(
            """
            SELECT id, answer FROM questions
            WHERE source_id=? AND section_id=? AND printed_number=?
            """,
            (source_id, section_id, number),
        ).fetchone()
        question_id = int(question["id"]) if question else None
        if (
            report_answer_conflicts
            and question
            and question["answer"]
            and question["answer"] != choice_label
        ):
            record_issue(
                connection,
                source_id,
                page_number,
                "answer_conflict",
                {
                    "section_id": section_id,
                    "number": number,
                    "existing": question["answer"],
                    "new": choice_label,
                },
            )
        connection.execute(
            """
            INSERT INTO answer_observations(
                source_id, section_id, question_id, source_page, printed_number,
                answer, confidence, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, section_id, source_page, printed_number) DO UPDATE SET
                question_id=excluded.question_id,
                answer=excluded.answer,
                confidence=excluded.confidence,
                raw_json=excluded.raw_json
            """,
            (
                source_id,
                section_id,
                question_id,
                page_number,
                number,
                choice_label,
                answer.get("confidence"),
                json_compact(answer),
            ),
        )
        if question_id is not None:
            recompute_question_answer(connection, question_id)
        else:
            record_issue(
                connection,
                source_id,
                page_number,
                "unmatched_answer",
                {"section_id": section_id, "number": number, "answer": choice_label},
            )

    for warning in require_list(result, "warnings"):
        record_issue(
            connection,
            source_id,
            page_number,
            "model_warning",
            {"warning": str(warning)},
        )

    return active_after, inserted_questions


def counts_for_page(result: dict[str, Any]) -> dict[str, int]:
    return {
        key: len(require_list(result, key))
        for key in ("section_events", "passages", "visuals", "questions", "answers", "warnings")
    }


def configure_logging(verbose: int) -> None:
    level = logging.WARNING
    if verbose == 1:
        level = logging.INFO
    elif verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a PDF question bank to SQLite with a local vision LLM."
    )
    parser.add_argument("pdf", type=Path, help="source PDF")
    parser.add_argument("--db", type=Path, default=Path("questions.sqlite"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1"),
        help="OpenAI-compatible base URL or full chat/completions URL",
    )
    parser.add_argument(
        "--model", default=os.environ.get("LOCAL_LLM_MODEL", "local-model")
    )
    parser.add_argument(
        "--api-key", default=os.environ.get("LOCAL_LLM_API_KEY"), help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--pages",
        default="9-",
        help="PDF pages to process (default: 9-, after this book's front matter)",
    )
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--answer-band-fraction", type=float, default=0.16)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--response-format",
        choices=("auto", "json", "none"),
        default="auto",
        help="request response_format=json_object; auto retries unsupported servers without it",
    )
    parser.add_argument(
        "--render-dir",
        type=Path,
        help="rendered image directory (default: <db>.assets/<pdf hash>)",
    )
    parser.add_argument(
        "--interaction-log",
        type=Path,
        help="append sanitized prompts, responses, timing, and errors as JSONL",
    )
    parser.add_argument("--force", action="store_true", help="re-extract selected pages")
    parser.add_argument(
        "--replay-stored",
        action="store_true",
        help="rebuild selected pages from stored parsed responses without calling the LLM",
    )
    parser.add_argument(
        "--render-only", action="store_true", help="render selected pages without calling the LLM"
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)
    pdf_path: Path = args.pdf.resolve()
    db_path: Path = args.db.resolve()
    if args.render_only and args.replay_stored:
        raise ValueError("--render-only and --replay-stored cannot be used together")
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if args.dpi < 72:
        raise ValueError("--dpi must be at least 72")
    if not 0.05 <= args.answer_band_fraction <= 0.5:
        raise ValueError("--answer-band-fraction must be between 0.05 and 0.5")

    page_count = pdf_page_count(pdf_path)
    selected_pages = parse_pages(args.pages, page_count)
    pdf_sha = file_sha256(pdf_path)
    render_dir = (
        args.render_dir.resolve()
        if args.render_dir
        else db_path.with_suffix(db_path.suffix + ".assets") / pdf_sha[:16]
    )
    interaction_logger = InteractionLogger(
        args.interaction_log.resolve() if args.interaction_log else None
    )
    connection = initialize_database(db_path)
    source_id = ensure_source(connection, pdf_path, pdf_sha, page_count)
    config = {
        "pages": args.pages,
        "dpi": args.dpi,
        "answer_band_fraction": args.answer_band_fraction,
        "temperature": args.temperature,
        "response_format": args.response_format,
        "render_dir": str(render_dir),
    }
    cursor = connection.execute(
        """
        INSERT INTO extraction_runs(source_id, model, endpoint, config_json, started_at, status)
        VALUES (?, ?, ?, ?, ?, 'running')
        """,
        (
            source_id,
            args.model,
            endpoint_url(args.base_url),
            json_compact(config),
            utc_now(),
        ),
    )
    run_id = int(cursor.lastrowid)
    connection.commit()
    LOG.info(
        "Source %s (%d pages, sha256=%s); selected %d page(s)",
        pdf_path.name,
        page_count,
        pdf_sha[:16],
        len(selected_pages),
    )

    try:
        for page_number in selected_pages:
            existing = connection.execute(
                "SELECT * FROM pages WHERE source_id=? AND page_number=?",
                (source_id, page_number),
            ).fetchone()
            if (
                existing
                and existing["status"] == "complete"
                and not args.force
                and not args.replay_stored
            ):
                LOG.info("Page %d already complete; skipping", page_number)
                continue
            current_section_id = previous_active_section(connection, source_id, page_number)
            if args.replay_stored:
                if not existing or not existing["parsed_json"] or not existing["pdf_text"]:
                    raise RuntimeError(
                        f"Page {page_number} has no stored parsed response to replay"
                    )
                page_text = str(existing["pdf_text"])
                context = build_page_context(connection, source_id, current_section_id)
                context["detected_page_header"] = detect_page_section_header(page_text)
                parsed = json.loads(existing["parsed_json"])
                parsed = ensure_detected_section_transition(parsed, context)
                parsed = merge_embedded_answer_key(parsed, page_text, context)
                parsed = validate_page_result(parsed, page_number)
                page_id = int(existing["id"])
                with connection:
                    cleanup_page_data(connection, source_id, page_number)
                    active_after, _ = ingest_page_result(
                        connection,
                        source_id,
                        run_id,
                        page_number,
                        page_id,
                        current_section_id,
                        parsed,
                        report_answer_conflicts=False,
                    )
                    connection.execute(
                        """
                        UPDATE pages SET run_id=?, status='complete',
                            active_section_before_id=?, active_section_after_id=?,
                            parsed_json=?, error=NULL, elapsed_seconds=0,
                            extracted_at=? WHERE id=?
                        """,
                        (
                            run_id,
                            current_section_id,
                            active_after,
                            json_compact(parsed),
                            utc_now(),
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
                    "Page %d replayed from stored response: %s",
                    page_number,
                    counts_for_page(parsed),
                )
                continue
            full_image, answer_band = render_page(
                pdf_path,
                page_number,
                render_dir,
                args.dpi,
                args.answer_band_fraction,
                args.force,
            )
            render_hash = file_sha256(full_image)
            page_text = extract_page_text(pdf_path, page_number)
            LOG.info(
                "Page %d rendered: %s%s",
                page_number,
                full_image,
                f"; rotated band {answer_band}" if answer_band else "",
            )
            if args.render_only:
                continue

            context = build_page_context(connection, source_id, current_section_id)
            context["detected_page_header"] = detect_page_section_header(page_text)
            connection.execute(
                """
                INSERT INTO pages(
                    source_id, page_number, run_id, status, rendered_image,
                    rendered_sha256, answer_band_image, pdf_text, active_section_before_id
                ) VALUES (?, ?, ?, 'processing', ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, page_number) DO UPDATE SET
                    run_id=excluded.run_id,
                    status='processing',
                    rendered_image=excluded.rendered_image,
                    rendered_sha256=excluded.rendered_sha256,
                    answer_band_image=excluded.answer_band_image,
                    pdf_text=excluded.pdf_text,
                    active_section_before_id=excluded.active_section_before_id,
                    error=NULL
                """,
                (
                    source_id,
                    page_number,
                    run_id,
                    str(full_image),
                    render_hash,
                    str(answer_band) if answer_band else None,
                    page_text,
                    current_section_id,
                ),
            )
            page_row = connection.execute(
                "SELECT id FROM pages WHERE source_id=? AND page_number=?",
                (source_id, page_number),
            ).fetchone()
            assert page_row is not None
            page_id = int(page_row["id"])
            connection.commit()

            include_response_format = args.response_format != "none"
            parsed: dict[str, Any] | None = None
            raw_api_response = ""
            sanitized_request: dict[str, Any] = {}
            started = time.monotonic()
            last_error: Exception | None = None
            for attempt in range(1, args.max_retries + 2):
                payload = make_request_payload(
                    args.model,
                    page_number,
                    full_image,
                    answer_band,
                    page_text,
                    context,
                    args.temperature,
                    include_response_format,
                )
                image_paths = [full_image]
                if answer_band and not has_embedded_answer_key(page_text):
                    image_paths.append(answer_band)
                sanitized_request = sanitized_payload(payload, image_paths)
                LOG.debug(
                    "Page %d attempt %d: POST %s with %d image(s) and %d embedded-text characters",
                    page_number,
                    attempt,
                    endpoint_url(args.base_url),
                    len(image_paths),
                    len(page_text),
                )
                interaction_logger.write(
                    {
                        "event": "request",
                        "page": page_number,
                        "attempt": attempt,
                        "endpoint": endpoint_url(args.base_url),
                        "payload": sanitized_request,
                    }
                )
                try:
                    response, raw_api_response = post_chat_completion(
                        endpoint_url(args.base_url), args.api_key, payload, args.timeout
                    )
                    content = extract_message_content(response)
                    LOG.debug(
                        "Page %d received %d response bytes and %d content characters",
                        page_number,
                        len(raw_api_response.encode("utf-8")),
                        len(content),
                    )
                    interaction_logger.write(
                        {
                            "event": "response",
                            "page": page_number,
                            "attempt": attempt,
                            "elapsed_seconds": round(time.monotonic() - started, 3),
                            "response": response,
                            "message_content": content,
                        }
                    )
                    candidate = parse_model_json(content)
                    candidate = ensure_detected_section_transition(candidate, context)
                    candidate = merge_embedded_answer_key(candidate, page_text, context)
                    parsed = validate_page_result(candidate, page_number)
                    transition_recovery = parsed.get("section_transition_recovery")
                    if transition_recovery:
                        LOG.info(
                            "Page %d section-transition recovery: %s",
                            page_number,
                            transition_recovery,
                        )
                    recovery = parsed.get("answer_key_recovery")
                    if recovery:
                        LOG.info("Page %d embedded answer-key recovery: %s", page_number, recovery)
                    break
                except Exception as exc:
                    last_error = exc
                    LOG.warning("Page %d attempt %d failed: %s", page_number, attempt, exc)
                    interaction_logger.write(
                        {
                            "event": "error",
                            "page": page_number,
                            "attempt": attempt,
                            "elapsed_seconds": round(time.monotonic() - started, 3),
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
                    if isinstance(exc, TimeoutError):
                        LOG.error(
                            "Page %d timed out after %.0fs. Not retrying immediately because "
                            "the local model server may still be generating the abandoned request. "
                            "Resume later with a larger --timeout if needed.",
                            page_number,
                            args.timeout,
                        )
                        break
                    if (
                        args.response_format == "auto"
                        and include_response_format
                        and re.search(r"HTTP (?:400|422)\b", str(exc))
                    ):
                        include_response_format = False
                        LOG.info("Server rejected response_format; retrying without it")
                    if attempt <= args.max_retries:
                        time.sleep(min(2 ** (attempt - 1), 8))
            elapsed = time.monotonic() - started
            if parsed is None:
                error_text = str(last_error or "Unknown extraction failure")
                connection.execute(
                    """
                    UPDATE pages SET status='failed', request_json=?, raw_response=?,
                        error=?, elapsed_seconds=?, extracted_at=? WHERE id=?
                    """,
                    (
                        json_compact(sanitized_request),
                        raw_api_response,
                        error_text,
                        elapsed,
                        utc_now(),
                        page_id,
                    ),
                )
                connection.commit()
                raise RuntimeError(f"Page {page_number} extraction failed: {error_text}")

            try:
                with connection:
                    cleanup_page_data(connection, source_id, page_number)
                    active_after, _ = ingest_page_result(
                        connection,
                        source_id,
                        run_id,
                        page_number,
                        page_id,
                        current_section_id,
                        parsed,
                    )
                    connection.execute(
                        """
                        UPDATE pages SET status='complete', active_section_after_id=?,
                            request_json=?, raw_response=?, parsed_json=?, error=NULL,
                            elapsed_seconds=?, extracted_at=? WHERE id=?
                        """,
                        (
                            active_after,
                            json_compact(sanitized_request),
                            raw_api_response,
                            json_compact(parsed),
                            elapsed,
                            utc_now(),
                            page_id,
                        ),
                    )
                    if active_after is not None:
                        connection.execute(
                            """
                            UPDATE sections SET source_page_end = MAX(COALESCE(source_page_end, ?), ?)
                            WHERE id = ?
                            """,
                            (page_number, page_number, active_after),
                        )
            except Exception as exc:
                connection.execute(
                    "UPDATE pages SET status='failed', error=?, extracted_at=? WHERE id=?",
                    (str(exc), utc_now(), page_id),
                )
                connection.commit()
                raise
            LOG.info(
                "Page %d complete in %.2fs: %s",
                page_number,
                elapsed,
                counts_for_page(parsed),
            )

        status = "rendered" if args.render_only else "complete"
        connection.execute(
            "UPDATE extraction_runs SET status=?, finished_at=? WHERE id=?",
            (status, utc_now(), run_id),
        )
        connection.commit()
    except Exception as exc:
        connection.execute(
            """
            UPDATE extraction_runs SET status='failed', finished_at=?, error=? WHERE id=?
            """,
            (utc_now(), str(exc), run_id),
        )
        connection.commit()
        raise
    finally:
        connection.close()

    if args.render_only:
        print(f"Rendered {len(selected_pages)} page(s) to {render_dir}")
    else:
        print(f"Extraction complete: {db_path}")
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
