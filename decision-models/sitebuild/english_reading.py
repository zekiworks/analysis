"""English reading (english-reading/), the site's fourth tab: the Text tab's reading questions translated into English,
asked of the decision models as on the Text tab, against the same models' Turkish runs on the same questions. From
results.json's `english_reading` (every number), english-reading.json (the track's public record: the translator, its
prompts, the flags and each question's hash of its English text) and page_config.json's `english_reading` (the models
not compared or not run, with their reasons). Its face, as the Hallucination tab's, is charts in HTML (Site hbars):
accuracy in both languages and the paired test; then, when results.json has `english_reading.dont_know`, the same
questions with an "I don't know" option in English against the Hallucination tab's "Bilmiyorum" in Turkish
(dont_know_face()). Under Info: the tables, the models not compared and Our method. The question text, Turkish or
English, is never published. The tab ranks nothing on the Text tab and changes none of its numbers."""

from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any

import build_page as bp
from sitebuild.data import BLOB_URL
from sitebuild.site import ROOT, Site, esc, hbars, pct, rel
from sitebuild.vision import cell, joined, run_span

PATH = "english-reading/"
RECORD = ROOT / "english-reading.json"
# The options heading of the Text tab's prompts (runner/benchmark_ollama.py OPTIONS_HEADING); results.json gives the
# English one.
TURKISH_OPTIONS_HEADING = "Seçenekler:"
# The translator's name on the page, by model ID (english-reading.json translator.model).
TRANSLATORS = {"claude-opus-5-5": "Claude Opus 5.5"}
# A model asked in English under another model ID than its Turkish run: (provider, Turkish model ID, English model ID)
# with the reason, a clause after "because".
RENAMED = {
    ("liquid", "d1:free", "d1"): "Liquid's API no longer serves that name; its model list still names d1, released "
                                 "29 September 2026",
}
SIGNIFICANT = 0.05


def check(site: Site, data: dict[str, Any], record: dict[str, Any]) -> None:
    """Stops the build when results.json's english_reading, english-reading.json and page_config.json's english_reading
    disagree, or when the data no longer fits what the page says about it."""
    problems = []
    for key, ours in (("translations_sha256", "translations_sha256"), ("reading_questions", "reading_questions"),
                      ("questions", "kept"), ("flagged", "flagged")):
        if data[key] != record[ours]:
            problems.append(f"{key} {data[key]!r}, english-reading.json {ours} {record[ours]!r}")
    questions = record["questions"]
    kept = sum(1 for question in questions if question["kept"])
    reasons = Counter(reason for question in questions if not question["kept"] for reason in question["reasons"])
    if len(questions) != record["reading_questions"] or kept != record["kept"] or len(questions) - kept != record["flagged"]:
        problems.append("english-reading.json: its question list does not give its counts")
    if dict(reasons) != record["reasons"] or any(question["kept"] == bool(question["reasons"]) for question in questions):
        problems.append("english-reading.json: its reasons are not its flagged questions' reasons")
    turkish = site.answers["prompts"]["system_one_instructions"]
    if turkish.count("Turkish") != 1 or data["instructions"] != turkish.replace("Turkish", "English"):
        problems.append("the English instructions are not the System One instructions with Turkish changed to English")
    if record["translator"]["model"] not in TRANSLATORS:
        problems.append(f"no name for the translator {record['translator']['model']}")
    makers = {run["provider"] for run in site.runs if run["model"] == record["translator"]["model"]}
    if any(site.decision(run) for run in site.runs if run["provider"] in makers):
        problems.append("the translator's maker has a decision model on the Text tab")
    for model in data["models"]:
        run = site.by_id.get(model["turkish_run"])
        if run is None:
            problems.append(f"{model['name']}: Turkish run {model['turkish_run']} is not on the Text tab")
            continue
        if model["name"] != run["name"] or model["provider"] != run["provider"] or not site.decision(run):
            problems.append(f"{model['name']}: not the decision model of Turkish run {run['run']}")
        if run["questions_per_request"] != 1:
            problems.append(f"{model['name']}: Turkish run {run['run']} does not ask one question per request")
        if model["model"] != run["model"] and (run["provider"], run["model"], model["model"]) not in RENAMED:
            problems.append(f"{model['name']}: asked as {model['model']}, its Turkish run as {run['model']}, with no reason")
        if model["runs"][0] != model["run"] or model["turkish_runs"][0] != model["turkish_run"]:
            problems.append(f"{model['name']}: the first run is not the one compared")
        for side in ("english", "turkish"):
            counts = model[side]
            if counts["right"] + counts["wrong"] + counts["invalid"] != data["questions"]:
                problems.append(f"{model['name']}: its {side} answers do not cover the {data['questions']} questions")
        paired = model["paired"]
        if paired["english_only_right"] - paired["turkish_only_right"] != model["english"]["right"] - model["turkish"]["right"]:
            problems.append(f"{model['name']}: the paired counts do not give the difference in right answers")
    config = site.config["english_reading"]
    compared = {model["turkish_run"] for model in data["models"]}
    not_compared = [item["run"] for item in config["not_compared"]]
    for run in not_compared + config["skipped"]:
        if run not in site.by_id:
            problems.append(f"page_config.json english_reading: run {run} is not on the Text tab")
    for run in sorted(compared & (set(not_compared) | set(config["skipped"]))):
        problems.append(f"page_config.json english_reading: run {run} is compared and also listed as not compared or skipped")
    if set(not_compared) & set(config["skipped"]):
        problems.append("page_config.json english_reading: a run is both not compared and skipped")
    selected = config["selected"]
    if len(selected) != 20 or len(set(selected)) != len(selected):
        problems.append("page_config.json english_reading: selected does not list 20 runs once each")
    if set(selected) != compared | set(not_compared) | set(config["skipped"]):
        problems.append("page_config.json english_reading: selected is not the compared, not compared and skipped runs")
    for model in site.config["aa_decision_index"]["models"]:
        if model["run"] is not None and model["run"] not in selected:
            problems.append(f"page_config.json english_reading: {model['name']} (run {model['run']}) of the Decision "
                            "Index is not selected")
    if problems:
        raise SystemExit("english_reading:\n  " + "\n  ".join(problems))


def label(site: Site, model: dict[str, Any]) -> str:
    return site.row_name(site.by_id[model["turkish_run"]])


def href(site: Site, model: dict[str, Any]) -> str:
    return rel(PATH, site.model_path(site.by_id[model["turkish_run"]]))


def significant(model: dict[str, Any]) -> bool:
    return model["paired"]["p_holm"] < SIGNIFICANT


