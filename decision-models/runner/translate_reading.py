#!/usr/bin/env python3
"""English translations of the Text tab's reading questions (units 1 to 6) for the English reading track, by one model
through the Claude Code CLI on the Claude subscription, and the same model's flags on the questions whose answer depends
on Turkish wording. Approved by Ümit (2 November 2026): translate faithfully, keep the option letters and their order, do
not solve the question, do not add or remove information; a separate request flags dependence on Turkish wording, and
flagged questions are left out of the track.

    translate_reading.py translate OUT.jsonl [--question-ids FILE] [--workers 4]
    translate_reading.py flag TRANSLATIONS.jsonl OUT.jsonl [--workers 4]
    translate_reading.py check TRANSLATIONS.jsonl
    translate_reading.py review TRANSLATIONS.jsonl FLAGS.jsonl OUT.html [--sample 50] [--seed 20261102]
    translate_reading.py publish TRANSLATIONS.jsonl FLAGS.jsonl KEPT OUT.json

translate and flag append to OUT and skip the questions already in it, so an interrupted pass resumes. The Turkish of
each question is exactly what the runner shows a model (benchmark_ollama.load_questions and compose_prompt): its body,
everything before the options block, and each option by letter. Each record keeps the model, effort, Claude Code version,
prompt version (a hash of the system prompt, the template and the JSON schema), this file's published commit, timing and
the CLI's own output. check makes the structural checks (letters, empty texts, markup, numbers); review writes the page
Ümit or Can checks before any model run: a fixed random sample of the unflagged questions and every flagged one. publish
writes the track's public record, without question text (publish()).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import json
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import benchmark_ollama as bo

HERE = Path(__file__).resolve().parent
DATA = HERE / "questions-v2.sqlite"
READING_UNITS = [str(unit) for unit in bo.READING_UNITS]
READING_QUESTIONS = 656  # the scored reading questions of answer key version 2
MODEL = "claude-opus-5-5"
EFFORT = "high"
TIMEOUT = 600.0
ATTEMPTS = 3

TRANSLATE_SYSTEM = (
    "You translate questions from a Turkish reading comprehension exam into English for a benchmark. Translate "
    "faithfully: keep the meaning, register and level of detail of the Turkish, and do not add or remove information. Do "
    "not explain, simplify, correct or comment. Keep every option letter and the order of the options exactly as given, "
    "and translate each option on its own. Keep markup in place: put <u> and </u> around the English words that "
    "correspond to the underlined Turkish words, and keep numbering such as (I), (II), I., II. or 1., 2. where it is. Keep "
    "proper names as they are. Do not solve the question: do not say, mark or hint which option is correct. Reply only "
    "with the JSON the schema asks for."
)
TRANSLATE_TEMPLATE = (
    "Translate this Turkish multiple-choice question into English. `body` is the question text (it may contain a "
    "passage); `options` are its answer options by letter.\n\n{question}"
)
FLAG_SYSTEM = (
    "You check translated questions from a Turkish reading comprehension exam. A question depends on Turkish wording "
    "when its correct answer turns on the Turkish language itself rather than on the content: the meaning of a Turkish "
    "word, phrase or idiom; the sound of Turkish words; Turkish spelling or punctuation; or Turkish words that are "
    "underlined, numbered or otherwise marked for the question. For such a question the English version tests something "
    "different, or its keyed answer may no longer hold. Reply only with the JSON the schema asks for."
)
FLAG_TEMPLATE = (
    "Does answering this question correctly depend on Turkish wording? Below are the Turkish original, its English "
    "translation and the keyed (correct) option.\n\n{payload}"
)
FLAG_REASONS = ["word_or_phrase_meaning", "idiom", "sound", "spelling_or_punctuation", "marked_words", "other"]
FLAG_SCHEMA = {
    "type": "object",
    "properties": {
        "depends_on_turkish": {"type": "boolean"},
        "reasons": {"type": "array", "items": {"type": "string", "enum": FLAG_REASONS}},
        "explanation": {"type": "string"},
    },
    "required": ["depends_on_turkish", "reasons", "explanation"],
    "additionalProperties": False,
}
ROMAN = re.compile(r"\((?:I|II|III|IV|V|VI|VII|VIII|IX|X)\)|\b(?:I|II|III|IV|V)\.(?=\s)")
NUMBER = re.compile(r"\d+")
TURKISH_LETTERS = re.compile(r"[çğıİöşüÇĞÖŞÜ]")


def translate_schema(labels: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "body": {"type": "string"},
            "options": {"type": "object", "properties": {label: {"type": "string"} for label in labels},
                        "required": labels, "additionalProperties": False},
        },
        "required": ["body", "options"],
        "additionalProperties": False,
    }


def short_hash(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


TRANSLATE_VERSION = short_hash(TRANSLATE_SYSTEM, TRANSLATE_TEMPLATE, translate_schema(list("ABCDE")))
FLAG_VERSION = short_hash(FLAG_SYSTEM, FLAG_TEMPLATE, FLAG_SCHEMA)


def reading_questions(ids: frozenset[int] | None = None) -> list[dict[str, Any]]:
    """The reading questions as the runner shows them: id, unit, the body before the options block, the options by
    letter and the key. Without ids, all of them, which must be READING_QUESTIONS."""
    selection = bo.load_questions(DATA, READING_UNITS, None, None, 0, question_ids=ids)
    questions = []
    for question in selection.questions:
        body, separator, _ = question.prompt.rpartition("\n\n" + bo.OPTIONS_HEADING)
        if not separator or not body.strip():
            raise SystemExit(f"question {question.question_id}: no body before the options block")
        questions.append({"question_id": question.question_id, "unit": int(question.unit_number), "body": body,
                          "options": {option.label: option.text for option in question.options}, "key": question.answer})
    if ids is None and len(questions) != READING_QUESTIONS:
        raise SystemExit(f"{len(questions)} reading questions, not {READING_QUESTIONS}")
    return questions


def claude_version() -> str:
    return subprocess.run(["claude", "--version"], capture_output=True, text=True, check=True).stdout.strip()


def ask(system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    """One Claude Code request with the runner's settings (ask_claude): the given system prompt instead of the agent's,
    no tools, settings, MCP servers or saved sessions, the subscription's sign-in; its structured output and the CLI's
    whole output."""
    command = ["claude", "--print", "--model", MODEL, "--effort", EFFORT, "--output-format", "json",
               "--json-schema", json.dumps(schema, ensure_ascii=False), "--system-prompt", system,
               "--tools", "", "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence"]
    for attempt in range(bo.CLAUDE_REFRESH_RETRIES + 1):
        with tempfile.TemporaryDirectory(prefix="turkce-translate-") as temporary:
            completed = subprocess.run(command, input=prompt, cwd=temporary, capture_output=True, text=True,
                                       timeout=TIMEOUT, env=bo.claude_subscription_environment(), check=False)
        detail = completed.stderr.strip() or completed.stdout.strip()
        if completed.returncode == 0 or bo.CLAUDE_REFRESH_FAILURE not in detail or attempt == bo.CLAUDE_REFRESH_RETRIES:
            break
        time.sleep(bo.CLAUDE_REFRESH_DELAY)
    if completed.returncode != 0:
        raise RuntimeError(f"Claude Code exited with {completed.returncode}: {detail[:500]}")
    output = json.loads(completed.stdout)
    if not isinstance(output, dict) or output.get("is_error") or not isinstance(output.get("structured_output"), dict):
        raise RuntimeError(f"Claude Code gave no structured output: {completed.stdout[:500]}")
    return output


def done_ids(path: Path) -> set[int]:
    if not path.is_file():
        return set()
    return {json.loads(line)["question_id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def run_pass(items: list[dict[str, Any]], out: Path, workers: int, work: Any) -> int:
    """work(item) -> record for each item, appended to out as it finishes; the number of failures (each printed)."""
    lock = threading.Lock()
    failures = 0
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool, out.open("a", encoding="utf-8") as sink:
        futures = {pool.submit(work, item): item["question_id"] for item in items}
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            question_id = futures[future]
            try:
                record = future.result()
            except Exception as error:  # noqa: BLE001 - reported, and the question stays for the next pass
                failures += 1
                print(f"question {question_id}: failed: {error}", file=sys.stderr)
                continue
            with lock:
                sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                sink.flush()
            print(f"{count}/{len(items)} question {question_id} ({time.monotonic() - started:.0f} s)", flush=True)
    return failures


def with_retries(call: Any) -> Any:
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return call()
        except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired):
            if attempt == ATTEMPTS:
                raise
            time.sleep(10 * attempt)
    raise AssertionError("unreachable")


def provenance(version: str) -> dict[str, Any]:
    return {"model": MODEL, "effort": EFFORT, "route": "Claude Code CLI, Claude subscription", "claude_code": CLAUDE_CODE,
            "prompt_version": version, "harness_commit": COMMIT}


def translate(item: dict[str, Any]) -> dict[str, Any]:
    labels = list(item["options"])
    prompt = TRANSLATE_TEMPLATE.format(question=json.dumps({"body": item["body"], "options": item["options"]},
                                                           ensure_ascii=False, indent=2))
    started = datetime.now(timezone.utc)
    output = with_retries(lambda: ask(TRANSLATE_SYSTEM, prompt, translate_schema(labels)))
    english = output["structured_output"]
    if list(english["options"]) != labels:
        english["options"] = {label: english["options"][label] for label in labels}
    return {"question_id": item["question_id"], "unit": item["unit"], "key": item["key"],
            "turkish": {"body": item["body"], "options": item["options"]}, "english": english,
            **provenance(TRANSLATE_VERSION), "started": started.isoformat(timespec="seconds"),
            "seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1), "output": output}


def flag(record: dict[str, Any]) -> dict[str, Any]:
    payload = {"turkish": record["turkish"], "english": record["english"], "keyed_option": record["key"]}
    prompt = FLAG_TEMPLATE.format(payload=json.dumps(payload, ensure_ascii=False, indent=2))
    started = datetime.now(timezone.utc)
    output = with_retries(lambda: ask(FLAG_SYSTEM, prompt, FLAG_SCHEMA))
    return {"question_id": record["question_id"], "unit": record["unit"], **output["structured_output"],
            **provenance(FLAG_VERSION), "started": started.isoformat(timespec="seconds"),
            "seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1), "output": output}


def load_jsonl(path: Path) -> dict[int, dict[str, Any]]:
    records = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[record["question_id"]] = record
    return records


def check(path: Path) -> int:
    """Structural checks of every translation against the bank as it stands; prints each problem and each warning,
    returns the number of problems."""
    questions = {item["question_id"]: item for item in reading_questions()}
    records = load_jsonl(path)
    problems, warnings = [], []
    missing = sorted(set(questions) - set(records))
    if missing:
        problems.append(f"{len(missing)} questions not translated: {missing[:20]}")
    for question_id, record in sorted(records.items()):
        item = questions.get(question_id)
        if item is None:
            problems.append(f"{question_id}: not a reading question")
            continue
        if record["turkish"] != {"body": item["body"], "options": item["options"]}:
            problems.append(f"{question_id}: the Turkish no longer matches the bank")
        english = record["english"]
        if list(english["options"]) != list(item["options"]):
            problems.append(f"{question_id}: option letters {list(english['options'])} for {list(item['options'])}")
        texts = {"body": english["body"], **english["options"]}
        sources = {"body": item["body"], **item["options"]}
        for part, text in texts.items():
            if not text.strip():
                problems.append(f"{question_id} {part}: empty")
                continue
            source = sources[part]
            for tag in ("<u>", "</u>"):
                if source.count(tag) != text.count(tag):
                    problems.append(f"{question_id} {part}: {source.count(tag)} {tag} in Turkish, {text.count(tag)} in English")
            if sorted(ROMAN.findall(source)) != sorted(ROMAN.findall(text)):
                warnings.append(f"{question_id} {part}: numbering {ROMAN.findall(source)} became {ROMAN.findall(text)}")
            if sorted(NUMBER.findall(source)) != sorted(NUMBER.findall(text)):
                warnings.append(f"{question_id} {part}: numbers {NUMBER.findall(source)} became {NUMBER.findall(text)}")
            if len(TURKISH_LETTERS.findall(text)) > 3:
                warnings.append(f"{question_id} {part}: {len(TURKISH_LETTERS.findall(text))} Turkish letters in the English")
            ratio = len(text) / max(1, len(source))
            if not 0.5 <= ratio <= 2.5:
                warnings.append(f"{question_id} {part}: English {ratio:.2f} times the Turkish length")
    for line in problems:
        print(f"problem: {line}")
    for line in warnings:
        print(f"warning: {line}")
    print(f"{len(records)} translations, {len(problems)} problems, {len(warnings)} warnings")
    return len(problems)


def side(title: str, part: dict[str, Any], key: str) -> str:
    options = "".join(f'<li class="{"key" if label == key else ""}"><b>{label}.</b> {text}</li>'
                      for label, text in part["options"].items())
    return f'<div class="side"><h4>{title}</h4><p class="body">{part["body"]}</p><ol>{options}</ol></div>'


def review(translations: Path, flags: Path, out: Path, sample: int, seed: int) -> None:
    """The review page: a fixed random sample of the unflagged questions, then every flagged one, each with its Turkish
    and English side by side and the keyed option marked; the checker confirms the keyed answer is still right in
    English. The question bank's markup (<u>) is kept; everything else is escaped."""
    records, flagged = load_jsonl(translations), load_jsonl(flags)
    if set(flagged) != set(records):
        raise SystemExit(f"flags cover {len(flagged)} questions, translations {len(records)}")
    marked = sorted(question_id for question_id, item in flagged.items() if item["depends_on_turkish"])
    unflagged = sorted(set(records) - set(marked))
    picked = sorted(random.Random(seed).sample(unflagged, min(sample, len(unflagged))))

    def keep_markup(text: str) -> str:
        return html.escape(text).replace("&lt;u&gt;", "<u>").replace("&lt;/u&gt;", "</u>").replace("\n", "<br>")

    def block(question_id: int, kind: str) -> str:
        record = records[question_id]
        clean = {side_name: {"body": keep_markup(record[side_name]["body"]),
                             "options": {label: keep_markup(text) for label, text in record[side_name]["options"].items()}}
                 for side_name in ("turkish", "english")}
        note = ""
        if kind == "flagged":
            item = flagged[question_id]
            note = f'<p class="flag">Flagged: {html.escape(", ".join(item["reasons"]))}. {html.escape(item["explanation"])}</p>'
        return (f'<section id="q{question_id}"><h3>Question {question_id} · unit {record["unit"]} · keyed answer '
                f'{record["key"]} · {kind}</h3>{note}<div class="pair">{side("Turkish", clean["turkish"], record["key"])}'
                f'{side("English", clean["english"], record["key"])}</div><p class="ask">Is {record["key"]} still the '
                "correct answer in English? Keep / Drop</p></section>")

    style = ("body{font:15px/1.5 system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#222}"
             "section{border-top:1px solid #ccc;padding:1rem 0}.pair{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem}"
             ".key{background:#e6f4ea;font-weight:600}.flag{color:#8a4b00}.ask{color:#555;font-style:italic}"
             "ol{list-style:none;padding:0}li{margin:.2rem 0}@media(max-width:800px){.pair{grid-template-columns:1fr}}")
    head = (f"<h1>English reading: translations to check</h1><p>{len(records)} reading questions translated by {MODEL} "
            f"(effort {EFFORT}, Claude Code CLI). {len(marked)} flagged as depending on Turkish wording (left out unless "
            f"you keep them), {len(unflagged)} not flagged. Below: {len(picked)} unflagged questions drawn at random "
            f"(seed {seed}), then all {len(marked)} flagged ones. For each, please confirm the keyed answer is still "
            "correct in English; any question where it is not is dropped. Reply with the question numbers to drop "
            "(and any flagged ones to keep).</p>")
    body = "".join(block(question_id, "random") for question_id in picked) + "".join(block(question_id, "flagged") for question_id in marked)
    out.write_text(f'<!doctype html><meta charset="utf-8"><title>English reading: translations to check</title>'
                   f"<style>{style}</style>{head}{body}\n", encoding="utf-8")
    (out.with_suffix(".tsv")).write_text("question_id\tkind\tunit\tkey\tdecision\n" + "".join(
        f"{question_id}\t{kind}\t{records[question_id]['unit']}\t{records[question_id]['key']}\t\n"
        for kind, ids in (("random", picked), ("flagged", marked)) for question_id in ids), encoding="utf-8")
    print(f"wrote {out} and {out.with_suffix('.tsv')}: {len(picked)} random, {len(marked)} flagged")


