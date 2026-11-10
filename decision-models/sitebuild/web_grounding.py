"""Web grounding (web-grounding/): Perplexity Decider v1.2 through its Decisions API with web search off and with web, from
results.json's web_grounding: the two hosted setups of the Text tab on the full bank, the 200-question pilot that came
first, the "Bilmiyorum" pairs, the English pair and PWS-Decisions. The full bank and the English questions have three
runs per mode: the cards, charts and main table show each arm's mean with the lowest and highest run, and the detailed
results each run with its paired counts; the ranking keeps each setup's first run. PWS-Decisions' rows are the mean of
our runs of the two setups in pws-decisions.json, as on its page, and its "I don't know" runs join the
non-hallucination chart and table when the file has them. Three result cards on the first screen (the three main
comparisons), four charts in the home page's format, each in its Measure section (accuracy, with the full bank by part
and the pilot folded; non-hallucination; latency; cost: each set of questions a small heading over its two setups, web
off grey and with web the accent colour), PWS-Decisions' charts of its decision models (pws_decisions.py), what the
search returned, the caveats, and the detailed tables. The home page's experiments line and the Perplexity family's
model pages link here. Every setup shown is a decision model (the build stops otherwise), so the page shows for the view
bar's all and decision groups (data-models) and the chat group shows a note instead; the Class row filters the setups'
rows and bars (data-class)."""

from __future__ import annotations

import math
import statistics
from typing import Any

from build_page import long_date
from sitebuild import names, pws_decisions
from sitebuild.site import (DECISION_ONLY, Site, chat_note, cost_per, cost_switch, cost_tick, cost_words, cost_value, esc,
                            family_icon, hbars, log_axis, more_link, pct, rel)

PATH = "web-grounding/"
TITLE = "Web grounding"
# The protocol's rule on the pilot: a full grounded run only for a gain of more than this many points of accuracy.
PILOT_RULE_POINTS = 5
# The day we first ran PWS-Decisions' public questions (grounding_test.py: the source checks' run), which no run id of
# ours records.
PWS_RUN_DATE = "2026-11-05"
SIDES = ("off", "on")
count = pws_decisions.count


def check(site: Site, data: dict[str, Any]) -> None:
    """Stop the build when web_grounding no longer fits the page: both Text tab runs are main runs with the section's
    names, and the English pair is those runs' English runs."""
    for arm in ("off", "on"):
        run = site.by_id.get(data["text_runs"][arm])
        if run is None or (run["provider"], run["model"], run["name"]) != (data["provider"], data["model"], data["names"][arm]):
            raise SystemExit(f"results.json web_grounding: run {data['text_runs'][arm]} is not the Text tab run of "
                             f"{data['names'][arm]}")
        if data["turkish"][arm]["run"] != data["text_runs"][arm]:
            raise SystemExit(f"results.json web_grounding: the Turkish {arm} run is not the Text tab run")
        english = next((model for model in (site.results.get("english_reading") or {}).get("models", [])
                        if model["run"] == data["english"][arm]["run"]), None)
        if english is None or english["turkish_run"] != data["text_runs"][arm]:
            raise SystemExit(f"results.json web_grounding: run {data['english'][arm]['run']} is not "
                             f"{data['names'][arm]}'s English run")


def ms(seconds: float) -> str:
    return f"{1000 * seconds:,.0f}"


def p_text(p: float) -> str:
    """An exact McNemar p as the page writes it: below 0.001 as a bound, else to three decimals."""
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def points(pair: dict[str, Any]) -> float:
    return 100 * (pair["on"]["accuracy"] - pair["off"]["accuracy"])


# The measures an arm shows: one run's values, or the mean of an arm's runs with the lowest and highest run.
KEYS = ("correct", "accuracy", "median_request_seconds", "p95_request_seconds", "cost_per_million_questions")


def single(item: dict[str, Any]) -> dict[str, Any]:
    """One run's arm as the page shows an arm: its values, one run, no range."""
    return {**item, "runs": 1, "ids": [item["run"]], "spread": {}}


def averaged(mean: dict[str, Any], runs: int, ids: list[int] | None) -> dict[str, Any]:
    """An arm's runs together (results.json's `mean`, or a PWS-Decisions setup): each measure's mean, with the lowest
    and highest run in spread."""
    return {"questions": mean["questions"], "runs": runs, "ids": ids, "averaged": True, **{key: mean[key]["mean"] for key in KEYS},
            "spread": {key: mean[key] for key in KEYS}}


def mean_pair(pair: dict[str, Any], group: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """A pair's two arms as the mean of their runs (`mean`), overall or for one group."""
    found = []
    for side in SIDES:
        mean = pair["mean"][side]
        found.append(averaged(mean if group is None else mean["groups"][group], len(mean["runs"]), mean["runs"]))
    return found[0], found[1]


def pws_arms(data: dict[str, Any], loaded: tuple[dict[str, Any], list[dict[str, Any]]] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """PWS-Decisions' rows: the mean of our runs of the section's two setups in pws-decisions.json (the same numbers as
    the PWS-Decisions page), each run's right answers from its runs."""
    if loaded is None:
        raise SystemExit("web-grounding/: the PWS-Decisions rows need pws-decisions.json")
    pws = loaded[0]
    found = {}
    for side, mode in (("off", None), ("on", "web_grounding")):
        setups = [setup for setup in pws["setups"] if (setup["provider"], setup["model"], setup["perplexity_mode"])
                  == (data["provider"], data["model"], mode)]
        if len(setups) != 1 or any(run["questions"] != pws["questions"] for run in setups[0]["runs"]):
            raise SystemExit(f"pws-decisions.json: needs one {data['model']} setup with mode {mode} over its {pws['questions']} questions")
        setup = setups[0]
        correct = [run["correct"] for run in setup["runs"]]
        mean = {"questions": pws["questions"], "correct": {"mean": statistics.mean(correct), "min": min(correct), "max": max(correct)},
                **{key: setup[key] for key in KEYS[1:]}}
        found[side] = averaged(mean, len(setup["runs"]), None)
    return found["off"], found["on"]


def arms(data: dict[str, Any], pws: tuple[dict[str, Any], dict[str, Any]]) -> list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]]:
    """The paired sets of the accuracy, latency and cost charts and the table: (label, off, on, paired test). The full
    bank and the English questions: the mean of each arm's runs (their paired counts are per run, in Each run); the
    pilot: one run per arm with its paired test; PWS-Decisions: the mean of our runs (pws_arms)."""
    turkish, pilot, english = data["turkish"], data["pilot"], data["english"]

    def pilot_groups() -> list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]]:
        return [(f"Pilot {group}, {pilot['off']['groups'][group]['questions']:,}",
                 single({**pilot["off"]["groups"][group], "run": pilot["off"]["run"]}),
                 single({**pilot["on"]["groups"][group], "run": pilot["on"]["run"]}), pilot["paired_groups"][group])
                for group in ("reading", "grammar")]

    return [
        (f"Turkish, full bank, {turkish['questions']:,}", *mean_pair(turkish), None),
        *((f"Turkish {group}, {turkish['off']['groups'][group]['questions']:,}", *mean_pair(turkish, group), None)
          for group in ("reading", "grammar")),
        (f"Turkish pilot, {pilot['questions']:,}", single(pilot["off"]), single(pilot["on"]), pilot["paired"]),
        *pilot_groups(),
        (f"English, {english['questions']:,} kept reading", *mean_pair(english), None),
        (f"PWS-Decisions, {pws[1]['questions']:,}", *pws, None),
    ]