def direction(model: dict[str, Any]) -> str:
    """Which language the model scored higher in, as the headline and charts say it."""
    difference = model["english"]["right"] - model["turkish"]["right"]
    return "higher in English" if difference > 0 else "higher in Turkish" if difference < 0 else "the same in both"


def headline(site: Site, data: dict[str, Any]) -> str:
    """One line at the top of the tab: how many compared models scored higher in English, and how many of the
    differences are significant after Holm's correction."""
    models = data["models"]
    total = len(models)
    higher = sum(1 for model in models if model["english"]["right"] > model["turkish"]["right"])
    lower = sum(1 for model in models if model["english"]["right"] < model["turkish"]["right"])
    same = total - higher - lower
    noun = "model" if total == 1 else "models"
    first = (f"{bp.opening_count(higher) if higher else 'None'} of the {bp.in_words(total)} {noun} compared scored higher "
             "on the English translation than on the Turkish original")
    rest = []
    if lower:
        rest.append(f"{bp.in_words(lower)} scored lower")
    if same:
        rest.append(f"{bp.in_words(same)} the same")
    found = [model for model in models if significant(model)]
    if not found:
        verdict = ("the difference is not significant" if total == 1 else
                   "none of the differences is significant") + " after Holm's correction, so each could be chance"
    else:
        named = joined([f"{esc(label(site, model))} ({direction(model)})" for model in found])
        verdict = (f"{bp.in_words(len(found))} of the {bp.in_words(total)} differences "
                   f"{'is' if len(found) == 1 else 'are'} significant after Holm's correction: {named}")
    return (f"<p><strong>{first}</strong>{''.join('; ' + part for part in rest)}; {verdict} "
            '(<a href="#chart-paired">Paired test</a>).</p>')


def face(site: Site, data: dict[str, Any]) -> str:
    """The tab's face: two chart cards, accuracy in Turkish and in English, and the paired test of the two (the
    questions only one side got right, with Holm-adjusted p), every number from results.json's english_reading."""
    digits = site.config["percent_digits"]
    total = data["questions"]
    models = data["models"]

    def card(anchor: str, title: str, sub: str, rows: list[dict[str, Any]], legend: str, **axis: Any) -> str:
        return (f'<figure class="panel chart-card" id="{anchor}"><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{sub}</p></div>{hbars(rows, **axis)}<p class="chart-legend">{legend}</p></figure>')

    accuracy = card(
        "chart-accuracy", "Accuracy in Turkish and in English",
        f"Share of the {total:,} kept reading questions answered right: each model's first English run and its Text tab run "
        "· higher is better",
        [{"label": label(site, model), "href": href(site, model),
          "text": f"{pct(model['english']['accuracy'], digits)} · {pct(model['turkish']['accuracy'], digits)}",
          "bars": [{"value": model["english"]["accuracy"], "kind": "lead"}, {"value": model["turkish"]["accuracy"], "kind": "base"}],
          "title": f"{label(site, model)}: {model['english']['right']:,} of {total:,} right in English, "
                   f"{model['turkish']['right']:,} in Turkish ({100 * model['difference']:+.{digits}f} points)"}
         for model in models],
        '<span><i class="swatch swatch-lead"></i>English (first run)</span> '
        '<span><i class="swatch swatch-base"></i>Turkish (the Text tab run)</span>')
    tested = sorted(models, key=lambda model: (model["paired"]["p_holm"], model["paired"]["p"], label(site, model).casefold()))
    most = max(max(model["paired"]["english_only_right"], model["paired"]["turkish_only_right"]) for model in tested)
    # A tick at each quarter of the axis, the quarter a round number of answers that fits the largest count.
    quarter = math.ceil(most / 40) * 10 if most >= 40 else max(1, math.ceil(most / 4))
    counts = lambda model: (model["paired"]["english_only_right"], model["paired"]["turkish_only_right"])  # noqa: E731
    found = [model for model in tested if significant(model)]
    others = [model for model in tested if not significant(model)]

    def adjusted(group: list[dict[str, Any]]) -> str:
        """The group's Holm-adjusted p values as the site writes p ("each" when they read the same)."""
        texts = [esc(bp.p_text(model["paired"]["p_holm"])) for model in group]
        return f"{texts[0]}{' each' if len(group) > 1 else ''}" if len(set(texts)) == 1 else joined(texts)

    verdict = ((f"* A significant difference (Holm-adjusted p below {SIGNIFICANT:g}): "
                f"{esc(joined([label(site, model) for model in found]))} ({adjusted(found)}).") if found else
               f"No difference is significant (Holm-adjusted p below {SIGNIFICANT:g}).")
    if others:
        verdict += f" The other {len(others)}: {adjusted(others)}." if found else f" Adjusted: {adjusted(others)}."
    paired = card(
        "chart-paired", "Right only in English, or only in Turkish?",
        f"Each model's first English run against its Text tab run on the {total:,} kept questions: the questions only one of "
        f"the two got right, by the exact McNemar test with p adjusted by Holm's method over the {len(tested)} "
        f"model{'' if len(tested) == 1 else 's'} · the longer bar is the language with more right answers",
        [{"label": label(site, model), "href": href(site, model),
          "text": f"{counts(model)[0]:,} · {counts(model)[1]:,}{' *' if significant(model) else ''}",
          "bars": [{"value": counts(model)[0], "kind": "lead"}, {"value": counts(model)[1], "kind": "base"}],
          "title": f"{label(site, model)}: {counts(model)[0]:,} right only in English, {counts(model)[1]:,} right only in "
                   f"Turkish; exact McNemar {bp.p_text(model['paired']['p'])}, Holm-adjusted {bp.p_text(model['paired']['p_holm'])}"}
         for model in tested],
        '<span><i class="swatch swatch-lead"></i>Right only in English</span> '
        '<span><i class="swatch swatch-base"></i>Right only in Turkish</span> '
        f"<span>{verdict}</span>",
        top=4 * quarter, tick=lambda value: f"{value:,.0f}")
    return f'<section class="charts" aria-label="Charts">{accuracy}{paired}</section>'


