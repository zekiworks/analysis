"""Web grounding (web-grounding/): Perplexity Decider v1.2 through its Decisions API with web search off and with web, from
results.json's web_grounding: the two hosted setups of the Text tab on the full bank, the 200-question pilot that came
first, the "Bilmiyorum" pairs, the English pair and PWS-Decisions. Three result cards on the first screen (the three main
comparisons), four charts in the home page's format, each in its Measure section (accuracy, with the full bank by part
and the pilot folded; non-hallucination; latency; cost: each set of questions a small heading over its two setups, web
off grey and with web the accent colour), PWS-Decisions' charts of every setup (pws_decisions.py, from
pws-decisions.json), what the search returned, the caveats, and the detailed tables. The home page's experiments line and
the Perplexity family's model pages link here. Both compared setups are decision models (the build stops otherwise), so
the comparison shows for the view bar's all and decision groups (data-models) and the chat group shows a note instead;
PWS-Decisions, with chat models among its setups, shows in every group."""

from __future__ import annotations

import math
from typing import Any

from build_page import long_date
from sitebuild import pws_decisions
from sitebuild.site import (DECISION_ONLY, Site, chat_note, cost_per, cost_switch, cost_tick, cost_words, cost_value, esc,
                            family_icon, hbars, log_axis, pct, rel)

PATH = "web-grounding/"
TITLE = "Web grounding"
# The protocol's rule on the pilot: a full grounded run only for a gain of more than this many points of accuracy.
PILOT_RULE_POINTS = 5
# The day we ran PWS-Decisions' public questions (grounding_test.py), which no run id of ours records.
PWS_RUN_DATE = "2026-11-05"
SIDES = ("off", "on")


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


def arms(data: dict[str, Any]) -> list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]]:
    """The paired sets of the accuracy, latency and cost charts and the table: (label, off, on, paired test)."""
    turkish, pilot, english, pws = data["turkish"], data["pilot"], data["english"], data["pws"]

    def groups(pair: dict[str, Any], name: str) -> list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]]:
        return [(f"{name} {group}, {pair['off']['groups'][group]['questions']:,}",
                 {**pair["off"]["groups"][group], "run": pair["off"]["run"]},
                 {**pair["on"]["groups"][group], "run": pair["on"]["run"]}, pair["paired_groups"][group])
                for group in ("reading", "grammar")]

    return [
        (f"Turkish, full bank, {turkish['questions']:,}", turkish["off"], turkish["on"], turkish["paired"]),
        *groups(turkish, "Turkish"),
        (f"Turkish pilot, {pilot['questions']:,}", pilot["off"], pilot["on"], pilot["paired"]),
        *groups(pilot, "Pilot"),
        (f"English, {english['questions']:,} kept reading", english["off"], english["on"], english["paired"]),
        (f"PWS-Decisions, {pws['on']['questions']:,}", pws["off"], pws["on"], pws["paired"]),
    ]


def by_label(data: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]]:
    return {row[0].split(",")[0]: row for row in arms(data)}


def main_arms(data: dict[str, Any]) -> list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]]:
    """The three main comparisons: the Turkish full bank, the English questions and PWS-Decisions (the result cards, the
    first accuracy chart, latency and cost)."""
    found = by_label(data)
    return [found["Turkish"], found["English"], found["PWS-Decisions"]]


def split_arms(data: dict[str, Any]) -> list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]]:
    """The full bank's reading and grammar."""
    found = by_label(data)
    return [found["Turkish reading"], found["Turkish grammar"]]


def pilot_arms(data: dict[str, Any]) -> list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]]:
    """The 200-question pilot that came first, with its reading and grammar."""
    found = by_label(data)
    return [found["Turkish pilot"], found["Pilot reading"], found["Pilot grammar"]]