def runs_label(label: str, item: dict[str, Any]) -> str:
    """A set's label, with how many runs its rows cover where they are means of an arm's runs ("mean of N runs", or
    "1 run" while an arm has only its first run)."""
    if not item.get("averaged"):
        return label
    return f"{label} · mean of {item['runs']} runs" if item["runs"] > 1 else f"{label} · 1 run"


def plural(number: int) -> str:
    return f"{number} run" if number == 1 else f"{number} runs"


def run_counts(data: dict[str, Any], pws: tuple[dict[str, Any], dict[str, Any]] | None = None) -> str:
    """How many runs per mode the full bank, the English questions (and PWS-Decisions) have: one count for all, else
    each set's."""
    sets = [("the full bank", len(data["turkish"]["mean"]["off"]["runs"])),
            ("the English questions", len(data["english"]["mean"]["off"]["runs"]))]
    if pws is not None:
        sets.append(("PWS-Decisions", pws[1]["runs"]))
    if len({number for _, number in sets}) == 1:
        names = [name for name, _ in sets]
        return f"{plural(sets[0][1])} per mode on {', '.join(names[:-1])} and {names[-1]}"
    return ("runs per mode: " + ", ".join(f"{plural(number)} on {name}" for name, number in sets[:-1])
            + f" and {plural(sets[-1][1])} on {sets[-1][0]}")


def cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def ranged(item: dict[str, Any], key: str, write: Any) -> str:
    """The lowest to the highest run of a mean, as text (empty for one run)."""
    spread = item["spread"].get(key)
    if spread is None or item["runs"] < 2:
        return ""
    low, high = write(spread["min"]), write(spread["max"])
    return f"{low} each run" if low == high else f"runs {low} to {high}"


def short_range(item: dict[str, Any], key: str, digits: int) -> str:
    """A mean's lowest to highest run as a chart writes it under the mean, a share without its first %: "88.5 to 89.4%"."""
    spread = item["spread"][key]
    low, high = pct(spread["min"], digits), pct(spread["max"], digits)
    return f"{low} each run" if low == high else f"{low.removesuffix('%')} to {high}"


def by_label(rows: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]]) -> dict[str, Any]:
    return {row[0].split(",")[0]: row for row in rows}


def main_arms(rows: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]]) -> list[Any]:
    """The three main comparisons: the Turkish full bank, the English questions and PWS-Decisions (the result cards, the
    first accuracy chart, latency and cost)."""
    found = by_label(rows)
    return [found["Turkish"], found["English"], found["PWS-Decisions"]]


def split_arms(rows: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]]) -> list[Any]:
    """The full bank's reading and grammar."""
    found = by_label(rows)
    return [found["Turkish reading"], found["Turkish grammar"]]


def pilot_arms(rows: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]]) -> list[Any]:
    """The 200-question pilot that came first, with its reading and grammar."""
    found = by_label(rows)
    return [found["Turkish pilot"], found["Pilot reading"], found["Pilot grammar"]]