def side_by_side(site: Site, data: dict[str, Any]) -> str:
    """A face card: each compared model's Turkish and English numbers in one row, Turkish first, ordered by Turkish
    accuracy: accuracy and its paired test, then with “I don't know” the non-hallucination rate (attempt rates in small
    text) and its paired test, every number from results.json's english_reading and english_reading.dont_know."""
    digits = site.config["percent_digits"]
    idk = data.get("dont_know") or {}
    matched = {(model["provider"], model["model"]): model for model in idk.get("models", [])}
    models = sorted(data["models"], key=lambda model: (-model["turkish"]["accuracy"], label(site, model).casefold()))
    p_cell = lambda p: esc(bp.p_text(p).removeprefix("p = ").removeprefix("p "))  # noqa: E731
    heads = ("Turkish accuracy", "English accuracy", "Accuracy difference (points)", "Accuracy Holm p",
             "Turkish non-hallucination", "English non-hallucination", "Non-hallucination difference (points)",
             "Non-hallucination Holm p")

    def rate(counts: dict[str, Any]) -> str:
        value = counts["non_hallucination"]
        shown = '<span class="nm">Not measured</span>' if value is None else pct(value, digits)
        return f'{shown}<span class="small">attempt rate {rate_text(counts["attempt_rate"], digits)}</span>'

    rows = []
    for model in models:
        values = [pct(model["turkish"]["accuracy"], digits), pct(model["english"]["accuracy"], digits),
                  f"{100 * model['difference']:+.{digits}f}",
                  p_cell(model["paired"]["p_holm"]) + (" *" if significant(model) else "")]
        other = matched.get((model["provider"], model["model"]))
        if other is None:
            values += ['<span class="nm">Not run</span>'] * 4
        else:
            tr, en = other["turkish"]["non_hallucination"], other["english"]["non_hallucination"]
            values += [rate(other["turkish"]), rate(other["english"]),
                       '<span class="nm">Not measured</span>' if tr is None or en is None else f"{100 * (en - tr):+.{digits}f}",
                       p_cell(other["paired"]["p_holm"]) + (" *" if idk_significant(other) else "")]
        name = f'<td class="model"><a class="model-name" href="{href(site, model)}">{esc(label(site, model))}</a></td>'
        rows.append(f"<tr>{name}" + "".join(cell(head, value) for head, value in zip(heads, values)) + "</tr>")
    short = "".join(f'<th scope="col" class="num">{name}</th>'
                    for name in ("Turkish", "English", "Difference (points)", "Holm p") * 2)
    head = ('<tr><th scope="col" rowspan="2">Model</th><th scope="colgroup" colspan="4">Accuracy</th>'
            '<th scope="colgroup" colspan="4">Non-hallucination with “I don\'t know”</th></tr>'
            f"<tr>{short}</tr>")
    links = ' (<a href="#dont-know">With “I don\'t know”</a>)' if idk else ""
    return (f'<section class="card" id="side-by-side"><h2>Turkish and English side by side</h2>'
            f'<div class="table-wrap"><table class="board list stack idk"><thead>{head}'
            f'</thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="note">Ordered by Turkish accuracy, highest first. Accuracy: right answers over the {data["questions"]:,} '
            "kept reading questions, the first English run against the Text tab run; the difference is English minus "
            f"Turkish in points; Holm p is the exact McNemar test with Holm's correction (<a href=\"#chart-accuracy\">Accuracy</a>, "
            f"<a href=\"#chart-paired\">Paired test</a>); * marks a Holm-adjusted p below {SIGNIFICANT:g}. Non-hallucination: "
            "“I don't know” / (“I don't know” + wrong) on the first runs with the option, read with the attempt rate under "
            f"it; its Holm p is the paired test of wrong answers{links}. The full tables are under "
            '<a href="#info">Info</a>.</p></section>')



def columns(data: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """The table's columns after the model: header and what it holds."""
    family = len(data["models"])
    return (
        ("English runs", "the first is compared; answers changed between runs where more than one"),
        ("Turkish runs", "the Text tab run, then its repeats; answers changed between them"),
        ("Turkish accuracy", "the Text tab run on the kept questions; range over its runs; higher is better"),
        ("English accuracy", "the first English run; range over its runs; higher is better"),
        ("Difference", "English minus Turkish, in points"),
        ("Right only in English", "questions the English run got right and the Turkish run did not"),
        ("Right only in Turkish", "questions the Turkish run got right and the English run did not"),
        ("p", "exact McNemar"),
        ("Holm p", f"adjusted over the {family} model{'' if family == 1 else 's'}"),
    )


def row(site: Site, data: dict[str, Any], model: dict[str, Any]) -> str:
    digits = site.config["percent_digits"]
    total = data["questions"]
    spread = model["spread"] or {}
    changed = model["answers_changed"] or {}

    def runs(side: str, numbers: list[int]) -> str:
        count = changed.get(side)
        return run_span(numbers) + ("" if count is None else
                                    f'<span class="small">{count:,} answer{"" if count == 1 else "s"} changed between runs</span>')

    def accuracy(side: str) -> str:
        counts, span = model[side], spread.get(side)
        invalid = f", {counts['invalid']:,} invalid" if counts["invalid"] else ""
        text = f'{pct(counts["accuracy"], digits)}<span class="small">{counts["right"]:,} of {total:,} right{invalid}</span>'
        if span and span["low"] == span["high"]:
            text += '<span class="small">the same in every run</span>'
        elif span:
            text += f'<span class="small">range {pct(span["low"], digits)} to {pct(span["high"], digits)}</span>'
        return text

    paired = model["paired"]
    values = [
        runs("english", model["runs"]),
        runs("turkish", model["turkish_runs"]),
        accuracy("turkish"),
        accuracy("english"),
        f"{100 * model['difference']:+.{digits}f}",
        f"{paired['english_only_right']:,}",
        f"{paired['turkish_only_right']:,}",
        esc(bp.p_text(paired["p"]).removeprefix("p = ").removeprefix("p ")),
        esc(bp.p_text(paired["p_holm"]).removeprefix("p = ").removeprefix("p ")) + (" *" if significant(model) else ""),
    ]
    heads = [f"{head} ({note})" for head, note in columns(data)]
    run = site.by_id[model["turkish_run"]]
    name = (f'<td class="model"><a class="model-name" href="{href(site, model)}">{esc(label(site, model))}</a>'
            f'<span class="small">{esc(site.detail(run))}</span></td>')
    return f"<tr>{name}" + "".join(cell(head, value) for head, value in zip(heads, values)) + "</tr>"


def table(site: Site, data: dict[str, Any]) -> str:
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>'
                   for name, note in columns(data))
    rows = "".join(row(site, data, model) for model in data["models"])
    return (f'<div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Model</th>{head}</tr>'
            f"</thead><tbody>{rows}</tbody></table></div>")


