#!/usr/bin/env python3
"""Turn an extracted copy of this site into what may be published, then check it.

No bench publishes its questions (Ümit #10760, #10764; Zeki #11139, #11168, #11435, #11470): for the Reading bench, the
public site carries nothing a reader could rebuild the answer key from or find a question in the book by. Per question it
holds no key letter, no book locator (page, printed number, topic, passage), no letter a model picked, no option
probabilities, no score of the chosen option and no question ID: the IDs (44 to 4231) were assigned in book order, so
they locate questions too. What stays: every run's record (run id, settings, timings, costs) and, per question in a
fixed order with no question ID beside it, whether the run's answer was right, wrong or missing.

Usage: publish_projection.py DIR

DIR is a copy of this folder (push_pages.sh extracts the page commit into one before copying it to the mirror). In DIR
only, each file that holds answers or question IDs is replaced by its projection under the same name, the pages and
scripts per question are deleted (DROPPED), and the guard reads every file left in DIR: it exits 1 with the list of
what survived when anything per question does. The originals here, with every pick, probability and ID, stay what
build_site.py, export_results.py and reproduce.py read.

A run's answers become one string, `outcome`, a character per question in the file's question order:
R right, W wrong, I the "I don't know" option, N no valid answer (counted wrong), . not asked.
A list of question IDs becomes its summary, {"questions": its length}, with "sha256" (fingerprint) when it holds at
least MIN_FINGERPRINT IDs: too few to be guessed back from the 2,210 IDs.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

ANSWERS = "answers.json"
# The "I don't know" option's letter in a run with it (reproduce.py DONT_KNOW_LETTER): always the sixth, after A to E.
DONT_KNOW_LETTER = "F"
# What a run record loses: its picks, their grades (kept as `outcome`), each pick's score and the option probabilities.
RUN_FIELDS = ("choice", "correct", "score", "probabilities")
# Of answers.json's question columns only the key audit's status stays (null, verified, suspect, excluded), in question
# order: it tells which questions are scored. The IDs, topics, pages, printed numbers, keys and passages go.
QUESTION_COLUMNS_KEPT = ("status",)
# A book locator or key beside a question ID, in vision.json's and english-reading.json's per-question entries, and the
# crop file named after the question's ID.
LOCATORS = ("page", "number", "unit", "topic", "test", "passage", "key", "file")
# A question's ID under its own name: the key goes wherever it stands.
ID_FIELDS = ("question_id", "question_ids", "qid", "qids")
# Lists of question IDs by their key (results.json's answer_key.excluded, high_confidence…wrong_questions and the web
# grounding searches' ids; web-grounding.json's searches; page_config.json's structural_check.problem_questions; the
# runner's pipeline splits): each becomes its summary (id_summary).
ID_LISTS = ("ids", "question_ids", "wrong_questions", "excluded", "problem_questions", "calibration", "held_out", "routed",
            "passed", "shared_words", "publisher", "source_book", "kept", "flagged")
# The smallest list of IDs given a fingerprint: C(2210, 20) is about 10^47 guesses.
MIN_FINGERPRINT = 20
# Keys whose integers are run ids, not question IDs (the two ranges overlap).
RUN_KEY = re.compile(r"(^|_)runs?$|^run_id$|repeat_set$|compared_runs$|^repeat_check$")
# Pages and scripts whose purpose is each question's answers; the build no longer writes them or links to them.
DROPPED = ("question", "questions", "disagreements", "question.js", "questions.js")


def outcome(choice: Any, correct: Any, dont_know: bool, where: str) -> str:
    if correct is None:
        if choice is not None:
            raise SystemExit(f"{where}: a pick without a grade")
        return "."
    if not (isinstance(choice, str) and len(choice) == 1):
        if correct:
            raise SystemExit(f"{where}: no valid pick, graded right")
        return "N"
    if choice == DONT_KNOW_LETTER and dont_know:
        if correct:
            raise SystemExit(f"{where}: the \"I don't know\" option graded right")
        return "I"
    return "R" if correct else "W"


def is_run(item: Any) -> bool:
    return isinstance(item, dict) and isinstance(item.get("choice"), list) and isinstance(item.get("correct"), list)


def project_run(run: dict[str, Any], where: str, removed: Counter) -> dict[str, Any]:
    """The run record without RUN_FIELDS, with `outcome` where `choice` stood."""
    choices, grades = run["choice"], run["correct"]
    if len(choices) != len(grades):
        raise SystemExit(f"{where}: {len(choices)} picks, {len(grades)} grades")
    dont_know = bool(run.get("dont_know"))
    out: dict[str, Any] = {}
    for key, value in run.items():
        if key == "choice":
            out["outcome"] = "".join(outcome(choice, grade, dont_know, f"{where}, question {index}")
                                     for index, (choice, grade) in enumerate(zip(choices, grades)))
        if key in RUN_FIELDS:
            removed[f"runs[].{key}"] += 1
            continue
        out[key] = value
    return out


def project_answers(doc: dict[str, Any], name: str, removed: Counter) -> dict[str, Any]:
    """answers.json or a file of its sections: each run record projected; answers.json's question columns cut to
    QUESTION_COLUMNS_KEPT."""
    out: dict[str, Any] = {}
    for key, value in doc.items():
        if key == "questions" and isinstance(value, dict):
            for column in value:
                if column not in QUESTION_COLUMNS_KEPT:
                    removed[f"questions.{column}"] += 1
            out[key] = {column: value[column] for column in QUESTION_COLUMNS_KEPT}
        elif isinstance(value, list) and value and all(is_run(item) for item in value):
            out[key] = [project_run(run, f"{name} {key} run {run.get('run')}", removed) for run in value]
        else:
            out[key] = value
    return out


def answer_map_outcome(answers: dict[str, Any], order: list[str], where: str, removed: Counter) -> str:
    """vision.json's answers of one cell, {question ID: [pick, option probabilities, grade]}, as an outcome string in
    the subset's order."""
    unknown = set(answers) - set(order)
    if unknown:
        raise SystemExit(f"{where}: questions outside the subset: {sorted(unknown, key=int)[:5]}")
    removed["answers{question id: [pick, probabilities, grade]}"] += 1
    return "".join(outcome(answers[qid][0], answers[qid][2], False, f"{where}, question {qid}") if qid in answers else "."
                   for qid in order)