def setups(site: Site, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The two setups, off and with web (on): their full names, links from this page and their family."""
    return {side: {"name": data["names"][side], "href": rel(PATH, site.model_path(site.by_id[data["text_runs"][side]])),
                   "family": site.families[data["text_runs"][side]]} for side in SIDES}


def pair_rows(named: dict[str, dict[str, Any]], group: str, values: dict[str, float], texts: dict[str, str],
              titles: dict[str, str], markers: dict[str, float] | None = None, html: bool = False) -> list[dict[str, Any]]:
    """A set of questions' two rows under the set's heading: the setup with web off (grey), then with web (the accent
    colour, v3.css .web-off and .web-on), each with its family icon and full name."""
    return [{"group": group, "label": named[side]["name"], "href": named[side]["href"], "family": named[side]["family"]["name"],
             "bars": [{"value": values[side], "kind": f"web-{side}"}],
             "html" if html else "text": texts[side], "title": f"{named[side]['name']}, {group}: {titles[side]}",
             **({"marker": markers[side]} if markers else {})}
            for side in SIDES]


def legend_pair(named: dict[str, dict[str, Any]]) -> str:
    return (f'<span><i class="swatch swatch-web-off"></i>Web off: {esc(named["off"]["name"])}</span> '
            f'<span><i class="swatch swatch-web-on"></i>With web: {esc(named["on"]["name"])}</span>')


def card(key: str, title: str, sub: str, chart: str, named: dict[str, dict[str, Any]], legend: str = "",
         switch: str = "", wide: bool = False) -> str:
    """A chart card in its measure's section (the id the view bar's Measure row links to); wide gives the value column
    more room."""
    return (f'<section class="measure" id="{key}" aria-label="{esc(title)}">'
            f'<figure class="panel chart-card{" chart-wide" if wide else ""}" id="chart-{key}"><div class="chart-head"><h2>{esc(title)}</h2>'
            f'<p class="chart-sub">{sub}</p>{switch}</div>{chart}<p class="chart-legend">{legend_pair(named)} '
            f"<span>Each heading names the questions both setups answered.</span>{legend}</p></figure></section>")


def accuracy_chart(data: dict[str, Any], named: dict[str, dict[str, Any]], digits: int) -> str:
    def chart(rows: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]]) -> str:
        return hbars([row for label, off, on, _ in rows for row in pair_rows(
            named, f"{label} · {points({'off': off, 'on': on}):+.1f} pt", {"off": off["accuracy"], "on": on["accuracy"]},
            {side: f"{pct(item['accuracy'], digits)} · {item['correct']:,}" for side, item in (("off", off), ("on", on))},
            {side: f"{item['correct']:,} of {item['questions']:,} right" for side, item in (("off", off), ("on", on))})],
            head=("Accuracy · Right", "% · Right"))

    pilot = data["pilot"]
    body = (chart(main_arms(data)) + '<h3 class="chart-part">The Turkish full bank by part</h3>' + chart(split_arms(data))
            + f'<details class="chart-more"><summary>The pilot, {pilot["questions"]:,} questions, run first</summary>'
            + chart(pilot_arms(data)) + "</details>")
    return card("accuracy", "Accuracy", "Share of questions answered right, then the right answers; beside each set, the "
                "change with web in percentage points · higher is better", body, named)


def dont_know_pairs(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(f"Turkish, full bank, {data['dont_know']['questions']:,}", data["dont_know"]),
            (f"Turkish pilot, {data['pilot_dont_know']['questions']:,}", data["pilot_dont_know"]),
            (f"English, {data['english_dont_know']['questions']:,} kept questions, I don't know", data["english_dont_know"])]


def non_hallucination_chart(data: dict[str, Any], named: dict[str, dict[str, Any]], digits: int) -> str:
    def group(label: str, pair: dict[str, Any]) -> str:
        off, on = pair["off"], pair["on"]
        right = f"{off['right']:,} right both ways" if off["right"] == on["right"] else f"right {off['right']:,} → {on['right']:,}"
        return f"{label}: {right}, wrong {off['wrong']:,} → {on['wrong']:,}"

    def title(side: dict[str, Any]) -> str:
        return (f"the option {side['dont_know']:,} of {side['dont_know'] + side['wrong']:,} not right; answered "
                f"{pct(side['answered'], digits)}; wrong of answers {pct(side['wrong_of_answers'], digits)}")

    rows = [row for label, pair in dont_know_pairs(data) for row in pair_rows(
        named, group(label, pair), {side: pair[side]["non_hallucination"] for side in SIDES},
        {side: f"{pct(pair[side]['non_hallucination'], digits)} | {pair[side]['dont_know']:,} · "
               f"{pct(pair[side]['answered'], digits)} · {pct(pair[side]['wrong_of_answers'], digits)}" for side in SIDES},
        {side: title(pair[side]) for side in SIDES})]
    return card("non-hallucination", "Non-hallucination",
                "“Bilmiyorum” in Turkish, “I don't know” in English, offered as a sixth option: the bar is the option's "
                "share of the answers that were not right; beside it the times it was chosen, the answered share (right + "
                "wrong of the questions) and the wrong share of the answers · higher is better, read with the answered "
                "share. Not run on PWS-Decisions",
                hbars(rows, head=("Rate | Option · Answered · Wrong", "Rate | Opt · Ans · Wrong")), named,
                " <span>A setup that always chose the option would reach 100% with no right answers.</span>", wide=True)


def latency_chart(data: dict[str, Any], named: dict[str, dict[str, Any]]) -> str:
    arms_shown = main_arms(data)
    top = max(0.5, math.ceil(2 * max(side["p95_request_seconds"] for _, off, on, _ in arms_shown for side in (off, on))) / 2)
    rows = [row for label, off, on, _ in arms_shown for row in pair_rows(
        named, label, {"off": off["median_request_seconds"] / top, "on": on["median_request_seconds"] / top},
        {side: f"{ms(item['median_request_seconds'])} · {ms(item['p95_request_seconds'])} ms" for side, item in (("off", off), ("on", on))},
        {side: f"median {ms(item['median_request_seconds'])} ms, 95th percentile {ms(item['p95_request_seconds'])} ms"
         for side, item in (("off", off), ("on", on))},
        markers={"off": off["p95_request_seconds"] / top, "on": on["p95_request_seconds"] / top})]
    return card("latency", "Latency",
                "Median time per request (the bar) and 95th percentile by nearest rank (the line), one question per "
                "request, from our machine · lower is better",
                hbars(rows, top=1.0, tick=lambda value: f"{top * value:g}\u00a0s", head=("Median · p95", "Med · p95")),
                named, ' <span><i class="swatch swatch-marker"></i>95th percentile</span>')


def cost_chart(data: dict[str, Any], named: dict[str, dict[str, Any]], upper: dict[str, str]) -> str:
    arms_shown = main_arms(data)
    per_k = lambda side: side["cost_per_million_questions"] / 1000  # noqa: E731
    place, axis = log_axis([per_k(side) for _, off, on, _ in arms_shown for side in (off, on)], lambda value: value)
    write = axis.pop("tick")
    prefix = {"off": "", "on": f"{upper['mark']} "}
    rows = [row for label, off, on, _ in arms_shown for row in pair_rows(
        named, label, {"off": place(per_k(off)), "on": place(per_k(on))},
        {side: cost_value(per_k(item), prefix[side]) + (esc(" incl. search") if side == "on" else "")
         for side, item in (("off", off), ("on", on))},
        {side: cost_words(per_k(item), prefix[side]) + ("; includes the search fee" if side == "on" else "; no search fee")
         for side, item in (("off", off), ("on", on))}, html=True)]
    price = data["price"]
    return card("cost", "Cost",
                f"Estimated dollars {cost_per()}, log scale: input tokens at ${price['input_per_million']:g} per 1M, plus "
                f"${price['per_search']:g} per request with web (incl. search) · lower is better",
                hbars(rows, head=("Cost", "Cost"), tick=lambda offset: cost_tick(write(offset)), **axis), named,
                f" <span>{esc(upper['mark'])} {esc(upper['note'])}</span>", cost_switch(), wide=True)


def result_cards(data: dict[str, Any], digits: int, upper: dict[str, str]) -> str:
    """The page's first screen: the three main comparisons, each its accuracy off and with web, the change in points,
    and the cost off and with web (with web an upper-bound estimate, ≤)."""
    turkish, english, pws = (row[1:3] for row in main_arms(data))
    names = [f"Turkish, {turkish[0]['questions']:,} questions", f"English reading, {english[0]['questions']:,}",
             f"PWS-Decisions, {pws[0]['questions']:,}"]
    cards = []
    for name, (off, on) in zip(names, (turkish, english, pws)):
        cost = (f"{cost_value(off['cost_per_million_questions'] / 1000)} vs "
                f"{cost_value(on['cost_per_million_questions'] / 1000, upper['mark'] + ' ')} {cost_per()}")
        cards.append(f'<div class="result-card"><h2>{esc(name)}</h2><p class="result-main">{esc(pct(off["accuracy"], digits))} → '
                     f'{esc(pct(on["accuracy"], digits))} <span class="result-gain">({points({"off": off, "on": on}):+.1f} '
                     f'points)</span></p><p class="result-cost">{cost}</p></div>')
    return (f'<div class="result-cards">{"".join(cards)}</div><p class="note">Accuracy with web off → with web; cost web '
            f"off vs with web. {esc(upper['mark'])} Upper-bound estimate: the search fee counted for every request with "
            f'web. {cost_switch()}</p>')


def setup_cell(named: dict[str, dict[str, Any]], side: str, questions: str, run: str) -> str:
    """A table row's setup: its family icon and full name, linked to its page, with its questions and run under it."""
    item = named[side]
    return (f'<td class="model">{family_icon(item["family"]["name"])}<a class="model-name" href="{item["href"]}">'
            f'{esc(item["name"])}</a><span class="small">{esc(questions)} · {esc(run)}</span></td>')


