#!/usr/bin/env python3
"""macOS Vision OCR adapter producing pdftotext-compatible positioned TSV."""

from __future__ import annotations

import csv
import io
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import extract_questions as core


@dataclass(frozen=True)
class Observation:
    text: str
    left: float
    top: float
    right: float
    bottom: float
    confidence: float


def ensure_binary(cache_dir: Path) -> Path:
    source = Path(__file__).with_name("vision_ocr.swift")
    binary = cache_dir / "vision_ocr"
    cache_dir.mkdir(parents=True, exist_ok=True)
    if not binary.is_file() or binary.stat().st_mtime < source.stat().st_mtime:
        core.run_command(
            [core.require_binary("swiftc"), "-O", str(source), "-o", str(binary)]
        )
    return binary


def supplement_numeric_anchors(
    image_path: Path,
    width: int,
    height: int,
    observations: list[Observation],
) -> None:
    completed = subprocess.run(
        [
            core.require_binary("tesseract"),
            image_path.name,
            "stdout",
            "-l",
            "eng",
            "--psm",
            "4",
            "tsv",
        ],
        cwd=image_path.parent,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"Tesseract numeric-anchor OCR failed: {completed.stderr.strip()}"
        )
    existing: list[tuple[str, float, float]] = []
    for item in observations:
        question_match = re.match(r"^(\d{1,3})\.\s*", item.text)
        choice_match = re.match(r"^([A-Ea-e])\)\s*", item.text)
        key = (
            f"q:{question_match.group(1)}"
            if question_match
            else f"c:{choice_match.group(1).upper()}"
            if choice_match
            else ""
        )
        if key:
            existing.append((key, (item.left + item.right) / 2, item.top))

    for row in csv.DictReader(completed.stdout.splitlines(), delimiter="\t"):
        if row.get("level") != "5":
            continue
        raw_text = str(row.get("text") or "").strip()
        question_match = re.fullmatch(r"(\d{1,3})\.", raw_text)
        choice_match = re.fullmatch(r"([A-Ea-e])\)", raw_text)
        if not question_match and not choice_match:
            continue
        key = (
            f"q:{question_match.group(1)}"
            if question_match
            else f"c:{choice_match.group(1).upper()}"
        )
        text = (
            question_match.group()
            if question_match
            else f"{choice_match.group(1).upper()})"
        )
        left = float(row["left"])
        top = float(row["top"])
        word_width = float(row["width"])
        word_height = float(row["height"])
        center = left + word_width / 2
        if any(
            existing_key == key
            and abs(other_center - center) < width * 0.03
            and abs(other_top - top) < height * 0.02
            for existing_key, other_center, other_top in existing
        ):
            continue
        observations.append(
            Observation(
                text=text,
                left=left,
                top=top,
                right=left + word_width,
                bottom=top + word_height,
                confidence=max(0.0, float(row.get("conf") or 0.0) / 100),
            )
        )
        existing.append((key, center, top))


def recognize(image_path: Path, cache_dir: Path) -> tuple[int, int, list[Observation]]:
    result = core.run_command([str(ensure_binary(cache_dir)), str(image_path)])
    rows = result.stdout.splitlines()
    if not rows or not rows[0].startswith("###PAGE###\t"):
        raise ValueError("Vision OCR returned no page geometry")
    _, width_text, height_text = rows[0].split("\t")
    width = int(width_text)
    height = int(height_text)
    observations: list[Observation] = []
    for row in rows[1:]:
        fields = row.split("\t", 5)
        if len(fields) != 6:
            raise ValueError(f"Malformed Vision OCR row: {row!r}")
        left, top, right, bottom, confidence, text = fields
        observations.append(
            Observation(
                text=text.strip(),
                left=float(left) * width,
                top=float(top) * height,
                right=float(right) * width,
                bottom=float(bottom) * height,
                confidence=float(confidence),
            )
        )
    supplement_numeric_anchors(image_path, width, height, observations)
    return width, height, observations


def positioned_tsv(
    width: int, height: int, observations: list[Observation]
) -> str:
    output = io.StringIO()
    fieldnames = [
        "level",
        "page_num",
        "block_num",
        "par_num",
        "line_num",
        "word_num",
        "left",
        "top",
        "width",
        "height",
        "conf",
        "text",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerow(
        {
            "level": "1",
            "page_num": "1",
            "block_num": "0",
            "par_num": "0",
            "line_num": "0",
            "word_num": "0",
            "left": "0",
            "top": "0",
            "width": str(width),
            "height": str(height),
            "conf": "100",
            "text": "###PAGE###",
        }
    )
    for line_number, observation in enumerate(observations, 1):
        matches = list(re.finditer(r"\S+", observation.text))
        if not matches:
            continue
        span = max(1, len(observation.text))
        line_width = max(1.0, observation.right - observation.left)
        block = 1 if (observation.left + observation.right) / 2 < width / 2 else 2
        for word_number, match in enumerate(matches, 1):
            left = observation.left + line_width * match.start() / span
            right = observation.left + line_width * match.end() / span
            if (
                block == 2
                and word_number == 1
                and re.fullmatch(r"\d{1,3}\.", match.group())
                and left < width / 2
            ):
                right += width / 2 + 2.0 - left
                left = width / 2 + 2.0
            writer.writerow(
                {
                    "level": "5",
                    "page_num": "1",
                    "block_num": str(block),
                    "par_num": "1",
                    "line_num": str(line_number),
                    "word_num": str(word_number),
                    "left": f"{left:.3f}",
                    "top": f"{observation.top:.3f}",
                    "width": f"{max(1.0, right - left):.3f}",
                    "height": f"{max(1.0, observation.bottom - observation.top):.3f}",
                    "conf": f"{observation.confidence * 100:.1f}",
                    "text": match.group(),
                }
            )
    return output.getvalue()


def plain_text(width: int, observations: list[Observation]) -> str:
    ordered = sorted(
        observations,
        key=lambda item: (
            0 if (item.left + item.right) / 2 < width / 2 else 1,
            item.top,
            item.left,
        ),
    )
    return "\n".join(item.text for item in ordered if item.text)