def strip_locators(item: Any, removed: Counter, path: str = "") -> Any:
    """Every dict that names a question_id loses LOCATORS."""
    if isinstance(item, dict):
        named = "question_id" in item
        out = {}
        for key, value in item.items():
            if named and key in LOCATORS:
                removed[f"{path}[question_id].{key}"] += 1
                continue
            out[key] = strip_locators(value, removed, f"{path}.{key}" if not key.isdigit() else path)
        return out
    if isinstance(item, list):
        return [strip_locators(value, removed, path + "[]") for value in item]
    return item


def subset_order(ids: list[int]) -> list[str]:
    if ids != sorted(ids):
        raise SystemExit("vision.json: subset.question_ids is not in ascending order")
    return [str(qid) for qid in ids]


def project_vision(doc: dict[str, Any], name: str, removed: Counter) -> dict[str, Any]:
    """vision.json: each cell's answers, and the engine check's, as outcome strings in the subset's (ascending) question
    order; the subset's question IDs and per-question reasons go (their counts stay); locators beside a question_id
    go."""
    order = subset_order(doc["subset"]["question_ids"])
    doc = strip_locators(doc, removed)
    subset = doc["subset"]
    for key in ("question_ids", "reasons"):
        subset.pop(key)
        removed[f"subset.{key}"] += 1
    doc["answers"] = {cell: answer_map_outcome(answers, order, f"{name} {cell}", removed)
                      for cell, answers in doc["answers"].items()}
    for check in doc["engine_checks"]:
        check["answers"] = answer_map_outcome(check["answers"], order, f"{name} engine check {check['name']}", removed)
    return doc


def project_vision_repeats(doc: dict[str, Any], name: str, removed: Counter, order: list[str]) -> dict[str, Any]:
    """vision-repeats.json: each pass's answers as an outcome string, in vision.json's subset order."""
    doc = strip_locators(doc, removed)
    for cell in doc["cells"]:
        for passed in cell["passes"]:
            passed["answers"] = answer_map_outcome(passed["answers"], order, f"{name} {cell['name']} pass {passed['pass']}",
                                                   removed)
    return doc


def project_english_reading(doc: dict[str, Any], name: str, removed: Counter) -> dict[str, Any]:
    """english-reading.json: each question's flags and English hash stay, in the order of the book; its topic goes (its
    ID goes with project_ids)."""
    return strip_locators(doc, removed)


# ---------------------------------------------------------------- question IDs