def table(data: dict[str, Any], named: dict[str, dict[str, Any]], digits: int, upper: dict[str, str]) -> str:
    heads = (("Right", "of the questions"), ("Accuracy", "higher is better"), ("Median per request", "ms; lower is better"),
             ("95th percentile", "ms; lower is better"), ("Cost", "lower is better"),
             ("Right only with this setup", "exact McNemar p"))
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">'
                   f'{(cost_per() + "; ") if name == "Cost" else ""}{esc(note)}</span></th>' for name, note in heads)

    def rows(label: str, off: dict[str, Any], on: dict[str, Any], test: dict[str, Any] | None) -> str:
        out = []
        for side, item in (("off", off), ("on", on)):
            run = f"run {item['run']}" if "run" in item else "ours, no run id"
            prefix = f"{upper['mark']} " if side == "on" else ""
            only = "—" if test is None else f"{test[f'{side}_only']:,} ({p_text(test['p'])})"
            cells = [esc(f"{item['correct']:,} of {item['questions']:,}"), esc(pct(item["accuracy"], digits)),
                     esc(ms(item["median_request_seconds"])), esc(ms(item["p95_request_seconds"])),
                     cost_value(item["cost_per_million_questions"] / 1000, prefix)
                     + f'<span class="small">{"incl. search" if side == "on" else "no search fee"}</span>', esc(only)]
            out.append(f"<tr>{setup_cell(named, side, label, run)}"
                       + "".join(f'<td class="num" data-label="{esc(name)}">{text}</td>' for (name, _), text in zip(heads, cells))
                       + "</tr>")
        return "".join(out)

    idk_heads = (("Right · wrong · the option", "counts"), ("Answered", "(right + wrong) / questions"),
                 ("Wrong of answers", "wrong / (right + wrong)"),
                 ("Non-hallucination", "the option / (the option + wrong); higher is better"))
    idk_head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>' for name, note in idk_heads)

    def idk_rows(label: str, pair: dict[str, Any]) -> str:
        out = []
        for side in SIDES:
            item = pair[side]
            cells = [f"{item['right']:,} · {item['wrong']:,} · {item['dont_know']:,}"] + [
                pct(item[key], digits) for key in ("answered", "wrong_of_answers", "non_hallucination")]
            out.append(f"<tr>{setup_cell(named, side, label, f'run {item['run']}')}"
                       + "".join(f'<td class="num" data-label="{esc(name)}">{esc(text)}</td>' for (name, _), text in zip(idk_heads, cells))
                       + "</tr>")
        return "".join(out)

    return (f'{cost_switch()}<div class="table-wrap"><table class="board list stack wrap-headers"><thead><tr>'
            f'<th scope="col">Setup</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows(*arm) for arm in arms(data))}</tbody></table></div>'
            '<p class="note">Two rows per set of questions: off, then with web; under each name, its questions and run. Times: '
            "per request from our machine; the 95th percentile by nearest rank. Cost: each run's input tokens at the price "
            f"below, plus the fee per search for every request with web ({esc(upper['mark'])} {esc(upper['note'])}) Right "
            "only with this setup: the questions it got right and the other setup did not, with the exact McNemar p of the "
            "pair.</p>"
            '<h3 class="board-group">With “Bilmiyorum” (Turkish) or “I don\'t know” (English) as a sixth option</h3>'
            f'<div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Setup</th>{idk_head}</tr>'
            f'</thead><tbody>{"".join(idk_rows(label, pair) for label, pair in dont_know_pairs(data))}</tbody></table></div>')


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