def not_compared(site: Site) -> str:
    """The Text tab models without an English comparison (page_config.json's english_reading): each group under the
    label its reasons open with ("Not compared", "Not run"), each model with the rest of its reason; then the models not
    run by decision, under skipped_reason's label, with its reason once. Names are the Text tab's."""
    config = site.config["english_reading"]
    groups: dict[str, list[str]] = {}
    for item in config["not_compared"]:
        head, reason = item["reason"].split(": ", 1)
        groups.setdefault(head, []).append(
            f"<li><strong>{esc(site.row_name(site.by_id[item['run']]))}</strong>: {esc(reason)}</li>")
    out = "".join(f'<h3 class="board-group">{esc(head)}</h3><ul>{"".join(lines)}</ul>' for head, lines in groups.items())
    if config["skipped"]:
        head, reason = config["skipped_reason"].split(": ", 1)
        names = joined([esc(site.row_name(site.by_id[run])) for run in config["skipped"]])
        out += f'<h3 class="board-group">{esc(head)}</h3><p>{names}: {esc(reason)}</p>'
    return out


def reason_name(key: str) -> str:
    return key.replace("_", " ")


def units_text(record: dict[str, Any]) -> str:
    units = sorted({question["unit"] for question in record["questions"]})
    if units != list(range(units[0], units[-1] + 1)):
        return "units " + joined([str(unit) for unit in units])
    return f"units {units[0]} to {units[-1]}"


def runs_text(site: Site, data: dict[str, Any]) -> str:
    """How many English runs each model has, from the data: the models with more than one named, by count."""
    by_count: dict[int, list[str]] = {}
    for model in data["models"]:
        by_count.setdefault(len(model["runs"]), []).append(esc(label(site, model)))
    parts = [f"{bp.in_words(count)} run{'' if count == 1 else 's'} for {joined(names)}"
             for count, names in sorted(by_count.items(), reverse=True) if count > 1]
    if 1 in by_count:
        single = len(by_count[1])
        parts.append(f"one for the other {bp.in_words(single)}" if parts else "one for each")
    return "; ".join(parts)


def renamed_text(site: Site, data: dict[str, Any]) -> str:
    """The models asked in English under another model ID than their Turkish runs, each with its reason."""
    sentences = []
    for model in data["models"]:
        run = site.by_id[model["turkish_run"]]
        if model["model"] != run["model"]:
            sentences.append(f" {esc(label(site, model))} was asked as <code>{esc(model['model'])}</code>, while its Turkish "
                             f"runs used <code>{esc(run['model'])}</code>, because "
                             f"{esc(RENAMED[(run['provider'], run['model'], model['model'])])}.")
    return "".join(sentences)


def check_dont_know(site: Site, data: dict[str, Any], idk: dict[str, Any]) -> None:
    """Stops the build when results.json's english_reading.dont_know does not add up: each side's answers cover the
    kept questions, its rates are its counts, the paired counts give the difference in wrong answers, the first run is
    the one compared, and every model is one of the accuracy comparison's."""
    problems = []
    total = idk["questions"]
    if total != data["questions"]:
        problems.append(f"{total} questions, the accuracy comparison {data['questions']}")
    compared = {model["turkish_run"]: model for model in data["models"]}
    close = lambda a, b: a is not None and abs(a - b) < 1e-9  # noqa: E731
    for model in idk["models"]:
        name = model["name"]
        other = compared.get(model["text_run"])
        if other is None:
            problems.append(f"{name}: Text tab run {model['text_run']} is not in the accuracy comparison")
            continue
        if name != other["name"] or model["provider"] != other["provider"] or model["model"] != other["model"]:
            problems.append(f"{name}: not the model of the accuracy comparison's run {model['text_run']}")
        for side in ("english", "turkish"):
            counts = model[side]
            if counts["right"] + counts["wrong"] + counts["dont_know"] + counts["invalid"] != total:
                problems.append(f"{name}: its {side} answers do not add up to {total}")
            if not close(counts["accuracy"], counts["right"] / total) or \
                    not close(counts["attempt_rate"], (counts["right"] + counts["wrong"]) / total):
                problems.append(f"{name}: its {side} accuracy or attempt rate is not its counts")
            unsure = counts["dont_know"] + counts["wrong"]
            if (counts["non_hallucination"] is None) != (unsure == 0) or \
                    (unsure and not close(counts["non_hallucination"], counts["dont_know"] / unsure)):
                problems.append(f"{name}: its {side} non-hallucination rate is not its counts")
            if not counts["runs"] or counts["runs"][0] != counts["run"]:
                problems.append(f"{name}: the first {side} run is not the one compared")
        paired = model["paired"]
        if paired["english_only_wrong"] - paired["turkish_only_wrong"] != model["english"]["wrong"] - model["turkish"]["wrong"]:
            problems.append(f"{name}: the paired counts do not give the difference in wrong answers")
        if paired["english_only_wrong"] > model["english"]["wrong"] or paired["turkish_only_wrong"] > model["turkish"]["wrong"]:
            problems.append(f"{name}: more wrong answers only on one side than on that side")
        if not (0 <= paired["p"] <= paired["p_holm"] <= 1):
            problems.append(f"{name}: p {paired['p']} and Holm p {paired['p_holm']} do not fit")
        if model["english"].get("subset"):
            problems.append(f"{name}: the English side is marked as a subset run")
    if problems:
        raise SystemExit("english_reading dont_know:\n  " + "\n  ".join(problems))


def idk_label(site: Site, model: dict[str, Any]) -> str:
    return site.row_name(site.by_id[model["text_run"]])


def idk_href(site: Site, model: dict[str, Any]) -> str:
    return rel(PATH, site.model_path(site.by_id[model["text_run"]]))


def idk_significant(model: dict[str, Any]) -> bool:
    return model["paired"]["p_holm"] < SIGNIFICANT


def rate_text(value: float | None, digits: int) -> str:
    return "not measured" if value is None else pct(value, digits)


def dont_know_summary(site: Site, idk: dict[str, Any]) -> str:
    """One paragraph from the data: how many models had the higher non-hallucination rate in English, and which paired
    differences in wrong answers are significant after Holm's correction."""
    models = idk["models"]
    total = len(models)
    rated = [model for model in models
             if model["english"]["non_hallucination"] is not None and model["turkish"]["non_hallucination"] is not None]
    higher = sum(1 for model in rated if model["english"]["non_hallucination"] > model["turkish"]["non_hallucination"])
    lower = sum(1 for model in rated if model["english"]["non_hallucination"] < model["turkish"]["non_hallucination"])
    parts = [f"{bp.opening_count(higher) if higher else 'None'} of the {bp.in_words(total)} models had a higher "
             "non-hallucination rate in English than in Turkish"]
    if lower:
        parts.append(f"{bp.in_words(lower)} lower")
    if len(rated) - higher - lower:
        parts.append(f"{bp.in_words(len(rated) - higher - lower)} the same")
    if total - len(rated):
        parts.append(f"{bp.in_words(total - len(rated))} without a rate on one side")
    found = [model for model in models if idk_significant(model)]
    if not found:
        verdict = ("none of the differences in wrong answers is significant after Holm's correction, so each could be "
                   "chance")
    else:
        named = joined([f"{esc(idk_label(site, model))} (more wrong answers in "
                        f"{'English' if model['paired']['english_only_wrong'] > model['paired']['turkish_only_wrong'] else 'Turkish'})"
                        for model in found])
        verdict = (f"{bp.in_words(len(found))} of the {bp.in_words(total)} differences in wrong answers "
                   f"{'is' if len(found) == 1 else 'are'} significant after Holm's correction: {named}")
    return (f"<p>{'; '.join(parts)}; {verdict} (<a href=\"#chart-idk-paired\">Paired test</a>). Read each rate with its "
            "attempt rate: a model that always chose the option would reach 100%.</p>")