class Known:
    """The private answer files' question IDs and run ids (run ids and question IDs share a range, so a number alone
    cannot tell them apart)."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.ids = set(answers["questions"]["id"])
        self.runs = {run["run"] for value in answers.values() if isinstance(value, list)
                     for run in value if isinstance(run, dict) and isinstance(run.get("run"), int)}

    @classmethod
    def of_tree(cls, root: Path) -> "Known":
        """From answers.json and the files it lists, before they are projected."""
        answers = json.loads((root / ANSWERS).read_bytes())
        if "id" not in answers.get("questions", {}):
            raise SystemExit(f"{root / ANSWERS}: no question IDs; not an unprojected tree")
        for name in answers.get("files", {}):
            answers.update({key: value for key, value in json.loads((root / name).read_bytes()).items()
                            if key not in answers})
        return cls(answers)

    def question_list(self, numbers: list[int]) -> bool:
        """Numbers that are question IDs and not all run ids."""
        return bool(numbers) and all(n in self.ids for n in numbers) and not all(n in self.runs for n in numbers)

    def named_list(self, numbers: list[int]) -> bool:
        """Numbers under an ID_LISTS key: question IDs, whether or not some run has the same number."""
        return bool(numbers) and all(n in self.ids for n in numbers)


def fingerprint(ids: list[int]) -> str:
    """SHA-256 of the sorted IDs as compact JSON ("[44,45,…]")."""
    return hashlib.sha256(json.dumps(sorted(ids), separators=(",", ":")).encode()).hexdigest()


def id_summary(ids: list[int]) -> dict[str, Any]:
    return {"questions": len(ids), **({"sha256": fingerprint(ids)} if len(ids) >= MIN_FINGERPRINT else {})}


ID = r"\d{2,4}"
ID_RUN = rf"{ID}(?:(?:,\s*(?:and\s+)?|\s+and\s+){ID})*"
# "four questions (IDs 292, 3219, 3243 and 3287)", "2 of the 763 questions (3355 and 4019)", "1 question (3043)"
PARENTHESISED = re.compile(rf"\b(questions?)\s*\((?:IDs?\s+)?({ID_RUN})\)")
SAME_QUESTION = re.compile(rf"\bquestion ({ID}) each time")
SINGLE = re.compile(rf"\bquestion\s+(?:IDs?\s+)?({ID})\b")
NAMED_IDS = re.compile(rf"\bIDs?\s+({ID_RUN})")
CROP_FILE = re.compile(rf"(?:^|/)({ID})-question\.[a-z]+\b")


def numbers(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", text)]


def redact(text: str, known: Known) -> str:
    """A text without the question IDs it names: a parenthesised list after "question(s)" goes, "question N each time"
    reads "the same question each time". Any other mention is left for the guard to report."""
    text = PARENTHESISED.sub(lambda m: m.group(1) if known.question_list(numbers(m.group(2))) else m.group(0), text)
    return SAME_QUESTION.sub(lambda m: "the same question each time" if int(m.group(1)) in known.ids else m.group(0), text)


def project_ids(item: Any, known: Known, removed: Counter, path: str = "$") -> Any:
    """Every ID field (ID_FIELDS) goes, every list of IDs under an ID_LISTS key becomes its summary, and every string is
    redacted."""
    if isinstance(item, dict):
        out = {}
        for key, value in item.items():
            where = f"{path}.{key}" if not key.isdigit() else f"{path}{{}}"
            if key in ID_FIELDS:
                removed[where] += 1
                continue
            if (key in ID_LISTS and isinstance(value, list) and all(isinstance(n, int) for n in value)
                    and known.named_list(value)):
                removed[f"{where} (ID list -> summary)"] += 1
                out[key] = id_summary(value)
                continue
            out[key] = project_ids(value, known, removed, where)
        return out
    if isinstance(item, list):
        return [project_ids(value, known, removed, path + "[]") for value in item]
    if isinstance(item, str):
        public = redact(item, known)
        if public != item:
            removed[f"{path} (IDs in text)"] += 1
        return public
    return item


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def public_markdown(text: str, known: Known, removed: Counter | None = None) -> str:
    """A Markdown file without its tables' Question ID column (key-changelog.md) and with its text redacted."""
    removed = Counter() if removed is None else removed
    out, drop = [], None
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("|"):
            cells = table_cells(line)
            if drop is None:
                drop = next((index for index, cell in enumerate(cells) if cell.lower() == "question id"), -1)
            if drop >= 0:
                removed["table column Question ID (cells)"] += 1
                del cells[drop]
                line = "| " + " | ".join(cells) + " |\n"
        else:
            drop = None
        out.append(line)
    public = redact("".join(out), known)
    if public != "".join(out):
        removed["IDs in text"] += 1
    return public