def sources(data: dict[str, Any]) -> str:
    """What the grounded runs' searches returned: pages and sites, then the literal-match and source checks."""
    turkish, pilot, english, pws = data["turkish"], data["pilot"], data["english"], data["pws"]
    words = data["rules"]["shared_words"]
    english_shared, gains = english["search"]["shared_words"], english["paired"]["on_only"]
    if english_shared["on_only"] == 0:
        english_gains = (f"None of the {gains:,} English gains had the defined {words}+ word overlap; this does not show "
                         "that the answer, or its semantic equivalent, was absent from the returned pages.")
    else:
        english_gains = (f"{english_shared['on_only']:,} of the {gains:,} English gains had the defined {words}+ word "
                         "overlap; this does not show where a gain came from.")
    return f"""<section class="card" id="sources">
      <h2>What the search returned</h2>
      <p><strong>In short.</strong> On the full bank, {turkish['search']['shared_words']['questions']:,} questions had {words}+ consecutive question words in a returned title or snippet, and {turkish['search']['source_book']['questions']:,} got the source book itself. A word match alone does not prove that the answer was found.</p>
      <p>Unit: returned pages, up to 5 per question; each site's count is out of the run's total pages.</p>
      <p><strong>The {words}+ word check.</strong> A literal-match check: runs of {words} or more consecutive words of the question (its body and each option's text, without the option letters) in a returned page's title or snippet. It shows only such matches. Our translations are unpublished, but that does not prove the answer, or equivalent information, cannot be found on the web.</p>
      <h3>Turkish, full bank (run {turkish['on']['run']})</h3>
      <p>{returned(turkish['search'], turkish['questions'])}</p>{top_sites(turkish['search'])}
      <p>{finding(turkish, words)}</p>
      <h3>Turkish pilot (run {pilot['on']['run']})</h3>
      <p>{returned(pilot['search'], pilot['questions'])}</p>{top_sites(pilot['search'])}
      <p>{finding(pilot, words)}</p>
      <h3>English (run {english['on']['run']})</h3>
      <p>{returned(english['search'], english['questions'])}</p>{top_sites(english['search'])}
      <p>{english_shared['questions']:,} of the {english['questions']:,} English questions had a literal match of {words}+ words: {english_shared['right_off']:,} right off, {english_shared['right_on']:,} with web. {english_gains}</p>
      <h3>PWS-Decisions</h3>
      <p>{returned(pws['on']['search'], pws['on']['questions'])}</p>{top_sites(pws['on']['search'])}
      <p>{pws['on']['search']['shared_words']:,} of the {pws['on']['questions']:,} questions had a literal match of {words}+ words (its state with its instructions, or a choice's description).</p>
      <p class="note">Sites: the page addresses' host names without “www.”. Words: runs of letters and digits, case-folded. Only these counts are published: the pages' addresses, titles and snippets stay with us.</p>
    </section>"""


