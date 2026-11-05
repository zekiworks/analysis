"""Web grounding (web-grounding/): Perplexity Decider v1.2 through its Decisions API with web search off and with web, from
results.json's web_grounding: the two hosted setups of the Text tab on the full bank, the 200-question pilot that came
first, the "Bilmiyorum" pairs, the English pair and PWS-Decisions. Four paired charts (accuracy, non-hallucination,
latency, cost), the tables, what the search returned and the caveats. The home page's experiments line and the Perplexity
family's model pages link here."""

from __future__ import annotations

import math
from typing import Any

from build_page import long_date
from sitebuild.site import Site, dollars_tick, esc, hbars, log_axis, pct, rel

PATH = "web-grounding/"
TITLE = "Web grounding"
# A paired test's p below this reads as a difference beyond chance.
SIGNIFICANT = 0.05
# The protocol's rule on the pilot: a full grounded run only for a gain of more than this many points of accuracy.
PILOT_RULE_POINTS = 5
# The day we ran PWS-Decisions' public questions (grounding_test.py), which no run id of ours records.
PWS_RUN_DATE = "2026-11-05"
HEAD = ("Off · With web", "Off · With web")


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


def dollars(value: float) -> str:
    return f"${value:,.2f}" if value < 100 else f"${value:,.0f}"


def p_text(p: float) -> str:
    """An exact McNemar p as the page writes it: below 0.001 as a bound, else to three decimals."""
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def paired_text(item: dict[str, Any]) -> str:
    """A paired test in words, as HTML: the right answers only off and only with web, its p, and whether it tells them
    apart."""
    verdict = "a difference beyond chance" if item["p"] < SIGNIFICANT else "within chance"
    return esc(f"{item['off_only']:,} right only off, {item['on_only']:,} only with web; exact McNemar {p_text(item['p'])}, "
               f"{verdict}")


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


def main_arms(data: dict[str, Any]) -> list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]]:
    """The sets of the latency and cost charts: arms() without the reading and grammar rows."""
    return [row for row in arms(data) if not row[0].split(",")[0].endswith(("reading", "grammar"))]


def card(anchor: str, title: str, sub: str, chart: str, legend: str = "") -> str:
    return (f'<figure class="panel chart-card" id="{anchor}"><div class="chart-head"><h2>{esc(title)}</h2>'
            f'<p class="chart-sub">{sub}</p></div>{chart}<p class="chart-legend"><span><i class="swatch swatch-base"></i>'
            f'Off</span> <span><i class="swatch swatch-lead"></i>With web</span>{legend}</p></figure>')


def pair_bars(value_off: float, value_on: float) -> list[dict[str, Any]]:
    return [{"value": value_off, "kind": "base"}, {"value": value_on, "kind": "lead"}]


def accuracy_chart(data: dict[str, Any], digits: int) -> str:
    chart = hbars([
        {"label": label, "bars": pair_bars(off["accuracy"], on["accuracy"]),
         "text": f"{pct(off['accuracy'], digits)} · {pct(on['accuracy'], digits)}",
         "title": f"{label}: {off['correct']:,} right off, {on['correct']:,} with web, of {off['questions']:,}"}
        for label, off, on, _ in arms(data)], head=HEAD)
    return card("chart-accuracy", "Accuracy", "Share of questions answered right, off and with web · higher is better", chart)


def dont_know_pairs(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(f"Turkish, full bank, {data['dont_know']['questions']:,}", data["dont_know"]),
            (f"Turkish pilot, {data['pilot_dont_know']['questions']:,}", data["pilot_dont_know"]),
            (f"English, {data['english_dont_know']['questions']:,} kept questions, I don't know", data["english_dont_know"])]


def non_hallucination_chart(data: dict[str, Any], digits: int) -> str:
    def notes(side: dict[str, Any]) -> str:
        return f"{side['dont_know']:,} of {side['dont_know'] + side['wrong']:,}"

    chart = hbars([
        {"label": label, "bars": pair_bars(pair["off"]["non_hallucination"], pair["on"]["non_hallucination"]),
         "text": f"{pct(pair['off']['non_hallucination'], digits)} · {pct(pair['on']['non_hallucination'], digits)}",
         "title": f"{label}: the option {notes(pair['off'])} not right off, {notes(pair['on'])} with web"}
        for label, pair in dont_know_pairs(data)], head=HEAD)
    legend = " ".join(
        f"<span>{esc(label)}: answered {pct(pair['off']['answered'], digits)} · {pct(pair['on']['answered'], digits)}, "
        f"wrong of answers {pct(pair['off']['wrong_of_answers'], digits)} · {pct(pair['on']['wrong_of_answers'], digits)}.</span>"
        for label, pair in dont_know_pairs(data))
    return card("chart-non-hallucination", "Non-hallucination",
                "“Bilmiyorum” in Turkish, “I don't know” in English, offered as a sixth option: the option among the "
                "answers that were not right · higher is better. Not run on PWS-Decisions", chart, " " + legend)