def id_lines(text: str, known: Known) -> list[int] | None:
    """The IDs of a plain list of question IDs (one per line, # comments), else None."""
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) < 5 or not all(re.fullmatch(r"\d+", line) for line in lines):
        return None
    values = [int(line) for line in lines]
    return values if known.question_list(values) else None


def public_text(text: str, known: Known, removed: Counter) -> str | None:
    """A plain list of question IDs as its summary line; None for any other text."""
    values = id_lines(text, known)
    if values is None:
        return None
    removed["question IDs, one per line (-> summary)"] += len(values)
    summary = id_summary(values)
    return (f"# {summary['questions']:,} question IDs; the list stays private (no bench publishes its questions)."
            + (f" SHA-256 of the sorted IDs as compact JSON ([44,45,...]): {summary['sha256']}" if "sha256" in summary else "")
            + "\n")


def dumps_like(original: bytes, doc: Any) -> bytes:
    """JSON in the original file's layout: compact, or indented as it was (its first line break and the spaces after
    it); UTF-8 kept as it is."""
    if original[1:2] == b"\n":
        indent = len(original[2:]) - len(original[2:].lstrip(b" "))
        return (json.dumps(doc, ensure_ascii=False, indent=indent) + ("\n" if original.endswith(b"\n") else "")).encode()
    return (json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + ("\n" if original.endswith(b"\n") else "")).encode()


def projections(root: Path) -> dict[str, Callable[[dict[str, Any], Counter], dict[str, Any]]]:
    """The files with answers per question, by path in the site, each with the function that projects its document
    (project_ids then runs on every JSON file)."""
    out: dict[str, Callable[[dict[str, Any], Counter], dict[str, Any]]] = {}
    answers = root / ANSWERS
    if answers.exists():
        out[ANSWERS] = lambda doc, removed: project_answers(doc, ANSWERS, removed)
        for name in json.loads(answers.read_bytes()).get("files", {}):
            out[name] = lambda doc, removed, name=name: project_answers(doc, name, removed)
    if (root / "vision.json").exists():
        out["vision.json"] = lambda doc, removed: project_vision(doc, "vision.json", removed)
        if (root / "vision-repeats.json").exists():
            order = subset_order(json.loads((root / "vision.json").read_bytes())["subset"]["question_ids"])
            out["vision-repeats.json"] = lambda doc, removed: project_vision_repeats(doc, "vision-repeats.json", removed, order)
    if (root / "english-reading.json").exists():
        out["english-reading.json"] = lambda doc, removed: project_english_reading(doc, "english-reading.json", removed)
    return out


def public_bytes(name: str, original: bytes, known: Known, project: Callable | None, removed: Counter) -> bytes | None:
    """A file as it is published, or None when it is published as it is."""
    suffix = Path(name).suffix
    if suffix == ".json":
        doc = json.loads(original)
        if project is not None:
            doc = project(doc, removed)
        doc = project_ids(doc, known, removed)
        return dumps_like(original, doc) if removed else None
    if suffix in (".md", ".txt"):
        text = original.decode("utf-8")
        public = public_text(text, known, removed) if suffix == ".txt" else public_markdown(text, known, removed)
        return public.encode() if public is not None and public != text else None
    return None


def public_sizes(root: Path, names: list[str]) -> dict[str, int]:
    """Each named file's size as it is published (the Data page's sizes, sitebuild/data.py)."""
    found, known = projections(root), Known.of_tree(root)
    out = {}
    for name in names:
        original = (root / name).read_bytes()
        public = public_bytes(name, original, known, found.get(name), Counter())
        out[name] = len(original if public is None else public)
    return out


# ---------------------------------------------------------------- the guard
# Each rule names what it found and where; any finding fails the publication.
LETTER = re.compile(r"[A-F]")
LETTER_RUN = re.compile(r"(?<![A-Za-z0-9+/=_-])[A-F-]{40,}(?![A-Za-z0-9+/=_-])")
PER_QUESTION = 20  # a list or map this long holds one entry per question (the smallest topic has 3; the runs, 138)
PER_QUESTION_KEYS = {"choice", "choices", "pick", "picks", "probabilities", "score", "scores"}
LOCATOR_COLUMNS = {"key", "keys", "page", "pages", "number", "unit", "passage", "topic", "printed"}
FORBIDDEN_LABELS = ("Answer key", "Page", "Number", "Pick", "Printed number", "Page in the book", "Question ID", "ID")
ID_LIST_MIN = 5  # an unnamed list or map of this many question IDs (and not all run ids) is an ID list