def caveats(data: dict[str, Any], upper: dict[str, str]) -> str:
    price, pws, reported, pilot = data["price"], data["pws"], data["pws"]["reported"], data["pilot"]
    gain = points(pilot)
    return f"""<section class="card" id="caveats">
      <h2>Read it with these caveats</h2>
      <ul>
        <li><strong>Grounded searches send the questions to Perplexity's search.</strong> Each question with web went out as a web search.</li>
        <li><strong>The pilot came first.</strong> Our protocol's first step was {pilot['questions']:,} questions ({pilot['off']['groups']['reading']['questions']:,} reading, {pilot['off']['groups']['grammar']['questions']:,} grammar; runs {pilot['off']['run']} and {pilot['on']['run']}). Its rule: a full grounded run only for a gain of more than {PILOT_RULE_POINTS} points. The pilot gained {gain:+.1f} points, short of the rule; the full-bank grounded run was made afterwards so that the setup could be ranked.</li>
        <li><strong>Costs with web are an upper bound.</strong> {esc(upper['mark'])} {esc(upper['note'])} Price: ${price['input_per_million']:g} per 1M input tokens plus ${price['per_search']:g} per completed search (<a href="{esc(price['source'])}">pricing</a>, read {esc(long_date(price['date']))}). Search evidence counts as input tokens.</li>
        <li><strong>One run per arm.</strong> The paired tests compare the two arms on the same questions.</li>
        <li><strong>Perplexity's own figures.</strong> Perplexity reported {reported['on_correct']} of {pws['on']['questions']} PWS-Decisions questions right with grounding (its run of {esc(long_date(reported['published']))}); the {reported['off_correct']}% without is the benchmark authors' (Parallel's) leaderboard figure, which Perplexity's own run matched. Its grounded requests took {ms(reported['on_median_request_seconds'])} ms at the median and {ms(reported['on_p95_request_seconds'])} ms at the 95th percentile, from Perplexity's client (<a href="{esc(reported['source'])}">{esc(reported['title'])}</a>, {esc(long_date(reported['published']))}). Ours are from our machine, run on {esc(long_date(PWS_RUN_DATE))}: {pct(pws['off']['accuracy'], 0)} off, {pct(pws['on']['accuracy'], 0)} with web; {ms(pws['on']['median_request_seconds'])} and {ms(pws['on']['p95_request_seconds'])} ms at the median and 95th percentile with web.</li>
        <li><strong>PWS-Decisions is gated.</strong> {esc(pws['name'])} (version {esc(pws['version'])}) is Parallel's dataset, for evaluation only; we publish aggregates only.</li>
      </ul>
    </section>"""