def dont_know_face(site: Site, idk: dict[str, Any]) -> str:
    """The section's face: a heading and summary, then two chart cards: the non-hallucination rate in English and in
    Turkish (attempt rates in the text and tooltip) and the paired test of wrong answers (as the Hallucination tab's
    #chart-paired), every number from results.json's english_reading.dont_know."""
    digits = site.config["percent_digits"]
    option = esc(idk["option"])
    total = idk["questions"]
    models = idk["models"]

    def card(anchor: str, title: str, sub: str, rows: list[dict[str, Any]], legend: str, **axis: Any) -> str:
        return (f'<figure class="panel chart-card" id="{anchor}"><div class="chart-head"><h2>{esc(title)}</h2>'
                f'<p class="chart-sub">{sub}</p></div>{hbars(rows, **axis)}<p class="chart-legend">{legend}</p></figure>')

    def side_title(model: dict[str, Any], side: str, language: str) -> str:
        counts = model[side]
        return (f"{language} {rate_text(counts['non_hallucination'], digits)} ({counts['dont_know']:,} “{idk['option']}” "
                f"of {counts['dont_know'] + counts['wrong']:,} not right), attempt rate {pct(counts['attempt_rate'], digits)}")

    rates = card(
        "chart-idk-rates", "Non-hallucination rate in English and in Turkish",
        f"“{option}” among the answers that were not right, on the {total:,} kept questions: each model's first run in each "
        "language · higher is better, read with the attempt rate (under the chart and in each bar's tooltip)",
        [{"label": idk_label(site, model), "href": idk_href(site, model),
          "text": f"{rate_text(model['english']['non_hallucination'], digits)} · "
                  f"{rate_text(model['turkish']['non_hallucination'], digits)}",
          "bars": [{"value": model["english"]["non_hallucination"] or 0, "kind": "lead"},
                   {"value": model["turkish"]["non_hallucination"] or 0, "kind": "base"}],
          "title": f"{idk_label(site, model)}: {side_title(model, 'english', 'English')}; "
                   f"{side_title(model, 'turkish', 'Turkish')}"}
         for model in models],
        '<span><i class="swatch swatch-lead"></i>English, with “I don\'t know”</span> '
        '<span><i class="swatch swatch-base"></i>Turkish, with “Bilmiyorum”</span> '
        "<span>Attempt rate, English · Turkish: "
        + esc("; ".join(f"{idk_label(site, model)} {pct(model['english']['attempt_rate'], digits)} · "
                        f"{pct(model['turkish']['attempt_rate'], digits)}" for model in models))
        + ". A model that always chose the option would reach 100% with no right answers.</span>")
    tested = sorted(models, key=lambda model: (model["paired"]["p_holm"], model["paired"]["p"], idk_label(site, model).casefold()))
    counts = lambda model: (model["paired"]["english_only_wrong"], model["paired"]["turkish_only_wrong"])  # noqa: E731
    most = max(max(counts(model)) for model in tested)
    # A tick at each quarter of the axis, the quarter a round number of answers that fits the largest count.
    quarter = math.ceil(most / 40) * 10 if most >= 40 else max(1, math.ceil(most / 4))
    found = [model for model in tested if idk_significant(model)]
    others = [model for model in tested if not idk_significant(model)]

    def adjusted(group: list[dict[str, Any]]) -> str:
        texts = [esc(bp.p_text(model["paired"]["p_holm"])) for model in group]
        return f"{texts[0]}{' each' if len(group) > 1 else ''}" if len(set(texts)) == 1 else joined(texts)

    verdict = ((f"* A significant difference (Holm-adjusted p below {SIGNIFICANT:g}): "
                f"{esc(joined([idk_label(site, model) for model in found]))} ({adjusted(found)}).") if found else
               f"No difference is significant (Holm-adjusted p below {SIGNIFICANT:g}).")
    if others:
        verdict += f" The other {len(others)}: {adjusted(others)}." if found else f" Adjusted: {adjusted(others)}."
    paired = card(
        "chart-idk-paired", "Wrong only in English, or only in Turkish?",
        f"Each model's first run in each language, both with the option, on the {total:,} kept questions: the questions only "
        f"one of the two got wrong, by the exact McNemar test with p adjusted by Holm's method over the {len(tested)} "
        f"model{'' if len(tested) == 1 else 's'} · the shorter bar is the language with fewer wrong answers",
        [{"label": idk_label(site, model), "href": idk_href(site, model),
          "text": f"{counts(model)[0]:,} · {counts(model)[1]:,}{' *' if idk_significant(model) else ''}",
          "bars": [{"value": counts(model)[0], "kind": "lead"}, {"value": counts(model)[1], "kind": "base"}],
          "title": f"{idk_label(site, model)}: {counts(model)[0]:,} wrong only in English, {counts(model)[1]:,} wrong only "
                   f"in Turkish; exact McNemar {bp.p_text(model['paired']['p'])}, Holm-adjusted {bp.p_text(model['paired']['p_holm'])}"}
         for model in tested],
        '<span><i class="swatch swatch-lead"></i>Wrong only in English</span> '
        '<span><i class="swatch swatch-base"></i>Wrong only in Turkish</span> '
        f"<span>{verdict}</span>",
        top=4 * quarter, tick=lambda value: f"{value:,.0f}")
    return (f'<section class="card" id="dont-know"><h2>With an “I don\'t know” option</h2>'
            f"<p>The same {total:,} kept questions with a sixth option, “{option}” in English and “Bilmiyorum” in Turkish, as "
            f'on the <a href="{rel(PATH, "dont-know/")}">Hallucination tab</a>, asked of the same models '
            f'(<a href="#dont-know-method">how</a>).</p>{dont_know_summary(site, idk)}</section>'
            f'<section class="charts" aria-label="Charts with “I don\'t know”">{rates}{paired}</section>')


