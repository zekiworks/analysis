"""Page images (vision/), the site's second tab: the questions that point at underlined or numbered words on
the printed page, asked as text (A), as a picture of the page only (B), as both (C) and as each OCR model's reading of the
picture (D), from vision.json. vision.json holds aggregate numbers and each answer's pick and option probabilities; no
question text, picture or OCR text.

The leaderboard keeps decision models and other models apart (page_config.json's rule, Site.decision), and within each,
the image models ranked by B, then the text-only models ranked by their best OCR route. A condition vision.json does not
hold reads "Not available" with its reason from the model's "missing"; a row without the result it is ranked by follows
the ranked rows, in vision.json's order. model_table() also gives a model page its row."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import build_page as bp
from sitebuild.site import Site, esc, interval, pct, rel

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


def model_cell(site: Site, origin: str, model: dict[str, Any]) -> str:
    """The model, linked to the page of its Text tab setup (condition A's run) when the Text tab has it, with the run's
    route where the same model ID runs as both kinds of model."""
    run = site.by_id.get(model["a_run"])
    if run is None:
        return (f'<td class="model"><span class="model-name">{esc(model["name"])}</span>'
                '<span class="small">Not on the Text tab</span></td>')
    return (f'<td class="model"><a class="model-name" href="{rel(origin, site.model_path(run))}">{esc(site.row_name(run))}</a>'
            f'<span class="small">{esc(site.detail(run))}</span></td>')


def model_table(site: Site, origin: str, data: dict[str, Any], models: list[dict[str, Any]]) -> str:
    """The leaderboard's columns for these models, in this order; every header says which way is better."""
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{DIRECTION}</span></th>' for _, name in COLUMNS)
    rows = "".join(f"<tr>{model_cell(site, origin, model)}{cells(data, model)}</tr>" for model in models)
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
    models = [model for model in data["models"] if site.decision(model) == decision]
    skipped = [item for item in data["skipped"] if site.decision(item) == decision]
    title = "Decision models" if decision else "Other models: chat and general models"
    if not models:
        empty = "No chat or general model has been run on the page images yet." if not decision else "No decision model has been run on the page images yet."
        return f'    <section class="card">\n      <h2>{title}</h2>\n      <p class="note">{empty}</p>{not_run(skipped)}\n    </section>'
    groups = "".join(group(site, data, [model for model in models if model["kind"] == kind], kind) for kind in ("image", "text"))
    return f'    <section class="card" id="{"decision" if decision else "other"}">\n      <h2>{title}</h2>\n      {groups}{not_run(skipped)}\n    </section>'


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
        name = site.config["short_names"].get(model["model"], model["name"])
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


def harness(data: dict[str, Any]) -> str:
    """The runner's commit and, once pushed, where it was merged into the published branch."""
    item = data["harness"]
    if not item.get("pushed") or not item.get("merged_in"):
        return f" (commit {esc(item['commit'][:7])}, not yet published)"
    same = "; runner file identical at the merge" if item.get("runner_file_at_merge") else ""
    return (f" (commit {esc(item['commit'][:7])}, merged into the published {esc(item['published_branch'])} in "
            f"{esc(item['merged_in'][:8])}{same})")


def engine_check(site: Site, data: dict[str, Any]) -> str:
    """vision.json's engine check: one condition of a model asked again on another serving engine, against the run in the
    table, with the paired exact McNemar test (first: the check, second: the table's run)."""
    item = data["engine_checks"][0]
    row, check, paired = item["row"], item["check"], item["paired"]
    server = next(model for model in data["models"] if model["provider"] == check["provider"])
    if ("d3_server.py" not in check["hardware"] or "transformers" not in check["hardware"] or "vLLM" not in row["hardware"]
            or round(paired["difference"] * paired["questions"]) != check["correct"] - row["correct"]):
        raise SystemExit("vision.json: engine_checks[0] no longer matches the engines or the order its note states")
    short = site.config["short_names"].get(server["model"], server["name"])
    runs = lambda side: " and ".join(f"run {run}" for run in side["runs"])  # noqa: E731
    questions = f"{check['questions']:,}"
    return (f"<p>Engine check: we asked {esc(item['name'])}'s condition {esc(item['condition'])} again through d3_server.py on "
            f"transformers, the server {esc(short)} ran on ({runs(check)}): {check['correct']:,} of {questions} right "
            f"({pct(check['correct'] / check['questions'])}), against {row['correct']:,} ({pct(row['correct'] / row['questions'])}) "
            f"through vLLM ({runs(row)}), the run in the table. Exact McNemar test: {paired['first_only']:,} questions right only "
            f"on transformers and {paired['second_only']:,} only on vLLM, {esc(bp.p_text(paired['p']))}; "
            f"{item['picks_differ']:,} of {questions} picks differ.</p>")


def build(site: Site) -> dict[str, str]:
    data = site.vision
    mixed = site.config["mixed_providers"]
    undecided = sorted({(model["provider"], model["model"]) for model in data["models"]
                        if model["provider"] in mixed and model["model"] not in mixed[model["provider"]]})
    if undecided:
        raise SystemExit("vision.json: decide whether each of these is a decision model, then list it under its provider in "
                         "page_config.json's mixed_providers: " + ", ".join(f"{model} ({provider})" for provider, model in undecided))
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
    body = f"""    {site.tabs(PATH)}
    <section class="card">
      <p class="eyebrow">Page images</p>
      <h1>{questions} questions with underlined or numbered words</h1>
      <p>The Page images benchmark contains the {questions} questions of the Text tab's {subset["scored_questions"]:,} that point at marked words on the printed page: {reasons["underline"]} at underlined words and {reasons["numbered"]} at numbered words ({subset["both_underline_and_numbered"]} at both). Each model answered them in up to four ways:</p>
      <ul>
        <li><strong>A · text only</strong>: the question as text, as in the Text tab.</li>
        <li><strong>B · image only</strong>: a picture of the question cut from the book's page, and nothing else.</li>
        <li><strong>C · text plus image</strong>: A's text with the picture after it.</li>
        <li><strong>D · OCR route</strong>: one OCR model's reading of the picture, as text, for each of {len(OCR_NAMES)} OCR models. The best OCR route is the one with the highest accuracy.</li>
      </ul>
      <p class="note">Accuracy: the share of the {questions} questions answered right ({esc(data["measures_method"]["accuracy"].split("; ")[1])}), with its 95% interval under it. This tab is ranked on its own; its numbers do not enter the Text tab's ranking.</p>
      <p class="note">Download: <a href="{rel(PATH, "vision.json")}" download>vision.json</a> (every number on this page, and each answer's pick and option probabilities; no question text, page image or OCR text).</p>
    </section>
{leaderboard(site, data, True)}
{leaderboard(site, data, False)}
    <section class="card" id="ocr">
      <h2>How well the OCR models read the pages</h2>
      <p class="note">The error rates and counts use only human-verified question text: {esc(data["ocr"]["verified"].removeprefix("the human-verified subset: "))}. Each OCR model's text is compared with that text. Character error rate: edits over the reference's characters, summed over the {verified} crops. Turkish letter error rate: edits of the same alignment whose reference or OCR character is one of ı İ ş Ş ğ Ğ ç Ç ö Ö ü Ü, over the reference's count of those letters. Kept: an underlined word still marked, or a numbered word's numeral still there, in the text the models received.</p>
      {ocr_table(data)}
    </section>
    <section class="card method-notes">
      <h2>How the benchmark was run</h2>
      <h3>Conditions</h3>
      {listing([f"<strong>{esc(label)}</strong>: {esc(text)}" for label, text in data["conditions"].items()])}
      <p>Each cell is one run: one pass over the {questions} questions, not an average of repeated runs ({len(data["requests"]["continued_cells"])} passes were resumed after an interruption; see Models and cost).</p>
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
      {"<h3>Failures</h3>" + listing(failures) if failures else ""}
    </section>"""
    return {PATH: site.page(PATH, "Page images",
                            f"{questions} questions with underlined or numbered words, asked as text, as a page image, "
                            "as both and through four OCR models.", body)}