def latency_chart(data: dict[str, Any]) -> str:
    rows = main_arms(data)
    top = max(0.5, math.ceil(2 * max(side["median_request_seconds"] for _, off, on, _ in rows for side in (off, on))) / 2)
    chart = hbars([
        {"label": label, "bars": pair_bars(off["median_request_seconds"] / top, on["median_request_seconds"] / top),
         "text": f"{ms(off['median_request_seconds'])} · {ms(on['median_request_seconds'])} ms",
         "title": f"{label}: median {ms(off['median_request_seconds'])} ms off, {ms(on['median_request_seconds'])} ms with web; "
                  f"95th percentile {ms(off['p95_request_seconds'])} ms off, {ms(on['p95_request_seconds'])} ms with web"}
        for label, off, on, _ in rows], top=1.0, tick=lambda value: f"{1000 * top * value:,.0f} ms", head=HEAD)
    p95 = "; ".join(f"{label}: {ms(off['p95_request_seconds'])} · {ms(on['p95_request_seconds'])} ms" for label, off, on, _ in rows)
    return card("chart-latency", "Latency",
                "Median time per request, one question per request, from our machine · lower is better", chart,
                f" <span>95th percentile by nearest rank, off · with web: {esc(p95)}.</span>")


def cost_chart(data: dict[str, Any], upper: dict[str, str]) -> str:
    rows = main_arms(data)
    values = [side["cost_per_million_questions"] for _, off, on, _ in rows for side in (off, on)]
    place, axis = log_axis(values, dollars_tick)
    on_text = lambda side: f"{upper['mark']} {dollars(side['cost_per_million_questions'])}"  # noqa: E731
    chart = hbars([
        {"label": label, "bars": pair_bars(place(off["cost_per_million_questions"]), place(on["cost_per_million_questions"])),
         "text": f"{dollars(off['cost_per_million_questions'])} · {on_text(on)}",
         "title": f"{label}: {dollars(off['cost_per_million_questions'])} per 1M questions off, {on_text(on)} with web"}
        for label, off, on, _ in rows], head=HEAD, **axis)
    price = data["price"]
    return card("chart-cost", "Cost",
                f"Per 1M questions, log scale: input tokens at ${price['input_per_million']:g} per 1M, plus "
                f"${price['per_search']:g} per request with web · lower is better", chart,
                f" <span>{esc(upper['mark'])} {esc(upper['note'])}</span>")


def headline(data: dict[str, Any], digits: int, upper: dict[str, str]) -> str:
    turkish, pilot, english, pws = data["turkish"], data["pilot"], data["english"], data["pws"]
    acc = lambda pair: f"{pct(pair['off']['accuracy'], digits)} to {pct(pair['on']['accuracy'], digits)}"  # noqa: E731
    on = turkish["on"]
    slower = on["median_request_seconds"] / turkish["off"]["median_request_seconds"]
    return (f"<p>With web, accuracy went from {acc(turkish)} on our full Turkish bank of {turkish['questions']:,} questions "
            f"({paired_text(turkish['paired'])}), from {acc(pilot)} on the {pilot['questions']:,}-question pilot "
            f"({paired_text(pilot['paired'])}), from {acc(english)} on our {english['questions']:,} English questions "
            f"({paired_text(english['paired'])}) and from {acc(pws)} on PWS-Decisions ({paired_text(pws['paired'])}). "
            f"On the full Turkish bank the median request took {slower:.1f} times as long, and the cost per 1M questions "
            f"went from {dollars(turkish['off']['cost_per_million_questions'])} to {upper['mark']} "
            f"{dollars(on['cost_per_million_questions'])}.</p>")