def method(data: dict[str, Any]) -> str:
    names, turkish, pilot = data["names"], data["turkish"], data["pilot"]
    reading = data["reading_units"]
    return f"""<section class="card method-notes" id="method">
      <h2>Our method</h2>
      <p>Model <code>{esc(data['model'])}</code> through Perplexity's Decisions API, one question per request, the Text tab's System One prompts. Each pair of runs differs only in the request's mode: off, or <code>web_grounding</code>, which runs a web search per question and adds its results as evidence. Runs from {esc(long_date(data['dates'][0]))} to {esc(long_date(data['dates'][-1]))}.</p>
      <ul>
        <li>Turkish, full bank: {turkish['questions']:,} questions = {turkish['off']['groups']['reading']['questions']:,} reading + {turkish['off']['groups']['grammar']['questions']:,} grammar (runs {turkish['off']['run']} and {turkish['on']['run']}, the Text tab rows {esc(names['off'])} and {esc(names['on'])}). Reading: units {", ".join(str(unit) for unit in reading[:-1])} and {reading[-1]}.</li>
        <li>Turkish pilot: {pilot['questions']:,} = {pilot['off']['groups']['reading']['questions']:,} reading + {pilot['off']['groups']['grammar']['questions']:,} grammar, the runner's sample with seed {data['sample']['seed']} (runs {pilot['off']['run']} and {pilot['on']['run']}).</li>
        <li>“Bilmiyorum” as a sixth option, as on the Hallucination tab: the full bank ({data['dont_know']['questions']:,} questions, runs {data['dont_know']['off']['run']} and {data['dont_know']['on']['run']}) and the pilot ({data['pilot_dont_know']['questions']:,}, runs {data['pilot_dont_know']['off']['run']} and {data['pilot_dont_know']['on']['run']}). “I don't know” as a sixth option in English, as on English and Turkish: the {data['english_dont_know']['questions']:,} kept questions (runs {data['english_dont_know']['off']['run']} and {data['english_dont_know']['on']['run']}).</li>
        <li>English: the {data['english']['questions']:,} kept reading questions of the English pages in our translations (runs {data['english']['off']['run']} and {data['english']['on']['run']}).</li>
        <li>PWS-Decisions: its {data['pws']['on']['questions']} public English questions with the benchmark's own request, run by us on {esc(long_date(PWS_RUN_DATE))}.</li>
      </ul>
      <p>Accuracy: right answers over the questions asked. Time: each request's wall-clock time on our machine; the median and the 95th percentile by nearest rank. Cost per 1M questions: the run's input tokens at ${data['price']['input_per_million']:g} per 1M plus ${data['price']['per_search']:g} per request with web, over its questions. The paired test: the exact McNemar test on the questions one arm got right and the other did not.</p>
      <p class="note">Download: <a href="{rel(PATH, "results.json")}" download>results.json</a> (every number on this page, under <code>web_grounding</code>), <a href="{rel(PATH, "answers.json")}" download>answers.json</a> (the pilots under <code>web_grounding_runs</code>, the other runs in their own lists) and <a href="{rel(PATH, "web-grounding.json")}" download>web-grounding.json</a> (tokens by group, the source checks' question ids and PWS-Decisions' aggregates). <code>reproduce.py</code> recomputes them.</p>
    </section>"""