def publish(translations: Path, flags: Path, kept: Path, out: Path) -> None:
    """The track's public record, without question text (the publisher owns it): the translating model and its route,
    both prompts with their versions and the commit each pass ran, the SHA-256 of the translations file as the runs
    record it (--english) and of the flags file, and per reading question its unit, whether the track keeps it, the
    flag's reasons and the SHA-256 of its English text (english_sha256). Stops unless every reading question has exactly
    one translation and one flag, each pass from one model, route and prompt version, and KEPT (the runs' --questions)
    holds exactly the unflagged questions."""
    ids = sorted(item["question_id"] for item in reading_questions())
    passes = {}
    for name, path, version in (("translate", translations, TRANSLATE_VERSION), ("flag", flags, FLAG_VERSION)):
        records = load_jsonl(path)
        lines = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        if sorted(records) != ids or lines != len(ids):
            raise SystemExit(f"{path}: {lines} records for {len(records)} questions, not one for each of the {len(ids)} reading questions")
        made = {(record["model"], record["effort"], record["route"], record["claude_code"], record["prompt_version"],
                 record["harness_commit"]) for record in records.values()}
        if len(made) != 1 or next(iter(made))[4] != version:
            raise SystemExit(f"{path}: not all from one model, route and prompt version {version}: {sorted(made)}")
        passes[name] = (records, next(iter(made)))
    texts, marks = passes["translate"][0], passes["flag"][0]
    keep = set(bo.read_question_ids(kept))
    unflagged = {question_id for question_id, mark in marks.items() if not mark["depends_on_turkish"]}
    if keep != unflagged:
        raise SystemExit(f"{kept}: {len(keep - unflagged)} flagged or unknown questions kept, {len(unflagged - keep)} unflagged left out")
    model, effort, route, claude_code, _, _ = passes["translate"][1]
    if passes["flag"][1][:4] != (model, effort, route, claude_code):
        raise SystemExit("the translations and the flags come from different models or routes")
    reasons = Counter(reason for mark in marks.values() if mark["depends_on_turkish"] for reason in mark["reasons"])
    document = {
        "translator": {"model": model, "effort": effort, "route": route, "claude_code": claude_code},
        "prompts": {
            "translate": {"version": TRANSLATE_VERSION, "harness_commit": passes["translate"][1][5], "system": TRANSLATE_SYSTEM,
                          "template": TRANSLATE_TEMPLATE, "schema": translate_schema(list("ABCDE"))},
            "flag": {"version": FLAG_VERSION, "harness_commit": passes["flag"][1][5], "system": FLAG_SYSTEM,
                     "template": FLAG_TEMPLATE, "schema": FLAG_SCHEMA},
        },
        "translations_sha256": hashlib.sha256(translations.read_bytes()).hexdigest(),
        "flags_sha256": hashlib.sha256(flags.read_bytes()).hexdigest(),
        "english_sha256": "each question's `english` object (body and options) as JSON with sorted keys, no spaces and "
                          "non-ASCII characters kept, hashed with SHA-256",
        "reading_questions": len(ids),
        "kept": len(keep),
        "flagged": len(ids) - len(keep),
        "reasons": {reason: reasons[reason] for reason in FLAG_REASONS if reasons[reason]},
        "questions": [
            {
                "question_id": question_id,
                "unit": texts[question_id]["unit"],
                "kept": question_id in keep,
                "reasons": marks[question_id]["reasons"] if marks[question_id]["depends_on_turkish"] else [],
                "english_sha256": hashlib.sha256(json.dumps(texts[question_id]["english"], ensure_ascii=False, sort_keys=True,
                                                            separators=(",", ":")).encode("utf-8")).hexdigest(),
            }
            for question_id in ids
        ],
    }
    out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{out}: {len(ids)} reading questions, {len(keep)} kept, {len(ids) - len(keep)} flagged")