def letters_share(values: list[Any]) -> float:
    present = [value for value in values if value is not None]
    return sum(isinstance(value, str) and len(value) == 1 and bool(LETTER.fullmatch(value)) for value in present) / len(present) if present else 0.0


def probability_vector(value: Any) -> bool:
    return (isinstance(value, dict) and len(value) >= 2 and all(LETTER.fullmatch(key) for key in value)
            and all(isinstance(number, float) or number in (0, 1) for number in value.values() if number is not None))


def text_ids(text: str, known: Known) -> list[str]:
    """The question IDs a text names: after "question(s) (", "question N", "ID(s) N, M", or in a crop's file name."""
    found = []
    for match in PARENTHESISED.finditer(text):
        if known.question_list(numbers(match.group(2))):
            found.append(match.group(0))
    for match in SINGLE.finditer(text):
        if int(match.group(1)) in known.ids:
            found.append(match.group(0))
    for match in NAMED_IDS.finditer(text):
        if known.question_list(numbers(match.group(1))):
            found.append(match.group(0))
    for match in CROP_FILE.finditer(text):
        if int(match.group(1)) in known.ids:
            found.append(match.group(0))
    return found


def guard_json(doc: Any, name: str, found: list[str], known: Known) -> None:
    vectors = 0
    stack: list[tuple[str, str, Any]] = [("$", "", doc)]
    while stack:
        path, key_of, item = stack.pop()
        if isinstance(item, dict):
            if probability_vector(item):
                vectors += 1
                continue
            if "question_id" in item and set(LOCATORS).intersection(item):
                found.append(f"{name}: {path} names a question_id beside {sorted(set(LOCATORS).intersection(item))}")
            numeric = len(item) >= PER_QUESTION and all(key.isdigit() for key in item)
            if (len(item) >= ID_LIST_MIN and all(key.isdigit() for key in item) and not RUN_KEY.search(key_of)
                    and known.question_list([int(key) for key in item])):
                found.append(f"{name}: {path} is keyed by question IDs ({len(item)})")
            for key, value in item.items():
                where = f"{path}{{id}}" if numeric else f"{path}.{key}"
                if key in ID_FIELDS:
                    found.append(f"{name}: {where} is a question ID field")
                ints = isinstance(value, list) and value and all(isinstance(n, int) and not isinstance(n, bool) for n in value)
                if ints and key in ID_LISTS and known.named_list(value):
                    found.append(f"{name}: {where} is a list of question IDs ({len(value)})")
                elif ints and len(value) >= ID_LIST_MIN and not RUN_KEY.search(key) and known.question_list(value):
                    found.append(f"{name}: {where} is an unnamed list of question IDs ({len(value)})")
                if isinstance(value, list) and len(value) >= PER_QUESTION:
                    if key in PER_QUESTION_KEYS:
                        found.append(f"{name}: {where} is a list per question ({len(value)})")
                    elif key in LOCATOR_COLUMNS:
                        found.append(f"{name}: {where} is a locator or key column ({len(value)})")
                if numeric and isinstance(value, list) and value and isinstance(value[0], str) and LETTER.fullmatch(value[0]):
                    found.append(f"{name}: {path} maps question IDs to picks")
                    break
                stack.append((where, key, value))
        elif isinstance(item, list):
            if len(item) >= PER_QUESTION and letters_share(item) >= 0.5:
                found.append(f"{name}: {path} is a list of letters ({len(item)})")
                continue
            stack.extend((f"{path}[]", key_of, value) for value in item)
        elif isinstance(item, str):
            if len(item) >= PER_QUESTION and re.fullmatch(r"[A-F-]+", item) and len(set(item) - {"-"}) >= 2:
                found.append(f"{name}: {path} is a string of picks or keys ({len(item)})")
            for mention in text_ids(item, known):
                found.append(f"{name}: {path} names question IDs ({mention!r})")
    if vectors:
        found.append(f"{name}: {vectors:,} option probability maps")


