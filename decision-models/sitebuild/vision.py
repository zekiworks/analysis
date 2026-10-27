"""Page images (vision/), the site's second tab, preliminary: the questions that point at underlined or numbered words on
the printed page, asked as text (A), as a picture of the page only (B), as both (C) and as each OCR model's reading of the
picture (D), from vision.json. vision.json holds aggregate numbers and each answer's pick and option probabilities; no
question text, picture or OCR text.

The leaderboard keeps decision models and other models apart (page_config.json's rule, Site.decision), and within each,
the image models ranked by B, then the text-only models ranked by their best OCR route. A condition vision.json does not
hold reads "Not available" with its reason from the model's "missing"; a row without the result it is ranked by follows
the ranked rows, in vision.json's order. model_table() also gives a model page its row."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
      <p class="eyebrow">Page images <span class="badge">Preliminary</span></p>
      <h1>{questions} questions with underlined or numbered words</h1>
      <p class="preliminary"><strong>Preliminary:</strong> these numbers are not final and may change.</p>
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
    <section class="card">
      <h2>How the benchmark was run</h2>
      <h3>Conditions</h3>
      {listing([f"<strong>{esc(label)}</strong>: {esc(text)}" for label, text in data["conditions"].items()])}
      <h3>Pictures of the questions</h3>
      <p>{esc(sentence(crops["method"]))}. {crops["images"]} images for {crops["questions"]} questions; {crops["clipped_at_key"]} crops stop above an answer key box, {crops["padded"]} were padded and {crops["scaled"]} scaled. Questions per topic: {esc(units)}.</p>
      <p>Checked by eye for leaks: {leak["checked_by_eye"]} crops, with {leak["leaks_found"]} leaks found. {esc(sentence(leak["detector_history"]))}.</p>
      <h3>OCR models</h3>
      {listing(ocr_methods)}
      <h3>Models and cost</h3>
      <p>Every request went through the benchmark's runner, one question per request; the images went in each API's own format. Self-hosted models ran on {esc("; ".join(hardware)) if hardware else "our GPU"}. The API image runs (B and C) cost ${cost["image_runs_usd"]:.2f} and the API runs of condition D ${cost["d_runs_usd"]:.2f}, at the prices in results.json.</p>
      {"<h3>Failures</h3>" + listing(failures) if failures else ""}
    </section>"""
    return {PATH: site.page(PATH, "Page images (preliminary)",
                            f"Preliminary: {questions} questions with underlined or numbered words, asked as text, as a page image, "
                            "as both and through four OCR models.", body)}