def dont_know_columns(idk: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    family = len(idk["models"])
    option = idk["option"]
    return (
        ("English runs", "with “I don't know”; the first is compared"),
        ("Turkish runs", "with “Bilmiyorum”; the first is compared"),
        ("English non-hallucination", f"“{option}” / (“{option}” + wrong); higher is better, read with the attempt rate"),
        ("Turkish non-hallucination", "“Bilmiyorum” / (“Bilmiyorum” + wrong); higher is better, read with the attempt rate"),
        ("English attempt rate", f"(right + wrong) / {idk['questions']:,}"),
        ("Turkish attempt rate", f"(right + wrong) / {idk['questions']:,}"),
        ("English accuracy", "higher is better"),
        ("Turkish accuracy", "higher is better"),
        ("English mean probability", f"of “{option}”"),
        ("Turkish mean probability", "of “Bilmiyorum”"),
        ("Wrong only in English", "questions the English run got wrong and the Turkish run did not"),
        ("Wrong only in Turkish", "questions the Turkish run got wrong and the English run did not"),
        ("p", "exact McNemar"),
        ("Holm p", f"adjusted over the {family} model{'' if family == 1 else 's'}"),
    )


def dont_know_row(site: Site, idk: dict[str, Any], model: dict[str, Any]) -> str:
    digits = site.config["percent_digits"]
    total = idk["questions"]
    spread = model["spread"] or {}

    def span(side: str, key: str) -> str:
        values = (spread.get(side) or {}).get(key)
        if not values or values[0] is None:
            return ""
        if values[0] == values[1]:
            return '<span class="small">the same in every run</span>'
        return f'<span class="small">range {pct(values[0], digits)} to {pct(values[1], digits)}</span>'

    def value(side: str, key: str, note: str) -> str:
        number = model[side][key]
        shown = '<span class="nm">Not measured</span>' if number is None else pct(number, digits)
        return f'{shown}<span class="small">{note}</span>{span(side, key)}'

    def runs(side: str) -> str:
        counts = model[side]
        if side == "english":
            source = "new runs" if len(counts["runs"]) > 1 else "a new run"
        elif counts.get("subset"):
            source = "new runs on the kept questions" if len(counts["runs"]) > 1 else "a new run on the kept questions"
        else:
            source = "the Hallucination tab's full runs, counted on the kept questions"
        return run_span(counts["runs"]) + f'<span class="small">{source}</span>'

    def option(side: str) -> str:
        return idk["option"] if side == "english" else "Bilmiyorum"

    def not_right(side: str) -> str:
        counts = model[side]
        return f"{counts['dont_know']:,} “{esc(option(side))}” of {counts['dont_know'] + counts['wrong']:,} not right"

    def answered(side: str) -> str:
        counts = model[side]
        invalid = f", {counts['invalid']:,} invalid" if counts["invalid"] else ""
        return f"{counts['right'] + counts['wrong']:,} answered, {counts['dont_know']:,} “{esc(option(side))}”{invalid}"

    paired = model["paired"]
    values = [
        runs("english"), runs("turkish"),
        value("english", "non_hallucination", not_right("english")), value("turkish", "non_hallucination", not_right("turkish")),
        value("english", "attempt_rate", answered("english")), value("turkish", "attempt_rate", answered("turkish")),
        value("english", "accuracy", f"{model['english']['right']:,} of {total:,} right"),
        value("turkish", "accuracy", f"{model['turkish']['right']:,} of {total:,} right"),
        value("english", "mean_dont_know_probability", ""), value("turkish", "mean_dont_know_probability", ""),
        f"{paired['english_only_wrong']:,}", f"{paired['turkish_only_wrong']:,}",
        esc(bp.p_text(paired["p"]).removeprefix("p = ").removeprefix("p ")),
        esc(bp.p_text(paired["p_holm"]).removeprefix("p = ").removeprefix("p ")) + (" *" if idk_significant(model) else ""),
    ]
    heads = [f"{head} ({note})" for head, note in dont_know_columns(idk)]
    run = site.by_id[model["text_run"]]
    name = (f'<td class="model"><a class="model-name" href="{idk_href(site, model)}">{esc(idk_label(site, model))}</a>'
            f'<span class="small">{esc(site.detail(run))}</span></td>')
    return f"<tr>{name}" + "".join(cell(head, item) for head, item in zip(heads, values)) + "</tr>"


def dont_know_table(site: Site, idk: dict[str, Any]) -> str:
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>'
                   for name, note in dont_know_columns(idk))
    rows = "".join(dont_know_row(site, idk, model) for model in idk["models"])
    return (f'<div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Model</th>{head}</tr>'
            f"</thead><tbody>{rows}</tbody></table></div>")


def dont_know_sources(site: Site, idk: dict[str, Any]) -> str:
    """Each model's Turkish side, from the data: the Hallucination tab's published full runs counted on the kept
    questions, or new runs on the kept questions; then the models asked under another model ID than their Text tab run."""
    published = [model for model in idk["models"] if not model["turkish"].get("subset")]
    new = [model for model in idk["models"] if model["turkish"].get("subset")]
    parts = []
    if published:
        parts.append("the Hallucination tab's published full runs, counted on the kept questions only, for "
                     + joined([f"{esc(idk_label(site, model))} ({run_span(model['turkish']['runs'])})" for model in published]))
    if new:
        parts.append("new runs on the kept questions only, with the Hallucination tab's prompts, for "
                     + joined([f"{esc(idk_label(site, model))} ({run_span(model['turkish']['runs'])})" for model in new]))
    text = f"<p>The Turkish side: {'; '.join(parts)}. The new Turkish runs are not on the Hallucination tab, which uses full runs only.</p>"
    for model in idk["models"]:
        run = site.by_id[model["text_run"]]
        if model["model"] != run["model"]:
            text += (f"<p>{esc(idk_label(site, model))} was asked as <code>{esc(model['model'])}</code> in both languages, "
                     f"while its Text tab run used <code>{esc(run['model'])}</code>, because "
                     f"{esc(RENAMED[(run['provider'], run['model'], model['model'])])}.</p>")
    return text


def dont_know_runs(site: Site, idk: dict[str, Any]) -> str:
    """How many runs each model has on each side, grouped by the pair of counts."""
    by_count: dict[tuple[int, int], list[str]] = {}
    for model in idk["models"]:
        by_count.setdefault((len(model["english"]["runs"]), len(model["turkish"]["runs"])), []).append(esc(idk_label(site, model)))
    words = lambda count: f"{bp.in_words(count)} run{'' if count == 1 else 's'}"  # noqa: E731
    return "; ".join(f"{words(english)} in English and {words(turkish)} in Turkish for {joined(names)}"
                     for (english, turkish), names in sorted(by_count.items(), reverse=True))