def pws_section(site: Site, loaded: tuple[dict[str, Any], list[dict[str, Any]]] | None) -> str:
    """PWS-Decisions' charts of its decision-model setups (pws_decisions.py), with its framing and provenance; the chat
    models' rows are on the PWS-Decisions page only. Nothing without pws-decisions.json."""
    if loaded is None:
        return ""
    pws, items = loaded
    items = [item for item in items if not pws_decisions.chat(item["setup"])]
    return f"""<section class="card" id="pws">
      <h2>PWS-Decisions: the decision models, with and without web</h2>
      {pws_decisions.framing(pws)}
      <p>Each bar is the mean of our {pws['runs_per_setup']} runs per setup; the PWS-Decisions rows of the charts above are our first pair of runs ({esc(long_date(PWS_RUN_DATE))}), one run each. Chat models, with and without their own web search, and every number: <a href="{rel(PATH, pws_decisions.PATH)}">PWS-Decisions</a>.</p>
      {pws_decisions.provenance(pws)}
    </section>
    <section class="charts" aria-label="PWS-Decisions charts">{pws_decisions.charts(site, pws, items, PATH, "chart-pws-")}</section>"""


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
    pws_nav = '<a href="#pws">PWS-Decisions, decision models</a>' if loaded else ""
    days = sorted(set(data["dates"]) | {PWS_RUN_DATE})
    when = long_date(days[0]) if len(days) == 1 else f"{long_date(days[0])} to {long_date(days[-1])}"
    body = f"""    <section class="card">
      <p class="eyebrow">Experiment</p>
      <h1>Web grounding: {esc(site.by_id[data["text_runs"]["off"]]["name"])} off and with web</h1>
      {chat_note("Chat models: the web grounding comparison is of two decision-model setups, so it shows under All models and Decision models. PWS-Decisions, below, includes chat models.")}
      <div {DECISION_ONLY}>
      <p class="note"><a href="{named['off']['href']}">{esc(named['off']['name'])}</a> and <a href="{named['on']['href']}">{esc(named['on']['name'])}</a>, Perplexity's Decisions API without and with a web search per question; one run per setting, run on {esc(when)}.</p>
      {result_cards(data, digits, upper)}
      <nav class="face-nav" aria-label="On this page"><a href="#accuracy">Accuracy</a><a href="#non-hallucination">Non-hallucination</a><a href="#latency">Latency</a><a href="#cost">Cost</a>{pws_nav}<a href="#sources">What the search returned</a><a href="#caveats">Caveats</a><a href="#info">Detailed results</a></nav></div>
    </section>
    <section class="charts" aria-label="Charts" {DECISION_ONLY}>{accuracy_chart(data, named, digits)}{non_hallucination_chart(data, named, digits)}{latency_chart(data, named)}{cost_chart(data, named, upper)}</section>
    {pws_section(site, loaded)}
    <div {DECISION_ONLY}>
    {sources(data)}
    {caveats(data, upper)}
    <details class="info info-details" id="info">
      <summary class="info-summary"><span class="info-title">Detailed results</span> <span class="info-sub">The tables, with the pilot, the unmatched answers and the paired tests, and our method</span></summary>
    <section class="card" id="results">
      <h2>Every number</h2>
      {table(data, named, digits, upper)}
    </section>
    {method(data)}
    </details>
    </div>"""
    return {PATH: site.page(PATH, TITLE, f"{data['names']['off']} and {data['names']['on']}: accuracy, non-hallucination, "
                            "time per request and cost on our Turkish and English questions and on PWS-Decisions.", body)}
