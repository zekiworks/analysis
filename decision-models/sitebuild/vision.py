"""Page images (vision/), the site's second tab: the questions that point at underlined or numbered words on
the printed page, asked as text (A), as a picture of the page only (B), as both (C) and as each OCR model's reading of the
picture (D), from vision.json. vision.json holds aggregate numbers and each answer's pick and option probabilities; no
question text, picture or OCR text. Under one line, the charts, the leaderboards and the OCR models' table; Info holds
what we found and the method. The longer intro and the four inputs drawn on a sample question written for the page
(inputs_sample) are in About's notes on each page (Site.note).

The leaderboard keeps decision models and other models apart (page_config.json's rule, Site.decision), and within each,
the image models ranked by B, then the text-only models ranked by their best OCR route. A condition vision.json does not
hold reads "Not available" with its reason from the model's "missing"; a row without the result it is ranked by follows
the ranked rows, in vision.json's order. model_table() also gives a model page its row. findings() puts the results in
words, computed from vision.json when the site is built. Every model here is a decision model (the build stops
otherwise), so the models' charts, tables and findings show for the view bar's all and decision groups (data-models)
and the chat group shows a note instead. The small group gets its own leaderboard (small_board) and the charts' rows of
the small models; the charts without one and the findings, which cover every model, give way to a note there. The OCR
models' parts show in every group."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import build_page as bp
from sitebuild.site import (DECISION_ONLY, ROOT, Site, chat_note, esc, hbars, interval, more_link, pct, rank_fill, rel,
                            shown, small_note)

PATH = "vision/"
OCR_NAMES = {
    "chandra-ocr-2": "Chandra OCR 2",
    "dots-mocr": "dots.mocr",
    "surya-ocr-2": "Surya OCR 2",
    "unlimited-ocr-2": "Baidu Unlimited-OCR-2",
}
# The leaderboard's columns after the model: condition (None for the best OCR route) and header.
COLUMNS = (("A", "A · text only"), ("B", "B · image only"), ("C", "C · text plus image"), (None, "Best OCR route"))
# What each leaderboard column measures and which way is better, under its header (and beside a phone's stacked cell).
DIRECTION = "accuracy, higher is better"
NOT_AVAILABLE = "Not available"
NO_IMAGE = '<span class="nm">No image input</span>'


def cell(label: str, content: str) -> str:
    """A number cell; on a phone, the table stacks each row and the cell shows its label (header and direction)."""
    return f'<td class="num" data-label="{esc(label)}"><span class="cell">{content}</span></td>'


def ocr_labels(data: dict[str, Any]) -> list[str]:
    """The D conditions, one per OCR model: "D chandra-ocr-2"."""
    return [f"D {key}" for key in data["ocr"]["models"]]


def best_route(data: dict[str, Any], model: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """The D condition with the highest accuracy among those measured (the first in vision.json's order on a tie), with
    its metrics; None when no D condition was measured."""
    measured = [(label, model["conditions"][label]) for label in ocr_labels(data) if label in model["conditions"]]
    return max(measured, key=lambda item: item[1]["accuracy"]) if measured else None


def accuracy_cell(head: str, got: dict[str, Any], route: str = "") -> str:
    """Accuracy on the questions with its 95% interval (Wilson, as everywhere on the site) and, for the best OCR route,
    the OCR model."""
    via = f'<span class="small">via {esc(route)}</span>' if route else ""
    return cell(f"{head} ({DIRECTION})",
                f'{pct(got["accuracy"])}{via}<span class="small">{interval(got["correct"], got["questions"])}</span>')


def unavailable_cell(model: dict[str, Any], head: str, labels: list[str]) -> str:
    """A condition not measured: "Not available" with its reason (vision.json's missing), never a number."""
    missing = model.get("missing") or {}
    absent = [label for label in labels if label not in missing]
    if absent:
        raise ValueError(f"vision.json: {model['name']} has no result and no reason for {', '.join(absent)}")
    reasons = "; ".join(dict.fromkeys(missing[label] for label in labels))
    return cell(f"{head} ({DIRECTION})", f'<span class="nm">{NOT_AVAILABLE}: {esc(reasons)}</span>')


def cells(data: dict[str, Any], model: dict[str, Any]) -> str:
    """A model's A, B, C and best OCR route cells; a text-only model has no image input for B and C."""
    conditions = model["conditions"]
    out = []
    for label, head in COLUMNS:
        if label is None:
            best = best_route(data, model)
            if best is None:
                out.append(unavailable_cell(model, head, ocr_labels(data)))
                continue
            route, got = best
            run = sum(item in conditions for item in ocr_labels(data))
            of = "" if run == len(ocr_labels(data)) else f", best of the {run} of {len(ocr_labels(data))} OCR models run"
            out.append(accuracy_cell(head, got, OCR_NAMES[route.removeprefix("D ")] + of))
        elif model["kind"] == "text" and label in ("B", "C"):
            out.append(cell(f"{head} ({DIRECTION})", NO_IMAGE))
        elif label in conditions:
            out.append(accuracy_cell(head, conditions[label]))
        else:
            out.append(unavailable_cell(model, head, [label]))
    return "".join(out)


def shown_names(site: Site, models: list[dict[str, Any]]) -> dict[int, str]:
    """The models' names where they show together, by condition A's run (site.names over their Text tab setups)."""
    return site.names([site.by_id[model["a_run"]] for model in models if model["a_run"] in site.by_id])


def model_cell(site: Site, origin: str, model: dict[str, Any], shown: dict[int, str]) -> str:
    """The model, linked to the page of its Text tab setup (condition A's run) when the Text tab has it, named as shown
    gives it, its settings in the tooltip."""
    run = site.by_id.get(model["a_run"])
    if run is None:
        return (f'<td class="model"><span class="model-name">{esc(model["name"])}</span>'
                '<span class="small">Not on the Text tab</span></td>')
    detail = site.detail(run)
    tip = f' title="{esc(detail)}"' if detail else ""
    return (f'<td class="model"{tip}><a class="model-name" href="{rel(origin, site.model_path(run))}">'
            f'{esc(shown[run["run"]])}</a></td>')


def model_table(site: Site, origin: str, data: dict[str, Any], models: list[dict[str, Any]]) -> str:
    """The leaderboard's columns for these models, in this order; every header says which way is better."""
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{DIRECTION}</span></th>' for _, name in COLUMNS)
    shown = shown_names(site, models)
    rows = "".join(f"<tr>{model_cell(site, origin, model, shown)}{cells(data, model)}</tr>" for model in models)
    return (f'<div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">Model</th>{head}</tr></thead>'
            f"<tbody>{rows}</tbody></table></div>")


def ranked(models: list[dict[str, Any]], result: Callable[[dict[str, Any]], dict[str, Any] | None]) -> tuple[list, list]:
    """The models with the result they are ranked by, highest accuracy first, and those without it, in vision.json's
    order."""
    have = [model for model in models if result(model) is not None]
    return sorted(have, key=lambda model: -result(model)["accuracy"]), [model for model in models if result(model) is None]


def names(models: list[dict[str, Any]]) -> str:
    items = [model["name"] for model in models]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def group(site: Site, data: dict[str, Any], models: list[dict[str, Any]], kind: str) -> str:
    """One group of a leaderboard: the image models ranked by B, or the text-only models ranked by their best OCR route;
    the rows without that result follow, unranked."""
    if kind == "image":
        title, by, missing = "Image models", "B · image only", "no B result"
        top, rest = ranked(models, lambda model: model["conditions"].get("B"))
    else:
        title, by, missing = "Text-only models", "their best OCR route", "no OCR route measured"
        top, rest = ranked(models, lambda model: (best_route(data, model) or (None, None))[1])
    heading = f'<h3 class="board-group">{title}</h3>'
    if not models:
        return f'{heading}<p class="note">None so far.</p>'
    note = f"Ranked by {by}, highest first."
    if kind == "text":
        note = f"These models take no image input, so B and C do not apply. {note}"
    if rest:
        note += (f" {esc(names(rest))} {'has' if len(rest) == 1 else 'have'} {missing}, so "
                 f"{'it is' if len(rest) == 1 else 'they are'} not ranked and {'follows' if len(rest) == 1 else 'follow'} the ranked rows.")
    return f'{heading}<p class="note">{note}</p>{model_table(site, PATH, data, top + rest)}'


def not_run(items: list[dict[str, Any]]) -> str:
    """The models we have not run yet, each with its reason from vision.json's skipped."""
    if not items:
        return ""
    lines = "".join(f"<li><strong>{esc(item['model'])}</strong>: {esc(item['reason'].removeprefix('Not run: '))}</li>" for item in items)
    return f'<h3 class="board-group">Not run</h3><ul>{lines}</ul>'


def leaderboard(site: Site, data: dict[str, Any], decision: bool) -> str:
    """The decision models' leaderboard (shown for the all and decision groups of the view bar), or the other models'
    (for the all group: the chat group shows the page's chat note instead, as build() stops on any chat model here)."""
    models = [model for model in data["models"] if site.decision(model) == decision]
    skipped = [item for item in data["skipped"] if site.decision(item) == decision]
    title = "Decision models" if decision else "Other models: chat and general models"
    marks = DECISION_ONLY if decision else 'data-models="all"'
    start = f'    <section class="card" id="{"decision" if decision else "other"}" {marks}>\n      <h2>{title}</h2>\n      '
    if not models:
        empty = "No chat or general model has been run on the page images yet." if not decision else "No decision model has been run on the page images yet."
        return f'{start}<p class="note">{empty}</p>{not_run(skipped)}\n    </section>'
    groups = "".join(group(site, data, [model for model in models if model["kind"] == kind], kind) for kind in ("image", "text"))
    return f"{start}{groups}{not_run(skipped)}\n    </section>"


def small(site: Site, model: dict[str, Any]) -> bool:
    """Whether a model is in the view bar's small group, by its Text tab setup (condition A's run); never without one."""
    run = site.by_id.get(model["a_run"])
    return run is not None and site.in_group(run, "small")


def small_board(site: Site, data: dict[str, Any]) -> str:
    """The small group's leaderboard: the small models (all decision models, as build() stops on any other), grouped
    as in the decision models' leaderboard."""
    models = [model for model in data["models"] if small(site, model)]
    start = f'    <section class="card" id="small" {shown("small")}>\n      <h2>Small decision models</h2>\n      '
    if not models:
        return f'{start}<p class="note">No small model has been run on the page images yet.</p>\n    </section>'
    groups = "".join(group(site, data, [model for model in models if model["kind"] == kind], kind) for kind in ("image", "text"))
    return f"{start}{groups}\n    </section>"


def ocr_table(data: dict[str, Any]) -> str:
    """Each OCR model on the human-verified question text: character error rate, Turkish letter error rate, and the
    underlined and numbered words its text kept."""
    heads = (("Character error rate", "lower is better"), ("Turkish letter error rate", "lower is better"),
             ("Underlined words kept", "higher is better"), ("Numbered words kept", "higher is better"))
    rows = []
    for key, item in data["ocr"]["models"].items():
        verified = item["verified"]
        sent, raw = verified["marked_in_text_sent"], verified["marked_in_raw_output"]
        underlined, numbered = sent["underlined"], sent["numbered"]
        raw_note = (f'<span class="small">{raw["underlined"]["marked"]:,} in its raw output</span>'
                    if raw and raw["underlined"]["marked"] != underlined["marked"] else "")
        values = (pct(verified["cer"], 2), pct(verified["turkish_letter_rate"]["rate"], 2),
                  f'{underlined["marked"]:,} of {underlined["spans"]:,}{raw_note}', f'{numbered["marked"]:,} of {numbered["markers"]:,}')
        rows.append(
            f'<tr><td class="model"><span class="model-name">{esc(OCR_NAMES[key])}</span>'
            f'<span class="small">{esc(item["model"])} at {esc(item["revision"][:7])}</span></td>'
            + "".join(cell(f"{name} ({direction})", value) for (name, direction), value in zip(heads, values)) + "</tr>"
        )
    head = "".join(f'<th scope="col" class="num">{name}<span class="small">{direction}</span></th>' for name, direction in heads)
    return (f'<div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">OCR model</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def sentence(text: str) -> str:
    """A text from vision.json as a sentence of the page: its first letter capitalised."""
    return text[:1].upper() + text[1:]


def listing(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def words(count: int) -> str:
    """A count in words, as at the start of a sentence: "Six"."""
    return sentence(bp.in_words(count))


def joined(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def repeats_note(data: dict[str, Any]) -> str:
    """vision-repeats.json's repeat passes, kept outside the table: for each model, the cells asked again with the same
    inputs and runner, and whether their picks and option probabilities match the table's first pass. Stops the build
    when a repeat's first pass is not the table's cell (its runs and its answers)."""
    path = ROOT / "vision-repeats.json"
    if not path.exists():
        return ""
    repeats = json.loads(path.read_text(encoding="utf-8"))
    by_model: dict[str, list[dict[str, Any]]] = {}
    for cell in repeats["cells"]:
        model = next(item for item in data["models"] if item["provider"] == cell["provider"] and item["model"] == cell["model"])
        table = model["conditions"][cell["condition"]]
        answers = data["answers"][f"{cell['provider']}|{cell['model']}|{cell['condition']}"]
        if cell["first_pass"]["runs"] != table["runs"] or cell["first_pass"]["right"] != table["correct"] or any(
                passed["answers"].keys() != answers.keys() for passed in cell["passes"]):
            raise SystemExit(f"vision-repeats.json: {cell['name']} {cell['condition']} is not the table's cell")
        by_model.setdefault(cell["name"], []).append(cell)
    sentences = []
    for name, cells in by_model.items():
        passes = sorted({passed["pass"] for cell in cells for passed in cell["passes"]})
        differ = sum(passed["picks_differ"] + passed["probabilities_differ"] for cell in cells for passed in cell["passes"])
        runs = joined([str(run) for cell in cells for run in cell["first_pass"]["runs"]])
        outcome = (f"every pass gave the same picks and option probabilities as the table's runs {runs}" if not differ else
                   f"{sum(passed['picks_differ'] for cell in cells for passed in cell['passes']):,} picks and "
                   f"{sum(passed['probabilities_differ'] for cell in cells for passed in cell['passes']):,} sets of option "
                   f"probabilities differ from the table's runs {runs}")
        sentences.append(
            f"{esc(name)} answered conditions {joined([cell['condition'] for cell in cells])} {bp.in_words(len(passes))} more "
            f"times with the same inputs and runner (passes {passes[0]} to {passes[-1]}, in "
            f'<a href="{rel(PATH, "vision-repeats.json")}">vision-repeats.json</a>); {outcome}. The table shows the first '
            "pass, chosen as the cell before the runs.")
    return f"<p>{' '.join(sentences)}</p>"


# The image documentation of each API the image models were called through.
IMAGE_DOCS = {
    "typesafe": "https://docs.typesafe.ai/images",
    "liquid": "https://docs.liquid.ai/lfm/models/d1",
    "openai": "https://developers.openai.com/api/docs/guides/images-vision",
}


def image_sizes(data: dict[str, Any]) -> str:
    """The size at which each API counted and billed a crop: the input tokens it reported against its documented billing
    grid at the sent size. The crops' size limit is the one their method names; the grids are each API's documentation."""
    if "1568" not in data["crops"]["method"]:
        raise SystemExit("vision.json: the crops' method no longer names the 1568 pixel limit the image size note states")
    questions = f"{data['subset']['questions']:,}"
    link = lambda key, text: f'<a href="{IMAGE_DOCS[key]}">{text}</a>'  # noqa: E731
    return ("<p>We sent every crop at its own size: at most 1568 pixels a side (one crop is 1568; the rest are at most 1169). "
            "The input tokens each API reported match its documented billing grid at those sent sizes, on all "
            f"{questions} questions: TypeSafe's Jev, {link('typesafe', '2 tokens per 28 by 28 pixel cell')} plus a fixed 354 to "
            f"361 tokens (375 to 380 with two crops); Liquid's d1-ultra, 44 plus {link('liquid', '1.5 tokens per 32 by 32 pixel patch')}; "
            f"OpenAI's GPT-6 Luna through the Decisions API, 130 plus {link('openai', '1 token per 32 by 32 pixel patch with the default detail setting')}. "
            "A downscale before counting, to 1024 pixels or less, would have changed these counts. This shows the size at "
            "which each API counted and billed an image, not what the model saw inside it. TypeSafe documents that it rejects "
            "images outside 280 to 1568 pixels a side instead of resizing them; that is a rule about accepted inputs, not a "
            "guarantee about every internal tensor. Liquid's and OpenAI's image dimensions after tokenization are not "
            "observable to us.</p>")


def full_scan(data: dict[str, Any]) -> str:
    """The search of every OCR output for answer-key text (crops.leak_check.full_scan); the build stops when the scan is
    incomplete or a hit is not what the sentence says."""
    scan = data["crops"]["leak_check"]["full_scan"]
    inventories = scan["inventories"]
    crops = data["crops"]["images"]
    if not scan["complete"] or any(item["outputs"] != crops or item["missing"] or item["extra"] for item in inventories.values()):
        raise SystemExit("vision.json: the full leak scan does not cover every OCR output of every crop")
    lone = [hit for hit in scan["hits"] if hit["kind"] == "lone pair"]
    if len(lone) != scan["lone_pair_hits"] or len(lone) + scan["key_text_hits"] != len(scan["hits"]) or any(
            hit["pairs"] != 1 or hit["pairs_on_own_number"] != 1 or hit["own_key_pair"] or hit["key_words"] for hit in lone):
        raise SystemExit("vision.json: the full leak scan's hits are not lone pairs on each question's own number")
    outputs = sum(item["outputs"] for item in inventories.values())
    text = (f"<p>We also searched every OCR output, {outputs:,} in all ({len(inventories)} OCR models × {crops:,} crops), for "
            "answer-key text: number-letter pairs as a key prints them (“1\u2011C 2\u2011C”) and key wording. "
            + ("None had key text." if not scan["key_text_hits"] else f"{words(scan['key_text_hits'])} had key text."))
    if lone:
        names = joined([OCR_NAMES[key] for key in dict.fromkeys(hit["ocr"] for hit in lone)])
        text += (f" {words(len(lone))} {esc(names)} output{'' if len(lone) == 1 else 's'} each had one number-letter pair; in "
                 "each, the number is the question’s own number and the letter is not its answer.")
    return text + "</p>"


def cell_name(cell: str) -> str:
    """A cell of vision.json's requests ("GPT-6 Luna D dots-mocr") with the OCR model's name: "GPT-6 Luna D · dots.mocr"."""
    for key, name in OCR_NAMES.items():
        cell = cell.replace(f"D {key}", f"D · {name}")
    return cell


def requests_note(site: Site, data: dict[str, Any]) -> str:
    """What the stored answers, the logs' retries, the tokens and the costs cover (vision.json's requests): one stored answer
    per question and cell, so neither the answers nor the empty failures list counts every request sent."""
    requests = data["requests"]
    run_model = {run: model for model in data["models"] for label, got in model["conditions"].items() if label != "A"
                 for run in got.get("runs", [])}
    retries = requests["recorded_client_retries"]
    # Each retried run's HTTP status, as the logs' source names it ("HTTP 503 ... in runs 4 and 9").
    status = {}
    for found in re.finditer(r"HTTP (\d{3})\b[^()]*?\bin runs? ([\d, and]+?)(?= \()", retries["source"]):
        for run in re.findall(r"\d+", found.group(2)):
            status[run] = found.group(1)
    if set(status) != set(retries["by_run"]) or sum(retries["by_run"].values()) != retries["total"]:
        raise SystemExit("vision.json: requests.recorded_client_retries does not name each retried run's HTTP status")
    groups: dict[tuple[str, str], list[str]] = {}
    for run, count in retries["by_run"].items():
        model = run_model[int(run)]
        name = model["name"]
        groups.setdefault((name, status[run]), []).append(f"{count} in run {run}")
    parts = [f"{joined(items)}, {'both ' if len(items) == 2 else ''}{esc(name)} after HTTP {code}{' errors' if len(items) > 1 else ''}"
             for (name, code), items in groups.items()]
    continued = requests["continued_cells"]
    cells = "; ".join(f"{esc(cell_name(item['cell']))}, runs {joined([str(run) for run in item['runs']])}" for item in continued)
    return (f"<p>Each cell holds one stored answer per question: {requests['retained_answers']:,} in all, from "
            f"{requests['runs']:,} runs. {words(len(continued))} cells were finished by a second run after an interruption "
            f"({cells}); these are continuations, not repeats. {requests['valid_choices']:,} answers name an option and "
            f"{requests['refusals']:,} are refusals. The runs’ logs record {retries['total']:,} client retries: "
            f"{', and '.join(parts)}. The logs do not cover every run, and an attempt that failed and was asked again is not stored, so "
            f"{requests['requests_lower_bound']:,} is a lower bound on the requests sent. Tokens and costs come from the stored "
            "responses only: not every attempt and not an invoice. The usage and cost of attempts that were not kept are "
            "unknown, not zero.</p>")


def run_span(runs: list[int]) -> str:
    """Run numbers as text, consecutive ones as a range: 'run 9', 'runs 56 and 57', 'runs 1 to 28'."""
    spans: list[list[int]] = []
    for run in runs:
        if spans and run == spans[-1][1] + 1:
            spans[-1][1] = run
        else:
            spans.append([run, run])
    texts = [str(first) if first == last else f"{first} and {last}" if last == first + 1 else f"{first} to {last}"
             for first, last in spans]
    return ("run " if len(runs) == 1 else "runs ") + ", ".join(texts)


def harness(data: dict[str, Any]) -> str:
    """The runner commits the runs recorded (vision.json's run_commits), each with where it was merged into the published
    branch, or that it sits on it."""
    def where(item: dict[str, Any]) -> str:
        if not item.get("merged_in"):
            return "not yet published"
        if item["merged_in"] == item["commit"]:
            return "on the published main"
        return f"merged into the published main in {esc(item['merged_in'][:8])}"

    parts = [f"{esc(item['commit'][:7])} for {run_span(item['runs'])}, {where(item)}" for item in data["run_commits"]]
    return " (the runs record its commit: " + "; ".join(parts) + ")"


def engine_check(site: Site, data: dict[str, Any]) -> str:
    """vision.json's engine check: one condition of a model asked again on another serving engine, against the run in the
    table, with the paired exact McNemar test (first: the check, second: the table's run)."""
    item = data["engine_checks"][0]
    row, check, paired = item["row"], item["check"], item["paired"]
    server = next(model for model in data["models"] if model["provider"] == check["provider"])
    if ("d3_server.py" not in check["hardware"] or "transformers" not in check["hardware"] or "vLLM" not in row["hardware"]
            or round(paired["difference"] * paired["questions"]) != check["correct"] - row["correct"]):
        raise SystemExit("vision.json: engine_checks[0] no longer matches the engines or the order its note states")
    short = server["name"]
    runs = lambda side: " and ".join(f"run {run}" for run in side["runs"])  # noqa: E731
    questions = f"{check['questions']:,}"
    return (f"<p>Engine check: we asked {esc(item['name'])}'s condition {esc(item['condition'])} again through d3_server.py on "
            f"transformers, the server {esc(short)} ran on ({runs(check)}): {check['correct']:,} of {questions} right "
            f"({pct(check['correct'] / check['questions'])}), against {row['correct']:,} ({pct(row['correct'] / row['questions'])}) "
            f"through vLLM ({runs(row)}), the run in the table. Exact McNemar test: {paired['first_only']:,} questions right only "
            f"on transformers and {paired['second_only']:,} only on vLLM, {esc(bp.p_text(paired['p']))}; "
            f"{item['picks_differ']:,} of {questions} picks differ.</p>")


def findings(site: Site, data: dict[str, Any]) -> str:
    """What we found: the leaderboards' main results in words, every number computed from vision.json; each difference is
    taken between accuracies computed from the right-answer counts and rounded only when shown (not between the tables'
    rounded percentages); significance from the paired exact McNemar tests vision.json holds (p below 0.05, one
    comparison at a time). The sentences assume what they state (each image model has A, B and C and is less accurate
    with the picture alone, every model's best OCR route is below its text, every OCR route beats the picture alone);
    the build stops when the data no longer fits them."""
    exact = lambda result: 100 * result["correct"] / result["questions"]  # noqa: E731 - an accuracy in percent, unrounded
    acc = lambda model, label: exact(model["conditions"][label])  # noqa: E731
    points = lambda value: f"{value:.1f}"  # noqa: E731

    shown = shown_names(site, data["models"])

    def name(model: dict[str, Any]) -> str:
        return esc(shown.get(model["a_run"], model["name"]))

    def p_value(model: dict[str, Any], first: str, second: str) -> float:
        found = [item["accuracy"]["mcnemar_p"] for item in model["paired"] if item["first"] == first and item["second"] == second]
        if len(found) != 1:
            raise SystemExit(f"vision.json findings: {model['name']} has no paired test of {first} against {second}")
        return found[0]

    image = [model for model in data["models"] if model["kind"] == "image"]
    if not image or any(label not in model["conditions"] for model in image for label in ("A", "B", "C")):
        raise SystemExit("vision.json findings: the text expects image models with conditions A, B and C")
    drop = {model["name"]: acc(model, "A") - acc(model, "B") for model in image}
    if min(drop.values()) <= 0:
        raise SystemExit("vision.json findings: an image model was not less accurate with the picture alone")
    least = min(image, key=lambda model: drop[model["name"]])
    most = max(image, key=lambda model: drop[model["name"]])
    weak = [model for model in image if p_value(model, "A", "B") >= 0.05]
    significance = ("each difference significant" if not weak else
                    f"significant for {len(image) - len(weak)} of the {len(image)}")
    first = (f"<p>All {len(image)} image models were less accurate with the picture alone (B) than with the text (A): by "
             f"{points(drop[least['name']])} points ({name(least)}) to {points(drop[most['name']])} points ({name(most)}), "
             f"{significance} in the exact McNemar test.</p>")

    change = {model["name"]: acc(model, "C") - acc(model, "A") for model in image}
    gains = [model for model in image if change[model["name"]] > 0]
    losses = [model for model in image if change[model["name"]] < 0]
    second = f"<p>With the picture added to the text (C), {len(gains)} of the {len(image)} were more accurate than with the text alone"
    if gains:
        second += (f", by {points(min(change[m['name']] for m in gains))} to "
                   f"{points(max(change[m['name']] for m in gains))} points")
        strong = [model for model in gains if p_value(model, "A", "C") < 0.05]
        if strong and len(strong) < len(gains):
            second += (f"; the gains of {joined([name(m) for m in strong])} ({points(min(change[m['name']] for m in strong))} to "
                       f"{points(max(change[m['name']] for m in strong))} points) are significant, the others are not")
        elif strong:
            second += ", each gain significant"
        else:
            second += ", none significantly"
    second += "."
    if losses:
        strong_losses = [model for model in losses if p_value(model, "A", "C") < 0.05]
        verb = "was" if len(losses) == 1 else "were"
        how = ("not significantly" if not strong_losses else
               "significantly" if len(strong_losses) == len(losses) else
               f"significantly for {joined([name(m) for m in strong_losses])}")
        second += (f" {joined([name(m) for m in losses])} {verb} less accurate with the picture "
                   f"({joined([points(-change[m['name']]) for m in losses])} points), {how}.")
    second += "</p>"

    routes = [(model, *best_route(data, model)) for model in data["models"] if best_route(data, model)]
    gap = {model["name"]: acc(model, "A") - exact(metrics) for model, _, metrics in routes}
    if not routes or min(gap.values()) <= 0:
        raise SystemExit("vision.json findings: the text expects every model's best OCR route below its text")
    third = (f"<p>Through an OCR model (D), each of the {len(routes)} models with an OCR route was less accurate than with the "
             f"text: its best route was {points(min(gap.values()))} to {points(max(gap.values()))} points below condition "
             f"A.")
    best_keys = {label.removeprefix("D ") for _, label, _ in routes}
    if len(best_keys) == 1:
        key = next(iter(best_keys))
        third += f" {esc(OCR_NAMES[key])} gave the best route for all {len(routes)}."
        verified = {other: item["verified"] for other, item in data["ocr"]["models"].items()}
        kept = lambda other, kind: verified[other]["marked_in_text_sent"][kind]  # noqa: E731
        fewest = min(verified, key=lambda other: verified[other]["cer"])
        if fewest != key and all(kept(key, kind)["marked"] > kept(other, kind)["marked"]
                                 for other in verified if other != key for kind in ("underlined", "numbered")):
            underlined, numbered = kept(key, "underlined"), kept(key, "numbered")
            third += (f" It kept the most of the marks these questions point at ({underlined['marked']:,} of "
                      f"{underlined['spans']:,} underlined words and {numbered['marked']:,} of {numbered['markers']:,} numbered "
                      f"words), although {esc(OCR_NAMES[fewest])} read the text with fewer errors (character error rate "
                      f"{pct(verified[fewest]['cer'], 2)} against {pct(verified[key]['cer'], 2)}).")
    both = [(model, label, metrics) for model, label, metrics in routes if "B" in model["conditions"]]
    if both:
        if any(acc(model, label) <= acc(model, "B")
               for model, _, _ in both for label in ocr_labels(data) if label in model["conditions"]):
            raise SystemExit("vision.json findings: the text expects every OCR route above the picture alone")
        lift = {model["name"]: exact(metrics) - acc(model, "B") for model, _, metrics in both}
        weak_routes = [model for model, label, _ in both if p_value(model, "B", label) >= 0.05]
        third += (f" For the {len(both)} image models with both, every OCR route was more accurate than the picture alone "
                  f"(B): the best route by {points(min(lift.values()))} to {points(max(lift.values()))} points, "
                  + (f"significant for {len(both) - len(weak_routes)} of the {len(both)} (not for "
                     f"{joined([name(m) for m in weak_routes])})." if weak_routes else "each significant."))
    third += "</p>"

    tops = {}
    for label in ("A", "B", "C"):
        having = [model for model in data["models"] if label in model["conditions"]]
        tops[label] = max(having, key=lambda model: model["conditions"][label]["accuracy"])
    best_overall = max(routes, key=lambda item: item[2]["accuracy"])
    if len({tops[label]["name"] for label in tops} | {best_overall[0]["name"]}) == 1:
        top = tops["A"]
        fourth = (f"<p>{name(top)} was the most accurate model in every condition: {pct(top['conditions']['A']['accuracy'])} "
                  f"with the text, {pct(top['conditions']['B']['accuracy'])} with the picture alone, "
                  f"{pct(top['conditions']['C']['accuracy'])} with both and {pct(best_overall[2]['accuracy'])} through "
                  f"{esc(OCR_NAMES[best_overall[1].removeprefix('D ')])}.</p>")
    else:
        fourth = ("<p>The most accurate: " + "; ".join(
            f"{what}, {name(tops[label])} ({pct(tops[label]['conditions'][label]['accuracy'])})"
            for label, what in (("A", "with the text"), ("B", "with the picture alone"), ("C", "with both")))
            + f"; through an OCR model, {name(best_overall[0])} ({pct(best_overall[2]['accuracy'])}).</p>")
    fifth = (f"<p>Each cell is one pass over the {data['subset']['questions']:,} questions. Each test compares two conditions "
             f"of the same model on the same questions, one comparison at a time, without an adjustment for the number of "
             f"comparisons; the OCR routes have no paired test against the text (A).</p>")
    return first + second + third + fourth + fifth


# A sample question written for the page, never one of the benchmark's (the site publishes no question text; its
# sentence and stem are in no question of questions-v2.sqlite): an underlined word as the bank marks it (<u>…</u>), the
# stem and the options; and its English for the caption.
SAMPLE_LINES = ("Kedimiz pencerenin önünde <u>sessizce</u> uyuyordu.", "Bu cümlede altı çizili sözcüğün türü nedir?",
                "A) İsim  B) Sıfat  C) Zarf  D) Fiil  E) Zamir")
SAMPLE_ENGLISH = "“Our cat was sleeping quietly in front of the window.” What word class is the underlined word?"


def inputs_sample(data: dict[str, Any]) -> str:
    """The four inputs (A, B, C, D) drawn on SAMPLE_LINES: the text as the models get it, with its markup; a picture
    of it as printed (in HTML, a page's colours in both themes); both; and an OCR model's text, its underline kept or
    lost as the OCR models' kept share of underlined words allows (vision.json, the human-verified text)."""
    kept = [item["verified"]["marked_in_text_sent"]["underlined"] for item in data["ocr"]["models"].values()]
    shares = [entry["marked"] / entry["spans"] for entry in kept]
    lost = min(shares) < 1
    text = f'<pre class="input-text">{esc(chr(10).join(SAMPLE_LINES))}</pre>'
    picture = ('<div class="input-page" role="img" aria-label="A picture of the sample question as printed, its word '
               'sessizce underlined">' + "".join(f"<p>{line}</p>" for line in SAMPLE_LINES) + "</div>")
    ocr_lines = [line.replace("<u>", "").replace("</u>", "") if lost else line for line in SAMPLE_LINES]
    ocr = f'<pre class="input-text">{esc(chr(10).join(ocr_lines))}</pre>'
    low, high = pct(min(shares), 0), pct(max(shares), 0)
    ocr_note = (f"Here the underline is lost; the OCR models kept {low} to {high} of underlined words."
                if lost else f"The OCR models kept {low} to {high} of underlined words.")
    panels = (
        ("A · text only", "The question as text, as in the Text tab, with the bank's markup.", text),
        ("B · image only", "A picture of the question cut from the book's page, alone.", picture),
        ("C · text plus image", "A's text, then the picture.", text + picture),
        ("D · OCR route", f"One OCR model's text of the picture, for each of {len(OCR_NAMES)} OCR models; the most accurate "
                          f"is the best OCR route. {ocr_note}", ocr),
    )
    items = "".join(f'<li><p class="input-head"><strong>{esc(title)}</strong></p>{content}<p class="small">{esc(note)}</p></li>'
                    for title, note, content in panels)
    return ('<figure class="inputs"><figcaption>The four inputs, on a sample question we wrote for this page, not one of '
            f'the benchmark\'s ({esc(SAMPLE_ENGLISH)})</figcaption><ol class="input-list">{items}</ol></figure>')


def face(site: Site, data: dict[str, Any]) -> tuple[str, list[str]]:
    """The tab's face: four chart cards, each with a line saying which way is better, every number from vision.json: the
    picture alone (B) against the text (A), the text plus the picture (C) against the text, the best OCR route against the
    text, and the marks each OCR model kept. Bars of one measure take the ranking scale between its worst and best. With
    the titles of the model charts without a small model's row, for the small group's note."""
    stops = site.config["rank_scale"]["stops"]
    questions = f"{data['subset']['questions']:,}"
    acc = lambda model, label: model["conditions"][label]["correct"] / model["conditions"][label]["questions"]  # noqa: E731

    names_shown = shown_names(site, data["models"])
    # The charts with no small model's row, which the small group's note names.
    whole: list[str] = []

    def name(model: dict[str, Any]) -> str:
        return names_shown.get(model["a_run"], model["name"])

    def groups(model: dict[str, Any]) -> str:
        return "all decision small" if small(site, model) else "all decision"

    def href(model: dict[str, Any]) -> str | None:
        run = site.by_id.get(model["a_run"])
        return rel(PATH, site.model_path(run)) if run else None

    def card(anchor: str, title: str, sub: str, rows: list[dict[str, Any]], legend: str, marks: str | None = None) -> str:
        """A chart card; a card of the models' rows shows for the all and decision groups, and for small when one of
        its rows is a small model's (each row marked with its groups)."""
        if marks is None:
            marks = DECISION_ONLY
            if any("small" in row["models"].split() for row in rows):
                marks = 'data-models="all decision small"'
            else:
                whole.append(title)
        return (f'<figure class="panel chart-card" id="{anchor}" {marks}><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{esc(sub)}</p></div>{hbars(rows)}<p class="chart-legend">{legend}</p></figure>')

    def colour_scale(low: float, high: float) -> str:
        """The legend of bars coloured by accuracy (the ranking scale between this chart's lowest and highest), which
        says that the colour is not the model family, as it is on the home page's charts."""
        return ('<span class="scale-legend colour-scale"><strong>Colour: accuracy, not the model family.</strong> '
                f'<span>Lowest {pct(low)}</span><i class="ramp wide" style="background:linear-gradient(to right, '
                f'{", ".join(stops)})" aria-hidden="true"></i><span>highest {pct(high)} (higher is better)</span></span>')

    marker = ' <span><i class="swatch swatch-marker"></i>The same model with the text (A)</span>'
    image = [model for model in data["models"] if all(label in model["conditions"] for label in ("A", "B", "C"))]
    by_b = sorted(image, key=lambda model: -acc(model, "B"))
    low, high = min(acc(model, "B") for model in image), max(acc(model, "B") for model in image)
    first = card(
        "chart-image", "The picture alone (B)", f"Share of the {questions} questions answered right from a picture of the question alone · higher is better",
        [{"label": name(model), "href": href(model), "text": pct(acc(model, "B")), "marker": acc(model, "A"),
          "bars": [{"value": acc(model, "B"), "colour": rank_fill(stops, acc(model, "B"), low, high)}],
          "title": f"{name(model)}: {pct(acc(model, 'B'))} from the picture alone, {pct(acc(model, 'A'))} with the text",
          "models": groups(model)}
         for model in by_b],
        colour_scale(low, high) + marker)
    by_c = sorted(image, key=lambda model: -acc(model, "C"))
    second = card(
        "chart-both", "The text plus the picture (C)", "Accuracy with the picture after the text, and with the text alone · higher is better",
        [{"label": name(model), "href": href(model), "text": f"{pct(acc(model, 'C'))} · {pct(acc(model, 'A'))}",
          "bars": [{"value": acc(model, "C"), "kind": "lead"}, {"value": acc(model, "A"), "kind": "base"}],
          "title": f"{name(model)}: {pct(acc(model, 'C'))} with the text plus the picture, {pct(acc(model, 'A'))} with the text",
          "models": groups(model)}
         for model in by_c],
        '<span><i class="swatch swatch-lead"></i>Text plus picture (C)</span> <span><i class="swatch swatch-base"></i>Text (A)</span>')
    routes = [(model, *best_route(data, model)) for model in data["models"] if best_route(data, model)]
    routes.sort(key=lambda item: -item[2]["correct"] / item[2]["questions"])
    shares = [metrics["correct"] / metrics["questions"] for _, _, metrics in routes]
    best_keys = {label.removeprefix("D ") for _, label, _ in routes}
    same = (f" <span>The best route is {esc(OCR_NAMES[next(iter(best_keys))])} for every model.</span>"
            if len(best_keys) == 1 else "")
    third = card(
        "chart-ocr-route", "The best OCR route (D)", "Accuracy with one OCR model's reading of the picture as text, the best of the four · higher is better",
        [{"label": name(model), "href": href(model), "text": pct(share), "marker": acc(model, "A"),
          "bars": [{"value": share, "colour": rank_fill(stops, share, min(shares), max(shares))}],
          "title": f"{name(model)}: {pct(share)} via {OCR_NAMES[label.removeprefix('D ')]}, {pct(acc(model, 'A'))} with the text",
          "models": groups(model)}
         for (model, label, _), share in zip(routes, shares)],
        colour_scale(min(shares), max(shares)) + marker + same)
    kept = []
    for key, item in data["ocr"]["models"].items():
        sent = item["verified"]["marked_in_text_sent"]
        kept.append((key, sent["underlined"]["marked"] / sent["underlined"]["spans"], sent["numbered"]["marked"] / sent["numbered"]["markers"]))
    kept.sort(key=lambda item: -item[1])
    fourth = card(
        "chart-marks", "Marks the OCR models kept",
        "Share of the underlined and of the numbered words still marked in the text the models received, on the human-verified text · higher is better",
        [{"label": OCR_NAMES[key], "text": f"{pct(underlined)} · {pct(numbered)}",
          "bars": [{"value": underlined, "kind": "lead"}, {"value": numbered, "kind": "base"}],
          "title": f"{OCR_NAMES[key]}: {pct(underlined)} of the underlined words and {pct(numbered)} of the numbered words kept"}
         for key, underlined, numbered in kept],
        '<span><i class="swatch swatch-lead"></i>Underlined words</span> <span><i class="swatch swatch-base"></i>Numbered words</span>',
        marks="")
    return f'<section class="charts" aria-label="Charts">{first}{second}{third}{fourth}</section>', whole


def build(site: Site) -> dict[str, str]:
    data = site.vision
    mixed = site.config["mixed_providers"]
    undecided = sorted({(model["provider"], model["model"]) for model in data["models"]
                        if model["provider"] in mixed and model["model"] not in mixed[model["provider"]]})
    if undecided:
        raise SystemExit("vision.json: decide whether each of these is a decision model, then list it under its provider in "
                         "page_config.json's mixed_providers: " + ", ".join(f"{model} ({provider})" for provider, model in undecided))
    chat = [model["name"] for model in data["models"] if not site.decision(model)]
    if chat:
        raise SystemExit("vision.json: chat or general models, which the page's charts and the view bar's chat group do not "
                         "show yet (give the face one copy per group, as english_view.py does): " + ", ".join(chat))
    subset = data["subset"]
    reasons = subset["by_reason"]
    questions = f"{subset['questions']:,}"
    crops = data["crops"]
    leak = crops["leak_check"]
    cost = data["cost"]
    verified = next(iter(data["ocr"]["models"].values()))["verified"]["crops"]
    hardware = sorted({value for model in data["models"] for value in (model.get("hardware") or {}).values()})
    units = ", ".join(f"{unit}: {count}" for unit, count in subset["by_unit"].items())
    failures = [esc(item) if isinstance(item, str) else esc(str(item)) for item in data["failures"]]
    ocr_methods = [f"<strong>{esc(OCR_NAMES[key])}</strong> ({esc(item['model'])} at {esc(item['revision'][:7])}): {esc(item['method'])}"
                   for key, item in data["ocr"]["models"].items()]
    charts, _ = face(site, data)
    site.note(PATH, "Page images", f"""<p>The {questions} questions of the Text tab's {subset["scored_questions"]:,} that point at marked words on the printed page: {reasons["underline"]} at underlined words and {reasons["numbered"]} at numbered words ({subset["both_underline_and_numbered"]} at both). Each model answered them in up to four ways. This tab is ranked on its own; its numbers do not enter the Text tab's ranking.</p>
      {inputs_sample(data)}""")
    body = f"""    <section class="card">
      <p class="eyebrow">Page images</p>
      <h1>{questions} questions with underlined or numbered words</h1>
      {chat_note("Chat models: none on this tab. Every model run on the page images is a decision model, so the models' charts and tables show under All models and Decision models. The OCR models' parts below show in every view.")}
      <p>Each model answered them from the text (A), a picture (B), both (C) or an OCR reading (D); ranked apart from the Text tab.</p>
      {more_link(PATH)}
      {small_note("Small models: the charts and What we found cover decision models of every size; they show under All models or Decision models.")}
      <nav class="face-nav" aria-label="On this page"><a href="#chart-image">Picture alone</a><a href="#chart-both">Text plus picture</a><a href="#chart-ocr-route">OCR route</a><a href="#chart-marks">OCR marks</a><a href="#decision" {DECISION_ONLY}>Tables</a><a href="#small" {shown("small")}>Tables</a><a href="#ocr">OCR reading</a><a href="#info">Info</a></nav>
    </section>
    {charts}
{leaderboard(site, data, True)}
{small_board(site, data)}
{leaderboard(site, data, False)}
    <section class="card" id="ocr">
      <h2>How well the OCR models read the pages</h2>
      <p class="note">The error rates and counts use only human-verified question text: {esc(data["ocr"]["verified"].removeprefix("the human-verified subset: "))}. Each OCR model's text is compared with that text. Character error rate: edits over the reference's characters, summed over the {verified} crops. Turkish letter error rate: edits of the same alignment whose reference or OCR character is one of ı İ ş Ş ğ Ğ ç Ç ö Ö ü Ü, over the reference's count of those letters. Kept: an underlined word still marked, or a numbered word's numeral still there, in the text the models received.</p>
      {ocr_table(data)}
    </section>
    <details class="info info-details" id="info">
      <summary class="info-summary"><span class="info-title">Info</span> <span class="info-sub">What we found, the measure and how the benchmark was run</span></summary>
    <section class="card">
      <h2>About this test</h2>
      <p class="note">Accuracy: the share of the {questions} questions answered right ({esc(data["measures_method"]["accuracy"].split("; ")[1])}), with its 95% interval under it in the tables.</p>
      <p class="note">Download: <a href="{rel(PATH, "vision.json")}" download>vision.json</a> (every number on this page, and each answer's pick and option probabilities; no question text, page image or OCR text).</p>
    </section>
    <section class="card" id="findings" {DECISION_ONLY}>
      <h2>What we found</h2>
      {findings(site, data)}
    </section>
    <section class="card method-notes" id="method">
      <h2>How the benchmark was run</h2>
      <h3>Conditions</h3>
      {listing([f"<strong>{esc(label)}</strong>: {esc(text)}" for label, text in data["conditions"].items()])}
      <p>Each cell is one run. It is one pass over the {questions} questions, not an average of repeated runs ({len(data["requests"]["continued_cells"])} passes were resumed after an interruption; see Models and cost).</p>
      <h3>Pictures of the questions</h3>
      <p>{esc(sentence(crops["method"]))}. {crops["images"]} images for {crops["questions"]} questions; {crops["clipped_at_key"]} crops stop above an answer key box, {crops["padded"]} were padded and {crops["scaled"]} scaled. Questions per topic: {esc(units)}.</p>
      {image_sizes(data)}
      <p>Checked by eye for leaks: {leak["checked_by_eye"]} crops, with {leak["leaks_found"]} leaks found. {esc(sentence(leak["detector_history"]))}.</p>
      {full_scan(data)}
      <h3>OCR models</h3>
      {listing(ocr_methods)}
      <h3>Models and cost</h3>
      <p>Every request went through the benchmark's runner{harness(data)}, one question per request; the images went in each API's own format. Self-hosted models ran on {esc("; ".join(hardware)) if hardware else "our GPU"}. The API image runs (B and C) cost ${cost["image_runs_usd"]:.2f} and the API runs of condition D ${cost["d_runs_usd"]:.2f}, at the prices in results.json.</p>
      {engine_check(site, data)}
      {requests_note(site, data)}
      {repeats_note(data)}
      {"<h3>Failures</h3>" + listing(failures) if failures else ""}
    </section>
    </details>"""
    return {PATH: site.page(PATH, "Page images",
                            f"{questions} questions with underlined or numbered words, asked as text, as a page image, "
                            "as both and through four OCR models.", body, image="vision")}