def setups(site: Site, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The two setups, off and with web (on): their official name, tag and the two as plain text (name), links from this
    page, their family, and their size label, class key and data-class attribute for the Class row."""
    found = {}
    for side in SIDES:
        run = site.by_id[data["text_runs"][side]]
        found[side] = {"name": site.plain(run), "title": site.title(run), "tag": site.tag(run),
                       "href": rel(PATH, site.model_path(run)),
                       "family": site.families[data["text_runs"][side]], "label": site.label(run),
                       "class_key": site.model_class(run), "class_attribute": site.class_attribute(run)}
    return found


def pair_rows(named: dict[str, dict[str, Any]], group: str, values: dict[str, float], texts: dict[str, Any],
              titles: dict[str, str], markers: dict[str, float] | None = None, html: bool = False) -> list[dict[str, Any]]:
    """A set of questions' two rows under the set's heading: the setup with web off (grey), then with web (the accent
    colour, v3.css .web-off and .web-on), each with its family icon, official name and tag. A side's text as a list: one value
    per line (the mean, then the runs' range)."""
    def value(side: str) -> dict[str, Any]:
        text = texts[side]
        if isinstance(text, list):
            return {"texts": text} if len(text) > 1 else {"text": text[0]}
        return {"html" if html else "text": text}

    return [{"group": group, "label": named[side]["title"], "tag": named[side]["tag"], "href": named[side]["href"],
             "family": named[side]["family"]["name"],
             "class_key": named[side]["class_key"],
             "bars": [{"value": values[side], "kind": f"web-{side}"}], **value(side),
             "title": f"{named[side]['name']}, {group}: {titles[side]}", **({"marker": markers[side]} if markers else {})}
            for side in SIDES]


def legend_pair(named: dict[str, dict[str, Any]]) -> str:
    return (f'<span><i class="swatch swatch-web-off"></i>Web off: {names.name_html(named["off"]["title"], named["off"]["tag"])}</span> '
            f'<span><i class="swatch swatch-web-on"></i>With web: {names.name_html(named["on"]["title"], named["on"]["tag"])}</span>')


def card(key: str, title: str, sub: str, chart: str, named: dict[str, dict[str, Any]], legend: str = "",
         switch: str = "", wide: bool = False) -> str:
    """A chart card in its measure's section (the id the view bar's Measure row links to); wide gives the value column
    more room."""
    return (f'<section class="measure" id="{key}" aria-label="{esc(title)}">'
            f'<figure class="panel chart-card{" chart-wide" if wide else ""}" id="chart-{key}"><div class="chart-head"><h2>{esc(title)}</h2>'
            f'<p class="chart-sub">{sub}</p>{switch}</div>{chart}<p class="chart-legend">{legend_pair(named)} '
            f"<span>Each heading names the questions both setups answered.</span>{legend}</p></figure></section>")


def accuracy_chart(rows: list[Any], named: dict[str, dict[str, Any]], digits: int, pilot: dict[str, Any]) -> str:
    def chart(shown: list[Any]) -> str:
        write = lambda value: pct(value, digits)  # noqa: E731
        return hbars([row for label, off, on, _ in shown for row in pair_rows(
            named, f"{runs_label(label, off)} · {points({'off': off, 'on': on}):+.1f} pt", {"off": off["accuracy"], "on": on["accuracy"]},
            {side: [f"{write(item['accuracy'])} · {count(item['correct'])}", *([short_range(item, 'accuracy', digits)] if item["runs"] > 1 else [])]
             for side, item in (("off", off), ("on", on))},
            {side: (f"mean of {item['runs']} runs: {count(item['correct'])} of {item['questions']:,} right, "
                    f"{ranged(item, 'accuracy', write)}" if item["runs"] > 1 else f"{item['correct']:,} of {item['questions']:,} right")
             for side, item in (("off", off), ("on", on))})],
            head=("Accuracy · Right", "% · Right"))

    body = (chart(main_arms(rows)) + '<h3 class="chart-part">The Turkish full bank by part</h3>' + chart(split_arms(rows))
            + f'<details class="chart-more"><summary>The pilot, {pilot["questions"]:,} questions, run first, one run each</summary>'
            + chart(pilot_arms(rows)) + "</details>")
    return card("accuracy", "Accuracy", "Share of questions answered right, then the right answers; for a mean of several "
                "runs, the lowest to highest run under it; beside each set, the change with web in percentage points · "
                "higher is better", body, named, wide=True)


def dont_know_pairs(data: dict[str, Any], pws_idk: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    """The sets with the option: the Turkish full bank and pilot, the English questions, and PWS-Decisions' runs when
    pws-decisions.json has them (pws_idk: the mean of its runs, with the lowest and highest run)."""
    found = [(f"Turkish, full bank, {data['dont_know']['questions']:,}", data["dont_know"]),
             (f"Turkish pilot, {data['pilot_dont_know']['questions']:,}", data["pilot_dont_know"]),
             (f"English, {data['english_dont_know']['questions']:,} kept questions, I don't know", data["english_dont_know"])]
    return found + ([(f"PWS-Decisions, {pws_idk['questions']:,}, {pws_idk['option']}", pws_idk)] if pws_idk else [])


def pws_dont_know(loaded: tuple[dict[str, Any], list[dict[str, Any]]] | None) -> dict[str, Any] | None:
    """PWS-Decisions' "I don't know" runs (pws_decisions.dont_know_block) as a pair of the non-hallucination chart and
    table: per arm each count and rate's mean, with the runs' spread; None until both arms have their runs."""
    block = pws_decisions.dont_know_block(loaded[0]) if loaded else None
    if block is None:
        return None
    keys = ("right", "wrong", "dont_know", "errors", "accuracy", "answered", "wrong_of_answers", "non_hallucination")
    sides = {side: {"runs": len(block[side]["runs"]), **{key: None if block[side][key] is None else block[side][key]["mean"] for key in keys},
                    "spread": {key: block[side][key] for key in keys if block[side][key] is not None}} for side in SIDES}
    questions = {run["questions"] for side in SIDES for run in block[side]["runs"]}
    if len(questions) != 1:
        raise SystemExit("pws-decisions.json dont_know: the runs count different questions")
    return {"questions": questions.pop(), "option": block["option"], **sides}


def rate(value: float | None, digits: int) -> str:
    return "n/a" if value is None else pct(value, digits)


def non_hallucination_chart(data: dict[str, Any], pws_idk: dict[str, Any] | None, named: dict[str, dict[str, Any]],
                            digits: int) -> str:
    def group(label: str, pair: dict[str, Any]) -> str:
        off, on = pair["off"], pair["on"]
        right = (f"{count(off['right'])} right both ways" if off["right"] == on["right"]
                 else f"right {count(off['right'])} → {count(on['right'])}")
        runs = f" · mean of {off['runs']} runs" if off.get("runs", 1) > 1 else ""
        return f"{label}{runs}: {right}, wrong {count(off['wrong'])} → {count(on['wrong'])}"

    def title(side: dict[str, Any]) -> str:
        found = (f"the option {count(side['dont_know'])} of {count(side['dont_know'] + side['wrong'])} not right; answered "
                 f"{rate(side['answered'], digits)}; wrong of answers {rate(side['wrong_of_answers'], digits)}")
        if side.get("runs", 1) > 1:
            found += f"; mean of {side['runs']} runs, non-hallucination {ranged(side, 'non_hallucination', lambda value: pct(value, digits))}"
        return found

    rows = [row for label, pair in dont_know_pairs(data, pws_idk) for row in pair_rows(
        named, group(label, pair), {side: pair[side]["non_hallucination"] for side in SIDES},
        {side: f"{rate(pair[side]['non_hallucination'], digits)} | {count(pair[side]['dont_know'])} · "
               f"{rate(pair[side]['answered'], digits)} · {rate(pair[side]['wrong_of_answers'], digits)}" for side in SIDES},
        {side: title(pair[side]) for side in SIDES})]
    pws_note = (f"PWS-Decisions: “{pws_idk['option']}” as an extra choice, the mean of {pws_idk['off']['runs']} runs per mode"
                if pws_idk else "Not run on PWS-Decisions")
    return card("non-hallucination", "Non-hallucination",
                "“Bilmiyorum” in Turkish, “I don't know” in English, offered as an extra option: the bar is the option's "
                "share of the answers that were not right; beside it the times it was chosen, the answered share (right + "
                "wrong of the questions) and the wrong share of the answers · higher is better, read with the answered "
                f"share. {pws_note}",
                hbars(rows, head=("Rate | Option · Answered · Wrong", "Rate | Opt · Ans · Wrong")), named,
                " <span>A setup that always chose the option would reach 100% with no right answers.</span>", wide=True)


def latency_chart(rows: list[Any], named: dict[str, dict[str, Any]]) -> str:
    arms_shown = main_arms(rows)
    top = max(0.5, math.ceil(2 * max(side["p95_request_seconds"] for _, off, on, _ in arms_shown for side in (off, on))) / 2)

    def title(item: dict[str, Any]) -> str:
        found = f"median {ms(item['median_request_seconds'])} ms, 95th percentile {ms(item['p95_request_seconds'])} ms"
        if item["runs"] > 1:
            found += (f"; mean of {item['runs']} runs, medians {ranged(item, 'median_request_seconds', ms)} ms, 95th "
                      f"percentiles {ranged(item, 'p95_request_seconds', ms)} ms")
        return found

    chart_rows = [row for label, off, on, _ in arms_shown for row in pair_rows(
        named, runs_label(label, off), {"off": off["median_request_seconds"] / top, "on": on["median_request_seconds"] / top},
        {side: f"{ms(item['median_request_seconds'])} · {ms(item['p95_request_seconds'])} ms" for side, item in (("off", off), ("on", on))},
        {side: title(item) for side, item in (("off", off), ("on", on))},
        markers={"off": off["p95_request_seconds"] / top, "on": on["p95_request_seconds"] / top})]
    return card("latency", "Latency",
                "Median time per request (the bar) and 95th percentile by nearest rank (the line), one question per "
                "request, from our machine; for a mean of several runs, the mean of the runs' values · lower is better",
                hbars(chart_rows, top=1.0, tick=lambda value: f"{top * value:g}\u00a0s", head=("Median · p95", "Med · p95")),
                named, ' <span><i class="swatch swatch-marker"></i>95th percentile</span>')


def cost_chart(data: dict[str, Any], rows: list[Any], named: dict[str, dict[str, Any]], upper: dict[str, str]) -> str:
    arms_shown = main_arms(rows)
    per_k = lambda side: side["cost_per_million_questions"] / 1000  # noqa: E731
    place, axis = log_axis([per_k(side) for _, off, on, _ in arms_shown for side in (off, on)], lambda value: value)
    write = axis.pop("tick")
    prefix = {"off": "", "on": f"{upper['mark']} "}

    def title(side: str, item: dict[str, Any]) -> str:
        found = cost_words(per_k(item), prefix[side]) + ("; includes the search fee" if side == "on" else "; no search fee")
        if item["runs"] > 1:
            found += f"; mean of {item['runs']} runs"
        return found

    chart_rows = [row for label, off, on, _ in arms_shown for row in pair_rows(
        named, runs_label(label, off), {"off": place(per_k(off)), "on": place(per_k(on))},
        {side: cost_value(per_k(item), prefix[side]) + (esc(" incl. search") if side == "on" else "")
         for side, item in (("off", off), ("on", on))},
        {side: title(side, item) for side, item in (("off", off), ("on", on))}, html=True)]
    price = data["price"]
    return card("cost", "Cost",
                f"Estimated dollars {cost_per()}, log scale: input tokens at ${price['input_per_million']:g} per 1M, plus "
                f"${price['per_search']:g} per request with web (incl. search); for a mean of several runs, the mean of "
                "the runs' costs · lower is better",
                hbars(chart_rows, head=("Cost", "Cost"), tick=lambda offset: cost_tick(write(offset)), **axis), named,
                f" <span>{esc(upper['mark'])} {esc(upper['note'])}</span>", cost_switch(), wide=True)


def result_cards(rows: list[Any], digits: int, upper: dict[str, str]) -> str:
    """The page's first screen: the three main comparisons, each its accuracy off and with web (the mean of its runs),
    the change in points, the runs' range, and the cost off and with web (with web an upper-bound estimate, ≤)."""
    write = lambda value: pct(value, digits)  # noqa: E731
    turkish, english, pws = (row[1:3] for row in main_arms(rows))
    names = [f"Turkish, {turkish[0]['questions']:,} questions", f"English reading, {english[0]['questions']:,}",
             f"PWS-Decisions, {pws[0]['questions']:,}"]
    cards = []
    for name, (off, on) in zip(names, (turkish, english, pws)):
        cost = (f"{cost_value(off['cost_per_million_questions'] / 1000)} vs "
                f"{cost_value(on['cost_per_million_questions'] / 1000, upper['mark'] + ' ')} {cost_per()}")
        runs = (f'<p class="result-cost">Mean of {off["runs"]} runs; {esc(ranged(off, "accuracy", write))} off, '
                f'{esc(ranged(on, "accuracy", write))} with web</p>' if off["runs"] > 1 else '<p class="result-cost">1 run per mode so far</p>')
        cards.append(f'<div class="result-card"><h2>{esc(name)}</h2><p class="result-main">{esc(write(off["accuracy"]))} → '
                     f'{esc(write(on["accuracy"]))} <span class="result-gain">({points({"off": off, "on": on}):+.1f} '
                     f'points)</span></p>{runs}<p class="result-cost">{cost}</p></div>')
    return (f'<div class="result-cards">{"".join(cards)}</div><p class="note">Accuracy with web off → with web, the mean '
            f"of the runs; cost web off vs with web. {esc(upper['mark'])} Upper-bound estimate: the search fee counted for "
            f'every request with web. {cost_switch()}</p>')


def setup_cell(named: dict[str, dict[str, Any]], side: str, questions: str, run: str) -> str:
    """A table row's setup: its family icon and official name, linked to its page, its tag, with its questions and run
    under it."""
    item = named[side]
    return (f'<td class="model">{family_icon(item["family"]["name"])}<a class="model-name" href="{item["href"]}">'
            f'{esc(item["title"])}</a>{names.tag_html(item["tag"])} {item["label"]}<span class="small">{esc(questions)} · {esc(run)}</span></td>')


HEADS = (("Right", "of the questions"), ("Accuracy", "higher is better"), ("Median per request", "ms; lower is better"),
         ("95th percentile", "ms; lower is better"), ("Cost", "lower is better"), ("Right only with this setup", "exact McNemar p"))


def num_head(heads: tuple[tuple[str, str], ...] | list[tuple[str, str]]) -> str:
    return "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">'
                   f'{(cost_per() + "; ") if name == "Cost" else ""}{esc(note)}</span></th>' for name, note in heads)


def small(text: str) -> str:
    return f'<span class="small">{esc(text)}</span>' if text else ""


def cost_range(item: dict[str, Any], prefix: str) -> str:
    """A mean cost's lowest to highest run under it, in both cost units (cost_value); nothing for one run."""
    spread = item["spread"].get("cost_per_million_questions")
    if spread is None or item["runs"] < 2:
        return ""
    low, high = (cost_value(spread[key] / 1000, prefix) for key in ("min", "max"))
    return f'<span class="small">{low} each run</span>' if low == high else f'<span class="small">runs {low} to {high}</span>'


def arm_rows(named: dict[str, dict[str, Any]], digits: int, upper: dict[str, str], label: str, off: dict[str, Any],
             on: dict[str, Any], test: dict[str, Any] | None) -> str:
    """A set's two table rows (off, then with web): right answers, accuracy, request times and cost, each a mean of
    several runs with the lowest and highest run under it, and the right answers only one setup had with the pair's
    exact McNemar p (a pair of runs only)."""
    write = lambda value: pct(value, digits)  # noqa: E731
    out = []
    for side, item in (("off", off), ("on", on)):
        if item["runs"] > 1:
            run = f"mean of {item['runs']} runs" + (f" ({', '.join(str(run) for run in item['ids'])})" if item["ids"] else "")
        else:
            run = f"run {item['ids'][0]}"
        prefix = f"{upper['mark']} " if side == "on" else ""
        if test is not None:
            only = f"{test[f'{side}_only']:,} ({p_text(test['p'])})"
        else:
            only = "per run, in Each run" if item["ids"] else "no per-question results"
        cells = [esc(f"{count(item['correct'])} of {item['questions']:,}") + small(ranged(item, "correct", count)),
                 esc(write(item["accuracy"])) + small(ranged(item, "accuracy", write)),
                 esc(ms(item["median_request_seconds"])) + small(ranged(item, "median_request_seconds", ms)),
                 esc(ms(item["p95_request_seconds"])) + small(ranged(item, "p95_request_seconds", ms)),
                 cost_value(item["cost_per_million_questions"] / 1000, prefix) + cost_range(item, prefix)
                 + small("incl. search" if side == "on" else "no search fee"), esc(only)]
        out.append(f"<tr{named[side]['class_attribute']}>{setup_cell(named, side, label, run)}"
                   + "".join(f'<td class="num" data-label="{esc(name)}">{text}</td>' for (name, _), text in zip(HEADS, cells))
                   + "</tr>")
    return "".join(out)


def table(rows: list[Any], pws_idk: dict[str, Any] | None, data: dict[str, Any], named: dict[str, dict[str, Any]],
          digits: int, upper: dict[str, str]) -> str:
    idk_heads = (("Right · wrong · the option", "counts"), ("Answered", "(right + wrong) / questions"),
                 ("Wrong of answers", "wrong / (right + wrong)"),
                 ("Non-hallucination", "the option / (the option + wrong); higher is better"))
    idk_head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>' for name, note in idk_heads)
    write = lambda value: pct(value, digits)  # noqa: E731

    def idk_rows(label: str, pair: dict[str, Any]) -> str:
        out = []
        for side in SIDES:
            item = pair[side]
            several = item.get("runs", 1) > 1
            cells = [esc(" · ".join(count(item[key]) for key in ("right", "wrong", "dont_know")))] + [
                esc(rate(item[key], digits)) + (small(ranged(item, key, write)) if several and item[key] is not None else "")
                for key in ("answered", "wrong_of_answers", "non_hallucination")]
            run = f"mean of {item['runs']} runs" if several else f"run {item['run']}"
            out.append(f"<tr{named[side]['class_attribute']}>{setup_cell(named, side, label, run)}"
                       + "".join(f'<td class="num" data-label="{esc(name)}">{text}</td>' for (name, _), text in zip(idk_heads, cells))
                       + "</tr>")
        return "".join(out)

    return (f'{cost_switch()}<div class="table-wrap"><table class="board list stack wrap-headers"><thead><tr>'
            f'<th scope="col">Setup</th>{num_head(HEADS)}</tr></thead>'
            f'<tbody>{"".join(arm_rows(named, digits, upper, *row) for row in rows)}</tbody></table></div>'
            '<p class="note">Two rows per set of questions: off, then with web; under each name, its questions and runs. The '
            "full bank, the English questions and PWS-Decisions: the mean of the runs, with the lowest and highest run "
            "under each value; each run, with its paired counts, is in Each run below. Times: per request from our "
            "machine; the 95th percentile by nearest rank. Cost: each run's input tokens at the price below, plus the fee "
            f"per search for every request with web ({esc(upper['mark'])} {esc(upper['note'])}) Right only with this "
            "setup: the questions it got right and the other setup did not, with the exact McNemar p of the pair.</p>"
            '<h3 class="board-group">With “Bilmiyorum” (Turkish) or “I don\'t know” (English) as an extra option</h3>'
            f'<div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Setup</th>{idk_head}</tr>'
            f'</thead><tbody>{"".join(idk_rows(label, pair) for label, pair in dont_know_pairs(data, pws_idk))}</tbody></table></div>')


def run_sets(data: dict[str, Any]) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """The full bank's and the English pair's pairs of runs by repeat number: (set, its questions, the pairs: the first
    runs as repeat 1, then the repeats)."""
    found = []
    for key, name in (("turkish", "Turkish, full bank"), ("english", "English, kept reading")):
        pair = data[key]
        entries = [{"repeat": 1, **{part: pair[part] for part in ("off", "on", "paired", "search")}}, *pair.get("repeats", [])]
        found.append((name, f"{pair['questions']:,}", entries))
    return found


def each_run(data: dict[str, Any], named: dict[str, dict[str, Any]], digits: int, upper: dict[str, str]) -> str:
    """Each run of the full bank and the English questions: its results with the pair's right-only counts and exact
    McNemar p, then per repeat number the paired counts of off against with web on the same questions."""
    rows, paired_rows = [], []
    pair_heads = (("Both right", "questions"), ("Right only off", "questions"), ("Right only with web", "questions"),
                  ("Both wrong", "questions"), ("Errors", "off · with web; scored wrong"),
                  ("Missing", "off · with web; not answered"), ("Exact McNemar p", "right only off against only with web"))
    for name, questions, entries in run_sets(data):
        total = len(entries)
        for entry in entries:
            label = f"{name}, {questions}, run {entry['repeat']} of {total}"
            rows.append(arm_rows(named, digits, upper, label, single(entry["off"]), single(entry["on"]), entry["paired"]))
            test = entry["paired"]
            cells = [f"{test['both_right']:,}", f"{test['off_only']:,}", f"{test['on_only']:,}", f"{test['both_wrong']:,}",
                     f"{test['errors']['off']:,} · {test['errors']['on']:,}", f"{test['missing']['off']:,} · {test['missing']['on']:,}",
                     p_text(test["p"])]
            paired_rows.append(f'<tr><td class="model">{esc(name)}, run {entry["repeat"]} of {total}<span class="small">runs '
                               f'{entry["off"]["run"]} and {entry["on"]["run"]}; {test["questions"]:,} questions</span></td>'
                               + "".join(f'<td class="num" data-label="{esc(head)}">{esc(text)}</td>'
                                         for (head, _), text in zip(pair_heads, cells)) + "</tr>")
    pair_head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>' for name, note in pair_heads)
    return (f'<section class="card" id="each-run"><h2>Each run</h2><p class="note">'
            f"{cap(run_counts(data))}: each mode's first run (the ranking's run), then its repeats with the same questions in "
            "the same order, answer key, runner and settings. Each run of one repeat number is paired with the other "
            "mode's run of the same number, on the first runs' questions.</p>"
            f'{cost_switch()}<div class="table-wrap"><table class="board list stack wrap-headers"><thead><tr>'
            f'<th scope="col">Setup</th>{num_head(HEADS)}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            '<h3 class="board-group">Paired counts, off against with web, per run</h3>'
            f'<div class="table-wrap"><table class="board list stack wrap-headers"><thead><tr><th scope="col">Runs</th>{pair_head}'
            f'</tr></thead><tbody>{"".join(paired_rows)}</tbody></table></div></section>')


def top_sites(search: dict[str, Any]) -> str:
    """The most returned sites of a grounded run, each with its pages of the run's total."""
    return ("<ol class=\"sites\">" + "".join(f"<li>{esc(name)}: {pages:,} of {search['pages']:,} pages</li>"
                                             for name, pages in search["top_domains"]) + "</ol>")


def returned(search: dict[str, Any], questions: int) -> str:
    per = search["pages_per_question"]
    span = f"{per['min']}" if per["min"] == per["max"] else f"{per['min']} to {per['max']}"
    return (f"{search['pages']:,} pages for {questions:,} questions ({span} per question), from {search['sites']:,} sites. "
            "The most returned:")


def finding(pair: dict[str, Any], words: int) -> str:
    """A Turkish grounded run's source checks, with the right answers off and with web among their questions."""
    search, test = pair["search"], pair["paired"]
    shared, publisher, book = search["shared_words"], search["publisher"], search["source_book"]
    both = lambda item: item["right_off"] - item["off_only"]  # noqa: E731
    return (f"{shared['questions']:,} questions had a literal match of {words}+ words: {shared['right_off']:,} right off, "
            f"{shared['right_on']:,} with web; {shared['on_only']:,} of the {test['on_only']:,} gains and "
            f"{shared['off_only']:,} of the {test['off_only']:,} losses. {publisher['questions']:,} got a page from Paraf, "
            f"the publisher of the bank's source book ({both(publisher):,} right both ways). {book['questions']:,} got the "
            f"source book itself, found by its title ({both(book):,} right both ways).")


def spread_text(values: list[int]) -> str:
    """Counts over runs: one number when all are equal, else the lowest to the highest."""
    return f"{min(values):,}" if min(values) == max(values) else f"{min(values):,} to {max(values):,}"


def run_checks(data: dict[str, Any]) -> str:
    """Each grounded run's source checks (the full bank and the English questions): pages, sites, and the questions of
    each check; N/A for a run that returned no page. Then each run's most returned sites."""
    words = data["rules"]["shared_words"]
    heads = (("Pages", "returned, of up to 5 per question"), ("Sites", "host names"),
             (f"{words}+ word match", "questions"), ("A Paraf page", "questions"), ("The source book", "questions"))
    rows, lists = [], []
    for name, questions, entries in run_sets(data):
        for entry in entries:
            search = entry["search"]
            label = f"{name}, run {entry['repeat']} of {len(entries)}"
            if search is None:
                cells = ["N/A"] * len(heads)
            else:
                cells = [f"{search['pages']:,}", f"{search['sites']:,}", f"{search['shared_words']['questions']:,}",
                         f"{search['publisher']['questions']:,}", f"{search['source_book']['questions']:,}"]
                lists.append(f"<h4>{esc(label)} (run {entry['on']['run']})</h4>{top_sites(search)}")
            rows.append(f'<tr><td class="model">{esc(label)}<span class="small">run {entry["on"]["run"]}, {questions} questions'
                        "</span></td>" + "".join(f'<td class="num" data-label="{esc(head)}">{esc(text)}</td>'
                                                 for (head, _), text in zip(heads, cells)) + "</tr>")
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>' for name, note in heads)
    return (f'<h3>Each grounded run</h3><div class="table-wrap"><table class="board list stack wrap-headers"><thead><tr>'
            f'<th scope="col">Run with web</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            "<p class=\"note\">N/A: the run returned no page, so it has no source checks. A Paraf page: questions with a "
            "page from the publisher of the bank's source book. The source book: questions with a page of the book itself, "
            "found by its title.</p>"
            f'<details class="chart-more"><summary>The 10 most returned sites, each run</summary>{"".join(lists)}</details>')


def sources(data: dict[str, Any]) -> str:
    """What the grounded runs' searches returned: pages and sites, then the literal-match and source checks of the first
    runs, and each grounded run's checks."""
    turkish, pilot, english, pws = data["turkish"], data["pilot"], data["english"], data["pws"]
    words = data["rules"]["shared_words"]
    english_shared, gains = english["search"]["shared_words"], english["paired"]["on_only"]
    if english_shared["on_only"] == 0:
        english_gains = (f"None of the {gains:,} English gains had the defined {words}+ word overlap; this does not show "
                         "that the answer, or its semantic equivalent, was absent from the returned pages.")
    else:
        english_gains = (f"{english_shared['on_only']:,} of the {gains:,} English gains had the defined {words}+ word "
                         "overlap; this does not show where a gain came from.")
    full = [entry["search"] for entry in run_sets(data)[0][2] if entry["search"] is not None]
    matched = spread_text([search["shared_words"]["questions"] for search in full])
    book = spread_text([search["source_book"]["questions"] for search in full])
    return f"""<section class="card" id="sources">
      <h2>What the search returned</h2>
      <p><strong>In short.</strong> On the full bank, {matched} questions per grounded run had {words}+ consecutive question words in a returned title or snippet, and {book} got the source book itself. A word match alone does not prove that the answer was found.</p>
      <p>Unit: returned pages, up to 5 per question; each site's count is out of the run's total pages.</p>
      <p><strong>The {words}+ word check.</strong> A literal-match check: runs of {words} or more consecutive words of the question (its body and each option's text, without the option letters) in a returned page's title or snippet. It shows only such matches. Our translations are unpublished, but that does not prove the answer, or equivalent information, cannot be found on the web.</p>
      <h3>Turkish, full bank, first run (run {turkish['on']['run']})</h3>
      <p>{returned(turkish['search'], turkish['questions'])}</p>{top_sites(turkish['search'])}
      <p>{finding(turkish, words)}</p>
      <h3>Turkish pilot (run {pilot['on']['run']})</h3>
      <p>{returned(pilot['search'], pilot['questions'])}</p>{top_sites(pilot['search'])}
      <p>{finding(pilot, words)}</p>
      <h3>English, first run (run {english['on']['run']})</h3>
      <p>{returned(english['search'], english['questions'])}</p>{top_sites(english['search'])}
      <p>{english_shared['questions']:,} of the {english['questions']:,} English questions had a literal match of {words}+ words: {english_shared['right_off']:,} right off, {english_shared['right_on']:,} with web. {english_gains}</p>
      {run_checks(data)}
      <h3>PWS-Decisions, our first grounded run ({esc(long_date(PWS_RUN_DATE))})</h3>
      <p>{returned(pws['on']['search'], pws['on']['questions'])}</p>{top_sites(pws['on']['search'])}
      <p>{pws['on']['search']['shared_words']:,} of the {pws['on']['questions']:,} questions had a literal match of {words}+ words (its state with its instructions, or a choice's description). This run came before the three runs whose mean the charts show; their responses were not kept for this check.</p>
      <p class="note">Sites: the page addresses' host names without “www.”. Words: runs of letters and digits, case-folded. Only these counts are published: the pages' addresses, titles and snippets stay with us.</p>
    </section>"""


def caveats(data: dict[str, Any], pws_rows: tuple[dict[str, Any], dict[str, Any]], pws_dates: list[str],
            upper: dict[str, str]) -> str:
    price, pws, reported, pilot = data["price"], data["pws"], data["pws"]["reported"], data["pilot"]
    off, on = pws_rows
    gain = points(pilot)
    when = long_date(pws_dates[0]) if len(set(pws_dates)) == 1 else f"{long_date(pws_dates[0])} to {long_date(pws_dates[-1])}"
    return f"""<section class="card" id="caveats">
      <h2>Read it with these caveats</h2>
      <ul>
        <li><strong>Grounded searches send the questions to Perplexity's search.</strong> Each question with web went out as a web search.</li>
        <li><strong>The pilot came first.</strong> Our protocol's first step was {pilot['questions']:,} questions ({pilot['off']['groups']['reading']['questions']:,} reading, {pilot['off']['groups']['grammar']['questions']:,} grammar; runs {pilot['off']['run']} and {pilot['on']['run']}). Its rule: a full grounded run only for a gain of more than {PILOT_RULE_POINTS} points. The pilot gained {gain:+.1f} points, short of the rule; the full-bank grounded run was made afterwards so that the setup could be ranked.</li>
        <li><strong>Costs with web are an upper bound.</strong> {esc(upper['mark'])} {esc(upper['note'])} Price: ${price['input_per_million']:g} per 1M input tokens plus ${price['per_search']:g} per completed search (<a href="{esc(price['source'])}">pricing</a>, read {esc(long_date(price['date']))}). Search evidence counts as input tokens.</li>
        <li><strong>{cap(run_counts(data))}.</strong> The cards, charts and first table show the mean of each mode's runs, with the lowest and highest run where there are several; Each run gives every run and its paired test. The ranking keeps each setup's first run. The pilot and the “Bilmiyorum” and “I don't know” pairs on our questions: one run each.</li>
        <li><strong>Perplexity's own figures.</strong> Perplexity reported {reported['on_correct']} of {pws['on']['questions']} PWS-Decisions questions right with grounding (its run of {esc(long_date(reported['published']))}); the {reported['off_correct']}% without is the benchmark authors' (Parallel's) leaderboard figure, which Perplexity's own run matched. Its grounded requests took {ms(reported['on_median_request_seconds'])} ms at the median and {ms(reported['on_p95_request_seconds'])} ms at the 95th percentile, from Perplexity's client (<a href="{esc(reported['source'])}">{esc(reported['title'])}</a>, {esc(long_date(reported['published']))}). Ours are from our machine, the mean of {on['runs']} runs per mode on {esc(when)}: {pct(off['accuracy'], 1)} off, {pct(on['accuracy'], 1)} with web; {ms(on['median_request_seconds'])} and {ms(on['p95_request_seconds'])} ms at the median and 95th percentile with web.</li>
        <li><strong>PWS-Decisions is gated.</strong> {esc(pws['name'])} (version {esc(pws['version'])}) is Parallel's dataset, for evaluation only; we publish aggregates only.</li>
      </ul>
    </section>"""


def method(data: dict[str, Any], named: dict[str, dict[str, Any]], pws_rows: tuple[dict[str, Any], dict[str, Any]], pws_dates: list[str]) -> str:
    turkish, pilot, english = data["turkish"], data["pilot"], data["english"]
    reading = data["reading_units"]

    def repeats(pair: dict[str, Any]) -> str:
        found = pair.get("repeats", [])
        if not found:
            return ""
        each = "; ".join(f"repeat {entry['repeat']}: runs {entry['off']['run']} and {entry['on']['run']}" for entry in found)
        return f" Repeats with the same questions in the same order: {each}."

    return f"""<section class="card method-notes" id="method">
      <h2>Our method</h2>
      <p>Model <code>{esc(data['model'])}</code> through Perplexity's Decisions API, one question per request, the Text tab's System One prompts. Each pair of runs differs only in the request's mode: off, or <code>web_grounding</code>, which runs a web search per question and adds its results as evidence. Runs from {esc(long_date(data['dates'][0]))} to {esc(long_date(data['dates'][-1]))}. {cap(run_counts(data))}: each mode's first run and its repeats with the same questions in the same order, answer key, runner and settings; the ranking keeps each setup's first run, and the repeats enter only this page.</p>
      <ul>
        <li>Turkish, full bank: {turkish['questions']:,} questions = {turkish['off']['groups']['reading']['questions']:,} reading + {turkish['off']['groups']['grammar']['questions']:,} grammar (first runs {turkish['off']['run']} and {turkish['on']['run']}, the Text tab rows {esc(named['off']['name'])} and {esc(named['on']['name'])}).{repeats(turkish)} Reading: units {", ".join(str(unit) for unit in reading[:-1])} and {reading[-1]}.</li>
        <li>Turkish pilot: {pilot['questions']:,} = {pilot['off']['groups']['reading']['questions']:,} reading + {pilot['off']['groups']['grammar']['questions']:,} grammar, the runner's sample with seed {data['sample']['seed']} (runs {pilot['off']['run']} and {pilot['on']['run']}).</li>
        <li>“Bilmiyorum” as an extra option, as on the Hallucination tab: the full bank ({data['dont_know']['questions']:,} questions, runs {data['dont_know']['off']['run']} and {data['dont_know']['on']['run']}) and the pilot ({data['pilot_dont_know']['questions']:,}, runs {data['pilot_dont_know']['off']['run']} and {data['pilot_dont_know']['on']['run']}). “I don't know” as an extra option in English, as on English and Turkish: the {data['english_dont_know']['questions']:,} kept questions (runs {data['english_dont_know']['off']['run']} and {data['english_dont_know']['on']['run']}).</li>
        <li>English: the {english['questions']:,} kept reading questions of the English pages in our translations (first runs {english['off']['run']} and {english['on']['run']}).{repeats(english)}</li>
        <li>PWS-Decisions: its {pws_rows[1]['questions']} public English questions with the benchmark's own request, {pws_rows[1]['runs']} runs per mode by us on {esc(long_date(pws_dates[0]))}, as on <a href="{rel(PATH, pws_decisions.PATH)}">PWS-Decisions</a>; the source checks come from our first grounded run of {esc(long_date(PWS_RUN_DATE))}.</li>
      </ul>
      <p>Accuracy: right answers over the questions asked. Time: each request's wall-clock time on our machine; the median and the 95th percentile by nearest rank. Cost per 1M questions: the run's input tokens at ${data['price']['input_per_million']:g} per 1M plus ${data['price']['per_search']:g} per request with web, over its questions. A mean of several runs: the mean of the runs' values, with the lowest and highest run. The paired test: the exact McNemar test on the questions one arm got right and the other did not, per pair of runs.</p>
      <p class="note">Download: <a href="{rel(PATH, "results.json")}" download>results.json</a> (every number on this page but PWS-Decisions' means, under <code>web_grounding</code>), <a href="{rel(PATH, "answers.json")}" download>answers.json</a> (the pilots and the repeats under <code>web_grounding_runs</code>, the other runs in their own lists), <a href="{rel(PATH, "web-grounding.json")}" download>web-grounding.json</a> (tokens by group, the source checks' question ids and the first PWS-Decisions run's aggregates) and <a href="{rel(PATH, "pws-decisions.json")}" download>pws-decisions.json</a> (PWS-Decisions' runs). <code>reproduce.py</code> recomputes results.json.</p>
    </section>"""


def pws_section(site: Site, loaded: tuple[dict[str, Any], list[dict[str, Any]]] | None) -> str:
    """PWS-Decisions' charts of its decision-model setups (pws_decisions.py; the chat rows stay on its page), with its
    framing and provenance; nothing without pws-decisions.json."""
    if loaded is None:
        return ""
    pws, items = loaded
    decisions = [item for item in items if not pws_decisions.chat(item["setup"])]
    return f"""<section class="card" id="pws" {DECISION_ONLY}>
      <h2>PWS-Decisions: the decision models, with and without web</h2>
      {pws_decisions.framing(pws)}
      <p>Each bar is the mean of our {pws['runs_per_setup']} runs per setup, decision models only; the PWS-Decisions rows of the charts above are the same means for Perplexity's two setups. Chat models, with and without their own web search, and every number: <a href="{rel(PATH, pws_decisions.PATH)}">PWS-Decisions</a>.</p>
      {pws_decisions.provenance(pws)}
    </section>
    <section class="charts" aria-label="PWS-Decisions charts" {DECISION_ONLY}>{pws_decisions.charts(site, pws, decisions, PATH, "chart-pws-")}</section>"""


def build(site: Site) -> dict[str, str]:
    data = site.results.get("web_grounding")
    if data is None:
        return {}
    check(site, data)
    if not all(site.decision(site.by_id[run]) for run in data["text_runs"].values()):
        raise SystemExit("results.json web_grounding: a setup that is not a decision model, which the page shows for the "
                         "view bar's all and decision groups only")
    digits = site.config["percent_digits"]
    upper = site.config["first_cost_marks"]["upper"]
    named = setups(site, data)
    loaded = pws_decisions.load(site)
    pws_rows = pws_arms(data, loaded)
    pws_idk = pws_dont_know(loaded)
    pws_dates = sorted(loaded[0]["dates"])
    rows = arms(data, pws_rows)
    days = sorted(set(data["dates"]) | {PWS_RUN_DATE} | set(pws_dates))
    when = long_date(days[0]) if len(days) == 1 else f"{long_date(days[0])} to {long_date(days[-1])}"
    site.note(PATH, TITLE, f'<p {DECISION_ONLY}><a href="{named["off"]["href"]}">{esc(named["off"]["title"])}</a>{names.tag_html(named["off"]["tag"])} and '
              f'<a href="{named["on"]["href"]}">{esc(named["on"]["title"])}</a>{names.tag_html(named["on"]["tag"])}, Perplexity\'s Decisions API without and '
              f"with a web search per question; {run_counts(data, pws_rows)}, the ranking keeping each setup's first run; "
              f"run on {esc(when)}.</p>")
    body = f"""    <section class="card">
      <p class="eyebrow">Experiment</p>
      <h1>Web grounding: {esc(named["off"]["title"])} off and with web</h1>
      {chat_note("Chat models: this page compares decision-model setups, so it shows under All models and Decision models. PWS-Decisions with chat models: its own page.")}
      <div {DECISION_ONLY}>
      <p>Perplexity's Decisions API without and with a web search per question.</p>
      {more_link(PATH)}
      {result_cards(rows, digits, upper)}
      <nav class="face-nav" aria-label="On this page"><a href="#accuracy">Accuracy</a><a href="#non-hallucination">Non-hallucination</a><a href="#latency">Latency</a><a href="#cost">Cost</a><a href="#pws">PWS-Decisions, decision models</a><a href="#sources">What the search returned</a><a href="#caveats">Caveats</a><a href="#info">Detailed results</a></nav></div>
    </section>
    <section class="charts" aria-label="Charts" {DECISION_ONLY}>{accuracy_chart(rows, named, digits, data["pilot"])}{non_hallucination_chart(data, pws_idk, named, digits)}{latency_chart(rows, named)}{cost_chart(data, rows, named, upper)}</section>
    {pws_section(site, loaded)}
    <div {DECISION_ONLY}>
    {sources(data)}
    {caveats(data, pws_rows, pws_dates, upper)}
    <details class="info info-details" id="info">
      <summary class="info-summary"><span class="info-title">Detailed results</span> <span class="info-sub">The tables, with the pilot, each run with its paired counts, the unmatched answers and our method</span></summary>
    <section class="card" id="results">
      <h2>Every number</h2>
      {table(rows, pws_idk, data, named, digits, upper)}
    </section>
    {each_run(data, named, digits, upper)}
    {method(data, named, pws_rows, pws_dates)}
    </details>
    </div>"""
    return {PATH: site.page(PATH, TITLE, f"{named['off']['name']} and {named['on']['name']}: accuracy, non-hallucination, "
                            "time per request and cost on our Turkish and English questions and on PWS-Decisions.", body)}