def main() -> int:
    global CLAUDE_CODE, COMMIT
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("translate")
    one.add_argument("out", type=Path)
    one.add_argument("--question-ids", type=Path)
    one.add_argument("--workers", type=int, default=4)
    two = sub.add_parser("flag")
    two.add_argument("translations", type=Path)
    two.add_argument("out", type=Path)
    two.add_argument("--workers", type=int, default=4)
    three = sub.add_parser("check")
    three.add_argument("translations", type=Path)
    four = sub.add_parser("review")
    four.add_argument("translations", type=Path)
    four.add_argument("flags", type=Path)
    four.add_argument("out", type=Path)
    four.add_argument("--sample", type=int, default=50)
    four.add_argument("--seed", type=int, default=20261102)
    five = sub.add_parser("publish")
    five.add_argument("translations", type=Path)
    five.add_argument("flags", type=Path)
    five.add_argument("kept", type=Path)
    five.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.command == "check":
        return 1 if check(args.translations) else 0
    if args.command == "review":
        review(args.translations, args.flags, args.out, args.sample, args.seed)
        return 0
    if args.command == "publish":
        publish(args.translations, args.flags, args.kept, args.out)
        return 0
    COMMIT = bo.harness_commit(Path(__file__).resolve())  # stops unless this file is committed and pushed
    CLAUDE_CODE = claude_version()
    if args.command == "translate":
        ids = bo.read_question_ids(args.question_ids) if args.question_ids else None
        items = [item for item in reading_questions(ids) if item["question_id"] not in done_ids(args.out)]
        print(f"translating {len(items)} questions with {MODEL} ({EFFORT}), prompt version {TRANSLATE_VERSION}, {COMMIT[:9]}")
        return 1 if run_pass(items, args.out, args.workers, translate) else 0
    records = load_jsonl(args.translations)
    items = [record for question_id, record in sorted(records.items()) if question_id not in done_ids(args.out)]
    print(f"flagging {len(items)} questions with {MODEL} ({EFFORT}), prompt version {FLAG_VERSION}, {COMMIT[:9]}")
    return 1 if run_pass(items, args.out, args.workers, flag) else 0


CLAUDE_CODE = ""
COMMIT = ""

if __name__ == "__main__":
    sys.exit(main())