def dont_know_info(site: Site, idk: dict[str, Any]) -> str:
    """Under Info: the table and the method notes of the “I don't know” section."""
    total = f"{idk['questions']:,}"
    option = esc(idk["option"])
    family = len(idk["models"])
    return f"""
    <section class="card" id="dont-know-results">
      <h2>Results with an “I don't know” option</h2>
      <p class="note">Ordered by the non-hallucination rate in English, highest first. Each row compares the model's first run with “{option}” in English with its first run with “Bilmiyorum” in Turkish, out of the {total} kept questions. Where a side has more than one run, its rates show the range over its runs. The paired counts, p and the Holm-adjusted p (over the {family} model{"" if family == 1 else "s"}) are those of the exact McNemar test on wrong answers; * marks a Holm-adjusted p below {SIGNIFICANT:g}.</p>
      {dont_know_table(site, idk)}
    </section>
    <section class="card method-notes" id="dont-know-method">
      <h2>Our method with an “I don't know” option</h2>
      <h3>The option</h3>
      <p>As on the <a href="{rel(PATH, "dont-know/")}">Hallucination tab</a>, each question gets a sixth option after its own five: F, “{option}” in English, “Bilmiyorum” in Turkish. It is always the last option, never shuffled and never correct. The English reading instructions get one added sentence: “{esc(idk["sentence"])}” The full instructions:</p>
      <blockquote><p>{esc(idk["instructions"])}</p></blockquote>
      <p>Prompt version {esc(idk["prompt_version"])}. The question and its options are the English translation, as in the accuracy comparison above; no person checked the translations. The Turkish side uses the Hallucination tab's prompts unchanged.</p>
      <h3>The Turkish side</h3>
      {dont_know_sources(site, idk)}
      <h3>Runs</h3>
      <p>{dont_know_runs(site, idk)}. These runs are kept out of the leaderboard, its repeats, the Hallucination tab and the accuracy comparison above.</p>
      <h3>The rates and how to read them</h3>
      <p>Each answer is right, wrong, the option or invalid. Out of the {total} kept questions, accuracy is right / {total}, the attempt rate is (right + wrong) / {total}, and the non-hallucination rate is the option / (the option + wrong): among the answers that were not right, the share where the model said it did not know. As the Hallucination tab says, it is not a direct measure of what the model does not know: a model that always chose the option would reach 100% with no right answers, so read it with the attempt rate. With neither a wrong answer nor the option, the rate is undefined (Not measured). The mean probability is the probability the model gave the option, averaged over its answers that report option probabilities. The paired test is the exact McNemar test on the questions only one of the two first runs got wrong, with p adjusted by Holm's method over the {family} model{"" if family == 1 else "s"}. No new combined score is made from these rates.</p>
    </section>"""


def languages(site: Site) -> str:
    """Languages the model cards list: one row per model of page_config.json's model_languages (each card or maker's
    docs as checked), the model named as the Text tab names its run. The sentence above the table is computed from the
    entries; the build stops when they no longer fit it."""
    config = site.config["model_languages"]
    models = config["models"]
    stated = [model for model in models if model["languages"] != "not stated"]
    tagged = [model for model in stated if model["languages"].startswith("English (the card's `language: en` tag")]
    quoted = [model for model in stated if model["languages"].startswith('"')]
    primary = [model for model in quoted if "English is the primary" in model["languages"]]
    if len(tagged) + len(quoted) != len(stated) or primary != quoted or not tagged or not quoted:
        raise SystemExit("page_config.json model_languages: the sentence expects cards that name English by their tag and "
                         "docs that call English the primary language, and no other statement")
    if any("turkish" in model["languages"].casefold() for model in models):
        raise SystemExit("page_config.json model_languages: the sentence says no card names Turkish")
    name = lambda model: site.row_name(site.by_id[model["run"]])  # noqa: E731
    code = lambda text: "<code>".join(esc(text).split("`", 1)).replace("`", "</code>", 1) if text.count("`") == 2 else esc(text)  # noqa: E731
    rows = "".join(
        f'<tr><td class="model"><a class="model-name" href="{rel(PATH, site.model_path(site.by_id[model["run"]]))}">'
        f'{esc(name(model))}</a></td><td data-label="Languages listed">{code(model["languages"])}</td>'
        f'<td data-label="Source"><a href="{esc(model["source"])}">{esc(model["source"].split("//", 1)[1].split("/", 1)[0])}</a></td>'
        f'<td data-label="Checked">{esc(config["checked"])}</td></tr>' for model in models)
    maker = lambda model: esc(name(model).split()[0])  # noqa: E731
    summary = (f"<p>Of the {len(models)} models whose cards or docs we checked, only "
               f"{joined([esc(name(model)) for model in tagged])} name a language: English, by the card's "
               f"<code>language: en</code> tag. {joined([maker(model) for model in quoted])}'s docs call English "
               f"its primary language. No card names Turkish.</p>")
    return f"""
    <section class="card" id="languages">
      <h2>Languages the model cards list</h2>
      {summary}
      <p class="note">Each model's card at the revision we ran (local weights) or its maker's model page and docs (APIs), searched for language statements and the Hugging Face <code>language:</code> field, on {esc(config["checked"])}. “not stated”: neither names a language.</p>
      <div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">Model</th><th scope="col">Languages listed</th><th scope="col">Source</th><th scope="col">Checked</th></tr></thead><tbody>{rows}</tbody></table></div>
    </section>"""


