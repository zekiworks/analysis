"""English reading (english-reading/), the site's fourth tab: the Text tab's reading questions translated into English,
asked of the decision models as on the Text tab, against the same models' Turkish runs on the same questions. From
results.json's `english_reading` (every number), english-reading.json (the track's public record: the translator, its
prompts, the flags and each question's hash of its English text) and page_config.json's `english_reading` (the models
not compared or not run, with their reasons). Its face, as the Hallucination tab's, is charts in HTML (Site hbars):
accuracy in both languages and the paired test. Under Info: the table, the models not compared and Our method. The
question text, Turkish or English, is never published. The tab ranks nothing on the Text tab and changes none of its
numbers."""

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
    ("liquid", "d1:free", "d1"): "Liquid's API no longer serves the d1:free name its Turkish runs used; its model list "
                                 "still names d1, released 29 September 2026",
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
        esc(bp.p_text(paired["p"]).removeprefix("p = ")),
        esc(bp.p_text(paired["p_holm"]).removeprefix("p = ")) + (" *" if significant(model) else ""),
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


def build(site: Site) -> dict[str, str]:
    if "english_reading" not in site.results:
        return {}
    data = site.results["english_reading"]
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    check(site, data, record)
    kept, flagged, reading = f"{data['questions']:,}", f"{data['flagged']:,}", f"{data['reading_questions']:,}"
    translator, prompts = record["translator"], record["prompts"]
    translator_name = TRANSLATORS[translator["model"]]
    family = len(data["models"])
    turkish_instructions = site.answers["prompts"]["system_one_instructions"]
    enum = prompts["flag"]["schema"]["properties"]["reasons"]["items"]["enum"]
    reasons = "".join(f"<li>{esc(reason_name(key))}: {record['reasons'][key]:,}</li>" for key in enum if key in record["reasons"])
    script = f'<a href="{BLOB_URL}runner/translate_reading.py"><code>runner/translate_reading.py</code></a>'
    download = f'<a href="{rel(PATH, "english-reading.json")}" download>english-reading.json</a>'
    body = f"""    {site.tabs(PATH)}
    <section class="card">
      <p class="eyebrow">English reading</p>
      <h1>The Text tab's reading questions, asked in English</h1>
      <p>{kept} of the Text tab's {reading} reading questions, translated into English by a model, asked of the decision models as on the Text tab and compared with the same models' Turkish runs on the same questions. No person checked the translations: a limit of this test (<a href="#method">Our method</a>). This tab is separate from the leaderboard; it ranks nothing on the Text tab and changes none of its numbers.</p>
      {headline(site, data)}
      <nav class="face-nav" aria-label="On this page"><a href="#chart-accuracy">Accuracy</a><a href="#chart-paired">Paired test</a><a href="#info">Info</a></nav>
    </section>
    {face(site, data)}
    <details class="info info-details" id="info">
      <summary class="info-summary"><span class="info-title">Info</span> <span class="info-sub">The table, the models not compared and our method</span></summary>
    <section class="card">
      <h2>About this test</h2>
      <p>The Text tab's reading questions ({esc(units_text(record))}; the grammar questions are left out) were translated into English by {esc(translator_name)}. The same model flagged the questions whose answer depends on Turkish wording; the {flagged} flagged questions are left out and the other {kept} kept. Each decision model answered the kept questions in English and is compared with its own Text tab run on the same {kept} questions.</p>
      <p class="note">Download: <a href="{rel(PATH, "results.json")}" download>results.json</a> (every number on this page, under <code>english_reading</code>), <a href="{rel(PATH, "answers.json")}" download>answers.json</a> (each English run's answers, under <code>english_runs</code>) and {download} (the translator, its prompts, the flags and each question's hash of its English text; no question text).</p>
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
      <p>The options follow the heading “{esc(data["options_heading"])}” instead of “{esc(TURKISH_OPTIONS_HEADING)}”, and the question and its options are the English translation. Prompt version {esc(data["prompt_version"])}; every English run used the translations with SHA-256 <code>{esc(data["translations_sha256"])}</code>.{renamed_text(site, data)}</p>
      <h3>Runs</h3>
      <p>One English run per model; five where the model's repeated Turkish runs on the Text tab changed answers. Here: {runs_text(site, data)}. The English runs are kept out of the leaderboard and its repeats.</p>
      <h3>The comparison</h3>
      <p>On the {kept} kept questions only: accuracy is the right answers over {kept} for the first English run and for the Text tab run (an invalid answer counts as not right), and the difference is English minus Turkish. The paired test is the exact McNemar test on the questions only one of the two runs got right, with p adjusted by Holm's method over the {family} model{"" if family == 1 else "s"} compared. Where a side has more than one run, its range is the lowest and highest accuracy over its runs, and its answers changed are the kept questions whose answer differs between them.</p>
      <h3>Why the translations are not published</h3>
      <p>The site never publishes question text, Turkish or English: the publisher owns the questions. {download} holds instead each reading question's ID, unit, whether it was kept, its flag reasons and the SHA-256 of its English text, with the translator and both prompts, so that a copy of these translations can be checked against it. Translating again with {script} need not give the same text word for word.</p>
    </section>
    </details>"""
    return {PATH: site.page(PATH, "English reading",
                            f"The Text tab's {kept} kept reading questions in English: accuracy of the decision models in "
                            "English against Turkish, with a paired test.", body)}