def dropped_target(href: str, page: Path, root: Path) -> str | None:
    """The dropped page or script an internal link points to, else None."""
    if re.match(r"[a-z]+:|//|#", href):
        return None
    target = (page.parent / href.split("#")[0].split("?")[0]).resolve()
    try:
        first = target.relative_to(root.resolve()).parts[:1]
    except ValueError:
        return None
    return first[0] if first and first[0] in DROPPED else None


def guard_html(text: str, page: Path, root: Path, name: str, found: list[str], known: Known) -> None:
    for href in re.findall(r'(?:href|src)="([^"]*)"', text):
        target = dropped_target(href, page, root)
        if target:
            found.append(f"{name}: links to the dropped {target} ({href})")
    for label in FORBIDDEN_LABELS:
        if f'data-label="{label}"' in text or re.search(rf'<th[^>]*>{re.escape(label)}</th>', text):
            found.append(f"{name}: a table column {label!r}")
    for run in LETTER_RUN.findall(text):
        if len(set(run) - {"-"}) >= 2:
            found.append(f"{name}: a run of {len(run)} answer letters")
    # The page's text, each tag a cell break, so that a table's "per question" and the next cell's number never join.
    for mention in text_ids(re.sub(r"<[^>]+>", " | ", text), known):
        found.append(f"{name}: names question IDs ({mention!r})")


def guard_markdown(text: str, name: str, found: list[str], known: Known) -> None:
    """A table with a Question ID column (key-changelog.md's rows), or a table of key changes with a locator or the
    answers in its columns; IDs in the text."""
    columns = {"topic", "page", "test", "number", "old answer", "new answer"}
    for line in text.splitlines():
        cells = {cell.lower() for cell in table_cells(line)}
        if line.lstrip().startswith("|") and ("question id" in cells or ("change" in cells and cells & columns)):
            found.append(f"{name}: a table of questions with {sorted(cells & (columns | {'question id'}))}")
    for mention in text_ids(text, known):
        found.append(f"{name}: names question IDs ({mention!r})")


def guard(root: Path, known: Known) -> list[str]:
    found: list[str] = []
    for name in DROPPED:
        if (root / name).exists():
            found.append(f"{name}: still in the tree")
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        name = path.relative_to(root).as_posix()
        if path.suffix == ".json":
            try:
                doc = json.loads(path.read_bytes())
            except (ValueError, UnicodeDecodeError) as error:
                found.append(f"{name}: not JSON ({error})")
                continue
            guard_json(doc, name, found, known)
        elif path.suffix == ".html":
            guard_html(path.read_text(encoding="utf-8", errors="replace"), path, root, name, found, known)
        elif path.suffix == ".md":
            guard_markdown(path.read_text(encoding="utf-8", errors="replace"), name, found, known)
        elif path.suffix in (".txt", ".js"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if id_lines(text, known) is not None:
                found.append(f"{name}: a list of question IDs, one per line")
            for mention in text_ids(text, known):
                found.append(f"{name}: names question IDs ({mention!r})")
    return found


def size_text(size: int) -> str:
    return f"{size / 1e6:.1f} MB" if size >= 1e6 else f"{size / 1e3:.1f} kB"


def main() -> int:
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        print(__doc__.split("\n\n")[2], file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    if (root / ".git").exists():
        print(f"{root}: a working copy, not an extracted tree; nothing rewritten", file=sys.stderr)
        return 2
    known = Known.of_tree(root)
    found_projections = projections(root)
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in (".json", ".md", ".txt"):
            continue
        name = path.relative_to(root).as_posix()
        original = path.read_bytes()
        removed: Counter = Counter()
        public = public_bytes(name, original, known, found_projections.get(name), removed)
        if public is None:
            continue
        path.write_bytes(public)
        fields = ", ".join(f"{field} ×{count:,}" for field, count in sorted(removed.items()))
        print(f"projected {name}: {size_text(len(original))} -> {size_text(len(public))}; removed {fields}")
        print(f"  sha256 {hashlib.sha256(public).hexdigest()}  {name}")
    for name in DROPPED:
        path = root / name
        if path.is_dir():
            shutil.rmtree(path)
            print(f"dropped {name}/")
        elif path.exists():
            path.unlink()
            print(f"dropped {name}")
    found = guard(root, known)
    if found:
        print(f"GUARD: {len(found):,} finding(s); not publishable:", file=sys.stderr)
        for line, count in Counter(found).items():
            print(f"  {line}" + (f" (×{count:,})" if count > 1 else ""), file=sys.stderr)
        return 1
    print("guard: no key, locator, pick, probability, chosen-option score or question ID per question in the tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