def table(data: dict[str, Any], digits: int, upper: dict[str, str]) -> str:
    heads = (("Runs", "off · with web"), ("Right", "off · with web"), ("Accuracy", "off · with web"),
             ("Median per request", "ms"), ("95th percentile", "ms"), ("Per 1M questions", "off · with web"),
             ("Right only off · only with web", "exact McNemar p"))
    head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>' for name, note in heads)

    def row(label: str, off: dict[str, Any], on: dict[str, Any], test: dict[str, Any] | None) -> str:
        def cell(name: str, write: Any, on_write: Any = None) -> str:
            return f'<td class="num" data-label="{esc(name)}">{esc(f"{write(off)} · {(on_write or write)(on)}")}</td>'

        runs = (lambda side: str(side["run"])) if "run" in off else (lambda side: "ours, no run id")
        return (f'<tr><td class="model"><span class="model-name">{esc(label)}</span></td>'
                f"{cell(heads[0][0], runs)}{cell(heads[1][0], lambda side: f'{side['correct']:,} of {side['questions']:,}')}"
                f"{cell(heads[2][0], lambda side: pct(side['accuracy'], digits))}"
                f"{cell(heads[3][0], lambda side: ms(side['median_request_seconds']))}"
                f"{cell(heads[4][0], lambda side: ms(side['p95_request_seconds']))}"
                f"{cell(heads[5][0], lambda side: dollars(side['cost_per_million_questions']), lambda side: f'{upper['mark']} {dollars(side['cost_per_million_questions'])}')}"
                f'<td class="num" data-label="{esc(heads[6][0])}">'
                f"{esc('—' if test is None else f'{test['off_only']:,} · {test['on_only']:,} ({p_text(test['p'])})')}</td></tr>")

    rows = "".join(row(label, off, on, test) for label, off, on, test in arms(data))
    idk_heads = (("Runs", "off · with web"), ("Right · wrong · the option", "off | with web"),
                 ("Answered", "(right + wrong) / questions"), ("Wrong of answers", "wrong / (right + wrong)"),
                 ("Non-hallucination", "the option / (the option + wrong)"))
    idk_head = "".join(f'<th scope="col" class="num">{esc(name)}<span class="small">{esc(note)}</span></th>' for name, note in idk_heads)
    counts = lambda side: f"{side['right']:,} · {side['wrong']:,} · {side['dont_know']:,}"  # noqa: E731

    def idk_row(label: str, pair: dict[str, Any]) -> str:
        cells = [f"{pair['off']['run']} · {pair['on']['run']}", f"{counts(pair['off'])} | {counts(pair['on'])}"] + [
            f"{pct(pair['off'][key], digits)} · {pct(pair['on'][key], digits)}" for key in ("answered", "wrong_of_answers", "non_hallucination")]
        return (f'<tr><td class="model"><span class="model-name">{esc(label)}</span></td>'
                + "".join(f'<td class="num" data-label="{esc(name)}">{esc(text)}</td>' for (name, _), text in zip(idk_heads, cells))
                + "</tr>")

    return (f'<div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">Questions</th>{head}</tr></thead>'
            f"<tbody>{rows}</tbody></table></div>"
            '<p class="note">Each cell: off · with web. Times: per request from our machine; the 95th percentile by nearest '
            "rank. Cost: each run's input tokens at the price below, plus the fee per search for every request with web "
            f"({esc(upper['mark'])} {esc(upper['note'])}) Right only off · only with web: the questions one arm got right and "
            "the other did not, with the exact McNemar p.</p>"
            '<h3 class="board-group">With “Bilmiyorum” (Turkish) or “I don\'t know” (English) as a sixth option</h3>'
            f'<div class="table-wrap"><table class="board list stack idk"><thead><tr><th scope="col">Questions</th>{idk_head}</tr>'
            f'</thead><tbody>{"".join(idk_row(label, pair) for label, pair in dont_know_pairs(data))}</tbody></table></div>')


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
        <li><strong>The pilot came first.</strong> Our protocol's first step was {pilot['questions']:,} questions ({pilot['off']['groups']['reading']['questions']:,} reading, {pilot['off']['groups']['grammar']['questions']:,} grammar; runs {pilot['off']['run']} and {pilot['on']['run']}). A full grounded run was due only for a gain of more than {PILOT_RULE_POINTS} points; the pilot gained {gain:+.1f} points. The full grounded run was made anyway, because Ümit asked for the setup in the ranking.</li>
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


def build(site: Site) -> dict[str, str]:
    data = site.results.get("web_grounding")
    if data is None:
        return {}
    check(site, data)
    digits = site.config["percent_digits"]
    upper = site.config["first_cost_marks"]["upper"]
    link = lambda arm: f'<a href="{rel(PATH, site.model_path(site.by_id[data["text_runs"][arm]]))}">{esc(data["names"][arm])}</a>'  # noqa: E731
    body = f"""    {site.tabs(PATH)}
    <section class="card">
      <p class="eyebrow">Experiment</p>
      <h1>Web grounding: Perplexity Decider v1.2 off and with web</h1>
      <p>Perplexity's Decisions API can search the web for each question and add what it finds as evidence. Both setups are in the ranking: {link('off')} and {link('on')}. This page compares them on the same questions.</p>
      {headline(data, digits, upper)}
      <nav class="face-nav" aria-label="On this page"><a href="#chart-accuracy">Accuracy</a><a href="#chart-non-hallucination">Non-hallucination</a><a href="#chart-latency">Latency</a><a href="#chart-cost">Cost</a><a href="#sources">What the search returned</a><a href="#caveats">Caveats</a><a href="#info">Info</a></nav>
    </section>
    <section class="charts" aria-label="Charts">{accuracy_chart(data, digits)}{non_hallucination_chart(data, digits)}{latency_chart(data)}{cost_chart(data, upper)}</section>
    {sources(data)}
    {caveats(data, upper)}
    <details class="info info-details" id="info">
      <summary class="info-summary"><span class="info-title">Info</span> <span class="info-sub">The tables and our method</span></summary>
    <section class="card" id="results">
      <h2>Results</h2>
      {table(data, digits, upper)}
    </section>
    {method(data)}
    </details>"""
    return {PATH: site.page(PATH, TITLE, f"{data['names']['off']} and {data['names']['on']}: accuracy, non-hallucination, "
                            "time per request and cost on our Turkish and English questions and on PWS-Decisions.", body)}