def build(site: Site) -> dict[str, str]:
    if "english_reading" not in site.results:
        return {}
    data = site.results["english_reading"]
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    check(site, data, record)
    idk = data.get("dont_know")
    if idk:
        check_dont_know(site, data, idk)
    kept, flagged, reading = f"{data['questions']:,}", f"{data['flagged']:,}", f"{data['reading_questions']:,}"
    translator, prompts = record["translator"], record["prompts"]
    translator_name = TRANSLATORS[translator["model"]]
    family = len(data["models"])
    selected = len(site.config["english_reading"]["selected"])
    selection = (f"{esc(site.config['english_reading']['selection'])} {bp.in_words(family).capitalize()} of them are "
                 f"compared here; the other {bp.in_words(selected - family)} are listed under the results with their reasons.")
    turkish_instructions = site.answers["prompts"]["system_one_instructions"]
    enum = prompts["flag"]["schema"]["properties"]["reasons"]["items"]["enum"]
    reasons = "".join(f"<li>{esc(reason_name(key))}: {record['reasons'][key]:,}</li>" for key in enum if key in record["reasons"])
    script = f'<a href="{BLOB_URL}runner/translate_reading.py"><code>runner/translate_reading.py</code></a>'
    download = f'<a href="{rel(PATH, "english-reading.json")}" download>english-reading.json</a>'
    body = f"""    {site.tabs(PATH)}
    <section class="card">
      <p class="eyebrow">English reading</p>
      <h1>The Text tab's reading questions, asked in English</h1>
      <p>{kept} of the Text tab's {reading} reading questions, translated into English by a model, asked of {bp.in_words(family)} of the {selected} decision models we chose (<a href="#about">which ones</a>) as on the Text tab and compared with the same models' Turkish runs on the same questions. No person checked the translations: a limit of this test (<a href="#method">Our method</a>). This tab is separate from the leaderboard; it ranks nothing on the Text tab and changes none of its numbers.</p>
      {headline(site, data)}
      <nav class="face-nav" aria-label="On this page"><a href="#side-by-side">Side by side</a><a href="#chart-accuracy">Accuracy</a><a href="#chart-paired">Paired test</a>{'<a href="#dont-know">I don&#x27;t know</a>' if idk else ""}<a href="#info">Info</a><a href="#languages">Languages</a></nav>
    </section>
    {side_by_side(site, data)}
    {face(site, data)}
    {dont_know_face(site, idk) if idk else ""}
    <details class="info info-details" id="info">
      <summary class="info-summary"><span class="info-title">Info</span> <span class="info-sub">The table, the models not compared and our method{", then the same with “I don't know”" if idk else ""}</span></summary>
    <section class="card" id="about">
      <h2>About this test</h2>
      <p>{selection}</p>
      <p>The Text tab's reading questions ({esc(units_text(record))}; the grammar questions are left out) were translated into English by {esc(translator_name)}. The same model flagged the questions whose answer depends on Turkish wording; the {flagged} flagged questions are left out and the other {kept} kept. Each of the {bp.in_words(family)} compared models answered the kept questions in English and is compared with its own Text tab run on the same {kept} questions.</p>
      <p class="note">Download: <a href="{rel(PATH, "results.json")}" download>results.json</a> (the comparison's numbers, under <code>english_reading</code>), <a href="{rel(PATH, "answers.json")}" download>answers.json</a> (each English run's answers, under <code>english_runs</code>) and {download} (the translator, its prompts, the flags, the question units and each question's hash of its English text; no question text).</p>
    </section>
    <section class="card" id="results">
      <h2>Results</h2>
      <p class="note">Ordered by accuracy in English, highest first. Each row compares the model's first English run with its Text tab run, out of the {kept} kept questions; an invalid answer counts as not right. Where a side has more than one run, its accuracy shows the range over its runs and its runs show how many answers changed between them. The paired counts, p and the Holm-adjusted p (over the {family} model{"" if family == 1 else "s"}) are those of the exact McNemar test; * marks a Holm-adjusted p below {SIGNIFICANT:g}.</p>
      {table(site, data)}
      {not_compared(site)}
    </section>
    <section class="card method-notes" id="method">
      <h2>Our method</h2>
      <h3>The translation</h3>
      <p>The translator is {esc(translator_name)} (<code>{esc(translator["model"])}</code>) at effort {esc(translator["effort"])}; route: {esc(translator["route"])}, Claude Code version {esc(translator["claude_code"].removesuffix(" (Claude Code)"))}. Its maker has no decision model on our board. It was told to translate faithfully, keep the option letters and their order, not solve the question and not add or remove information (translation prompt version {esc(prompts["translate"]["version"])}).</p>
      <h3>The flags</h3>
      <p>In a separate request, the same model was shown each Turkish question, its English translation and the keyed option, and asked whether answering it correctly depends on Turkish wording, with the reasons (flag prompt version {esc(prompts["flag"]["version"])}). It flagged {flagged} of the {reading} questions; they are left out, and {kept} are kept. By reason, as a flagged question can have several:</p>
      <ul>{reasons}</ul>
      <p>No person checked the translations or the flags, and this is a limit of the method: a translation error, or a question whose answer still depends on Turkish wording that the model did not flag, would stay among the {kept} kept questions and could move a model's accuracy in English. Both prompts in full are in {download} and {script}.</p>
      <h3>Asking the decision models</h3>
      <p>Each model is asked exactly as on the Text tab, with its own settings, one question per request, and with its option probabilities, except for one word of the System One instructions, the options heading and the question itself. The Text tab's instructions:</p>
      <blockquote><p>{esc(turkish_instructions)}</p></blockquote>
      <p>The English runs' instructions:</p>
      <blockquote><p>{esc(data["instructions"])}</p></blockquote>
      <p>The options follow the heading “{esc(data["options_heading"])}” instead of “{esc(TURKISH_OPTIONS_HEADING)}”, and the question and its options are the English translation. Prompt version {esc(data["prompt_version"])}; every English run used the translations with SHA-256 <code>{esc(data["translations_sha256"])}</code>.{renamed_text(site, data)}{"".join(" " + esc(note) for note in site.config["english_reading"].get("method_notes", []))}</p>
      <h3>Runs</h3>
      <p>One English run per model; five where the model's repeated Turkish runs on the Text tab changed answers. Here: {runs_text(site, data)}. The English runs are kept out of the leaderboard and its repeats.</p>
      <h3>The comparison</h3>
      <p>On the {kept} kept questions only: accuracy is the right answers over {kept} for the first English run and for the Text tab run (an invalid answer counts as not right), and the difference is English minus Turkish. The paired test is the exact McNemar test on the questions only one of the two runs got right, with p adjusted by Holm's method over the {family} model{"" if family == 1 else "s"} compared. Where a side has more than one run, its range is the lowest and highest accuracy over its runs, and its answers changed are the kept questions whose answer differs between them.</p>
      <h3>Why the translations are not published</h3>
      <p>The site never publishes question text, Turkish or English: the publisher owns the questions. {download} holds instead each reading question's ID, unit, whether it was kept, its flag reasons and the SHA-256 of its English text, with the translator and both prompts, so that a copy of these translations can be checked against it. Translating again with {script} need not give the same text word for word.</p>
    </section>{dont_know_info(site, idk) if idk else ""}{languages(site)}
    </details>"""
    return {PATH: site.page(PATH, "English reading",
                            f"The Text tab's {kept} kept reading questions in English: accuracy of {family} decision models "
                            "in English against Turkish, with a paired test.", body)}
