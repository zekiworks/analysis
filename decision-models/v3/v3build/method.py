"""The Method page (method/): how we ran the test, the request format check, the full study and its limits.

Its numbers come from results.json through build_page.py's Snapshot (the values the earlier page, v1/, showed),
from page_config.json's method_records, and from answers.json where results.json holds no count. One table is new:
the reasoning pairs' gains on Reading and Grammar with the 95% interval of their difference, from results.json's
reasoning. Build checks raise ValueError when the copy no longer fits the data.
"""

from __future__ import annotations

import json
import re
from typing import Any

import build_page as bp
from v3build.site import REPO_URL, Site, esc, rel, up

PATH = "method/"
TITLE = "Method"
DESCRIPTION = (
    "How we tested decision models and chat models on a reading comprehension and grammar test "
    "in native Turkish (not translated): the questions, the settings, the measures, the routing replays, the limits "
    "and the sources."
)
# Charts kept on this page: each shows what no table here does. (name, caption)
CHARTS = {
    "coverage": "We order each model's answers by confidence and check accuracy as we keep more of them. No second model "
                "answers the rest here.",
    "calibration-all": "A point on the diagonal means the average confidence matches the hit rate in that group. Points "
                       "below it show confidence that was too high; points above it, too low.",
    "sources": "Only the score used to rank the same answers changes; the Open Jev row also changes the model that gives "
               "the score.",
}
# The rows of the setup table, in build_page.METHOD_SETUPS's order (which runs each row covers comes from there).
SETUP_TEXTS = (
    "TypeSafe's hosted decision model; Open Jev compares with it.",
    "Perplexity's Decisions API (two versions) and Liquid's free tier.",
    "Cloudflare's model, on our hardware: it adapts Qwen 3.8 27B and scores all options in one pass.",
    "Cloudflare's smaller model: Qwen 3.5 9B, with Clef's scoring method and release code.",
    "It adapts Qwen 3.5 4B and lists Turkish among its training languages.",
    "blockbrain-ai's recipe on an unchanged Gemma 4 12B IT, served by vLLM: answer letter probabilities rescaled with a "
    "temperature of 3.4.",
    "Gemma 4 12B IT trained for decisions, published only as GGUF files: the recommended Q8_0 file (eight bits per weight) "
    "on its author's llama.cpp-based server.",
    "Fastino's System One API. GLiDE reasons more on uncertain cases, which we could not switch off.",
    "Celeris's System One API: probabilities rounded to whole points, no model size or design published.",
    "SubQ's Decisions API, in public preview, with no model size or design published.",
    "Amazon's released model: an adapter and a scoring part on Qwen 3.5 2B Base, with its own server.",
    "Both released models, on our hardware; each scores all options in one pass.",
    "Fastino's {size} parameter text classifier, scoring the options as labels: a much smaller baseline.",
    "The same {size} parameter model, trained by Fastino for decisions.",
    "The released open model, with its own scoring part and calibration setting.",
    "Open Jev's base model and prompts without its trained parts: the preference for Yes over No, with a calibration "
    "temperature of 1.",
    "The base model chooses an option and writes its confidence.",
    "Ten sampled answers: the most common one, with the share that agrees as confidence.",
    "Chat models for comparison; each writes a confidence estimate. Sonnet and Gemini Flash ran with low and with high "
    "reasoning.",
    "OpenAI's Decisions API, in beta, {per_request} question per request. The other Luna run writes its confidence "
    "through Codex, {other_per_request} questions per request.",
    "On our hardware, with answer letter probabilities. DeepSeek's reasoning run also samples.",
    "Z.ai's model with TensorFold: {size} parameters, about {active} used per token (a mixture of experts); it writes its "
    "confidence. Mia's AI Lab's EXL3 checkpoint, with DFlash2 speculative decoding.",
    "Erk continues this Qwen model's training on Turkish text; both ran with the same requests and settings.",
)
REFERENCES = (
    ("Mitchell, M., &amp; Krakauer, D. C. (2023). The debate over understanding in AI's large language models. Proceedings "
     "of the National Academy of Sciences, 120(13), e2215907120.", "https://doi.org/10.1073/pnas.2215907120"),
    ("Chollet, F. (2019). On the Measure of Intelligence. arXiv:1911.01547.", "https://arxiv.org/abs/1911.01547"),
    ("Yüksel, A., Köksal, A., Şenel, L. K., Korhonen, A., &amp; Schütze, H. (2024). TurkishMMLU: Measuring Massive "
     "Multitask Language Understanding in Turkish. Findings of EMNLP 2024.", "https://aclanthology.org/2024.findings-emnlp.413/"),
    ("Liang, P., et al. (2023). Holistic Evaluation of Language Models. Transactions on Machine Learning Research.",
     "https://arxiv.org/abs/2211.09110"),
    ("Chen, L., Zaharia, M., &amp; Zou, J. (2023). FrugalGPT: How to Use Large Language Models While Reducing Cost and "
     "Improving Performance. arXiv:2305.05176.", "https://arxiv.org/abs/2305.05176"),
    ("Ong, I., et al. (2024). RouteLLM: Learning to Route LLMs with Preference Data. arXiv:2406.18665.",
     "https://arxiv.org/abs/2406.18665"),
    ("Snell, C., Lee, J., Xu, K., &amp; Kumar, A. (2024). Scaling LLM Test-Time Compute Optimally can be More Effective "
     "than Scaling Model Parameters. arXiv:2408.03314.", "https://arxiv.org/abs/2408.03314"),
    ("Zheng, C., Zhou, H., Meng, F., Zhou, J., &amp; Huang, M. (2024). Large Language Models Are Not Robust Multiple "
     "Choice Selectors. ICLR 2024.", "https://arxiv.org/abs/2309.03882"),
    ("Ribeiro, M. T., Wu, T., Guestrin, C., &amp; Singh, S. (2020). Beyond Accuracy: Behavioral Testing of NLP Models with "
     "CheckList. Proceedings of ACL, pp. 4902–4912.", "https://aclanthology.org/2020.acl-main.442/"),
    ("Geifman, Y., &amp; El-Yaniv, R. (2017). Selective Classification for Deep Neural Networks. Advances in Neural "
     "Information Processing Systems 30.", "https://arxiv.org/abs/1705.08500"),
    ("Guo, C., Pleiss, G., Sun, Y., &amp; Weinberger, K. Q. (2017). On Calibration of Modern Neural Networks. Proceedings "
     "of ICML, PMLR 70, 1321–1330.", "https://arxiv.org/abs/1706.04599"),
    ("Xiong, M., et al. (2024). Can LLMs Express Their Uncertainty? An Empirical Evaluation of Confidence Elicitation in "
     "LLMs. ICLR 2024.", "https://arxiv.org/abs/2306.13063"),
    ("Kadavath, S., et al. (2022). Language Models (Mostly) Know What They Know. arXiv:2207.05221.",
     "https://arxiv.org/abs/2207.05221"),
    ("McCoy, R. T., Pavlick, E., &amp; Linzen, T. (2019). Right for the Wrong Reasons: Diagnosing Syntactic Heuristics in "
     "Natural Language Inference. Proceedings of ACL, pp. 3428–3448.", "https://aclanthology.org/P19-1334/"),
    ("Beckmann, P., &amp; Queloz, M. (2026). Mechanistic indicators of understanding in large language models. "
     "Philosophical Studies, 183, 1747–1792.", "https://doi.org/10.1007/s11098-026-02513-1"),
    ("Blanck, R., &amp; Noble, B. (2026). Logic, inference, understanding: cross-domain generalization for generative "
     "language models. Frontiers in Artificial Intelligence, 9, 1800372.", "https://doi.org/10.3389/frai.2026.1800372"),
    ("Dietterich, T. G. (1998). Approximate Statistical Tests for Comparing Supervised Classification Learning "
     "Algorithms. Neural Computation, 10(7), 1895–1923.", "https://doi.org/10.1162/089976698300017197"),
    ("Card, D., Henderson, P., Khandelwal, U., Jia, R., Mahowald, K., &amp; Jurafsky, D. (2020). With Little Power Comes "
     "Great Responsibility. Proceedings of EMNLP 2020, pp. 9263–9274.", "https://aclanthology.org/2020.emnlp-main.745/"),
    ("Sainz, O., et al. (2023). NLP Evaluation in trouble: On the Need to Measure LLM Data Contamination for each "
     "Benchmark. Findings of EMNLP 2023.", "https://arxiv.org/abs/2310.18018"),
    ("Northcutt, C. G., Athalye, A., &amp; Mueller, J. (2021). Pervasive Label Errors in Test Sets Destabilize Machine "
     "Learning Benchmarks. NeurIPS 2021 Datasets and Benchmarks Track.", "https://arxiv.org/abs/2103.14749"),
)
# The earlier page's price list texts (v1/app.js): the reuse note and the lines for free and self-hosted runs.
REUSE_EXPLAINED = "A service may save input so a later call can reuse it. It may charge one rate to save it and another to read it again."
FREE_RATE = "Free tier used; no paid rate in this record."
NO_COST_LOCAL = "No dollar estimate; see hardware and time"


class Cites:
    """Numbered citations: each call links to its reference and gets an id the reference list links back to."""

    def __init__(self) -> None:
        self.used: dict[int, list[str]] = {}

    def __call__(self, number: int) -> str:
        ids = self.used.setdefault(number, [])
        ids.append(f"cite-{number}-{'abcdefgh'[len(ids)]}")
        return f'<sup class="cite"><a id="{ids[-1]}" href="#ref-{number}">{number}</a></sup>'

    def references(self) -> str:
        items = []
        for number, (text, url) in enumerate(REFERENCES, start=1):
            back = "".join(f' <a class="backref" href="#{anchor}" aria-label="Return to the paragraph that cites this source">↩</a>'
                           for anchor in self.used.get(number, []))
            items.append(f'<li id="ref-{number}">{text} <a href="{url}">{url}</a>{back}</li>')
        return f'<ol class="references">{"".join(items)}</ol>'


def snapshot(site: Site) -> bp.Snapshot:
    """build_page.py's Snapshot over a copy of results.json (it adds request size labels to the runs it holds), with
    the count of checks from running reproduce.py (bp.reproduce), which stops the build unless every check matches."""
    return bp.Snapshot(json.loads(json.dumps(site.results)), site.config, bp.reproduce())


def signed(points: float) -> str:
    return f"{points:+.1f}".replace("-", "\u2212")


def reasoning_pairs(site: Site, snap: bp.Snapshot) -> list[dict[str, Any]]:
    """results.json's reasoning pairs (N3), in page_config.json's order: each one's gain on Reading and on Grammar, and
    the 95% interval of the Grammar gain minus the Reading gain, in points. The build stops when results.json's pairs
    are not page_config.json's, or when the reasoning paragraph no longer fits them."""
    published = {(item["low"], item["high"]): item for item in site.results["reasoning"]["pairs"]}
    pairs = []
    for first_key, second_key in site.config["reasoning_pairs"]:
        first, second = snap.named[first_key], snap.named[second_key]
        item = published.get((first["run"], second["run"]))
        if item is None:
            raise ValueError(f"results.json has no reasoning pair {first_key} → {second_key}")
        pairs.append({
            "keys": (first_key, second_key), "first": first, "second": second,
            "reading": 100 * item["reading_gain"], "grammar": 100 * item["grammar_gain"],
            "low": 100 * item["interval"][0], "high": 100 * item["interval"][1],
        })
    if len(pairs) != len(published):
        raise ValueError("results.json has reasoning pairs page_config.json does not name")
    keys = {key for item in pairs for key in item["keys"]}
    sonnet = next((item for item in pairs if item["keys"] == ("sonnet_low", "sonnet_high")), None)
    failed = [bp.label(item["first"]) for item in pairs if not item["grammar"] > item["reading"] or not item["low"] > 0]
    if (len(pairs) != 4 or failed or sonnet is None or signed(sonnet["grammar"]) != "+32.7" or signed(sonnet["reading"]) != "+2.3"
            or not {"deepseek_off", "deepseek_on", "glm_off", "glm_on"} <= keys):
        raise ValueError(f"the reasoning paragraph no longer fits the four pairs (failing: {failed or 'Sonnet, DeepSeek or GLM'})")
    return pairs


def pair_label(item: dict[str, Any]) -> str:
    low, high = item["first"]["reasoning"], item["second"]["reasoning"]
    setting = f"reasoning {low} → {high}" if {low, high} == {"off", "on"} else f"{low} → {high} reasoning"
    return f"{esc(item['first']['name'])}, {setting}"


def pairs_table(pairs: list[dict[str, Any]]) -> str:
    heads = ("Pair", "Reading gain (points)", "Grammar gain (points)", "Difference (grammar gain minus reading gain, points)",
             "95% interval of the difference")
    rows = "".join(
        f'<tr><td data-label="{heads[0]}">{pair_label(item)}</td>'
        f'<td class="num" data-label="{heads[1]}">{signed(item["reading"])}</td>'
        f'<td class="num" data-label="{heads[2]}">{signed(item["grammar"])}</td>'
        f'<td class="num" data-label="{heads[3]}">{signed(item["grammar"] - item["reading"])}</td>'
        f'<td class="num" data-label="{heads[4]}">{signed(item["low"])} to {signed(item["high"])}</td></tr>'
        for item in pairs
    )
    head = "".join(f'<th scope="col"{"" if index == 0 else " class=\"num\""}>{text}</th>' for index, text in enumerate(heads))
    return f'<div class="table-wrap"><table class="overview cards"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'


def average_cost(snap: bp.Snapshot) -> tuple[str, str]:
    """In how many of the worked example's live tests (one per second model and rule, at the second model's own request
    size) the live saving was smaller than the replay's, out of how many. The build stops unless the passed questions
    cost more than the second model's average question in most of them."""
    replayed = {item["key"]: item for item in snap.replay["frontiers"]}
    rule_of = {"half": "strict", "share": "share", "cutoff": "sure"}
    tests = [(key, rule, test) for key, rules in bp.live_tests(snap)["decider"].items() for rule, test in rules.items()]
    smaller = sum(bp.saving(test["measured"]) < replayed[key][rule_of[rule]]["saving"] for key, rule, test in tests)
    dearer = sum(bp.passed_cost(test) > 1 for _, _, test in tests)
    if not 2 * dearer > len(tests) or not 2 * smaller > len(tests):
        raise ValueError("the average-cost caveat says the passed questions mostly cost more and the live savings were mostly smaller")
    return bp.in_words(smaller), bp.in_words(len(tests))


def from_here(figure: str) -> str:
    """A figure built for the site's folder (charts/…), with its links made relative to this page inside v3/."""
    charts = up(PATH, "charts/")
    return figure.replace('href="charts/', f'href="{charts}').replace('src="charts/', f'src="{charts}')


def chart(name: str, alt: str, caption: str) -> str:
    """A chart in both themes, linked from this page to charts/."""
    return from_here(bp.chart_sizes(bp.chart_figure(name, alt, caption)))


def chart_alt(block: str, name: str) -> str:
    """The accessible description build_page.py gives a chart, from its figure."""
    found = re.search(rf'src="charts/{re.escape(name)}\.svg" alt="([^"]*)"', block)
    if not found:
        raise ValueError(f"build_page.py no longer draws the chart {name}")
    return found.group(1).replace("&#x27;", "'").replace("&quot;", '"').replace("&amp;", "&")


def setups_table(site: Site, snap: bp.Snapshot) -> str:
    """Why each model is in the test: build_page.METHOD_SETUPS's rows (which runs each covers) with this page's shorter
    texts. Each name links to its first setup's page."""
    if len(SETUP_TEXTS) != len(bp.METHOD_SETUPS):
        raise ValueError("SETUP_TEXTS needs one text per row of build_page.METHOD_SETUPS")
    used: set[int] = set()
    rows = []
    for (specs, _), text in zip(bp.METHOD_SETUPS, SETUP_TEXTS):
        runs = [run for run in snap.runs if any(bp.matches(run, spec) for spec in specs)]
        if not runs or used & {run["run"] for run in runs}:
            raise ValueError(f"the setup row {specs} matches no run or a run another row has")
        used |= {run["run"] for run in runs}
        first = runs[0]
        others = [run for run in snap.runs if run["model"] == first["model"] and run not in runs]
        fields = {
            "size": bp.method_size(first["parameters"]) if first.get("parameters") else "",
            "active": bp.and_list([bp.method_size(value) for value in first["active_parameters"]]) if first.get("active_parameters") else "",
            "per_request": bp.in_words(first["questions_per_request"]),
            "other_per_request": bp.count(others[0]["questions_per_request"]) if others else "",
        }
        firsts = {}
        for run in runs:
            firsts.setdefault(run["name"], run)
        names = bp.and_list([f'<a href="{rel(PATH, site.model_path(run))}">{esc(name)}</a>' for name, run in firsts.items()])
        rows.append(f'<tr><th scope="row">{names}</th><td><p>{esc(text.format(**fields))}</p></td></tr>')
    missing = [bp.label(run) for run in snap.runs if run["run"] not in used]
    if missing:
        raise ValueError(f"setups without a row: {', '.join(missing)}")
    return ('<div class="table-wrap"><table class="setups"><thead><tr><th scope="col">Model or setup</th>'
            f'<th scope="col">Why we included it</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def display_name(run: dict[str, Any]) -> str:
    details = [item for item in (run.get("variant"), run.get("format")) if item]
    return run["name"] + (f" ({', '.join(details)})" if details else "")


def rate(value: float) -> str:
    if float(value).is_integer():
        return f"${int(value)}"
    whole, decimals = repr(value).split(".")
    return f"${whole}.{decimals.ljust(2, '0')}"


def rate_parts(price: dict[str, Any]) -> list[str]:
    rates = price["rates"]

    def differs(key: str) -> bool:
        return rates.get(key) is not None and rates[key] != rates["input_tokens"]

    parts = [f"input {rate(rates['input_tokens'])}"]
    if differs("cached_input_tokens"):
        parts.append(f"reused input {rate(rates['cached_input_tokens'])}")
    short, long = differs("cache_write_input_tokens"), differs("cache_write_1h_input_tokens")
    if short and long:
        parts.append(f"saving input for reuse {rate(rates['cache_write_input_tokens'])} for 5 minutes, "
                     f"{rate(rates['cache_write_1h_input_tokens'])} for 1 hour")
    elif short or long:
        parts.append(f"saving input for reuse {rate(rates['cache_write_input_tokens' if short else 'cache_write_1h_input_tokens'])}")
    parts.append(f"output {rate(rates['output_tokens'])}" if rates["output_tokens"] else "output free")
    return parts


def price_list(snap: bp.Snapshot) -> str:
    """The price notes as the earlier page's app.js (v1/) drew them under "How we estimate the money cost"."""
    def names(runs: list[dict[str, Any]]) -> str:
        return ", ".join(dict.fromkeys(display_name(run) for run in runs))

    items = []
    if any(part.startswith(("reused", "saving")) for price in snap.results["prices"] for part in rate_parts(price)):
        items.append(esc(REUSE_EXPLAINED))
    for price in snap.results["prices"]:
        runs = [run for run in snap.runs if run["provider"] == price["provider"] and run["model"] == price["model"]]
        change = f" Provider update: {esc(price['change'])}." if price.get("change") else ""
        items.append(f"{esc(names(runs) or price['model'])}. Prices recorded {bp.long_date(price['date'])}. "
                     f"Per one million tokens: {esc('; '.join(rate_parts(price)))}. Source: "
                     f'<a href="{esc(price["source"])}">{esc(price["basis"])}</a>.{change}')
    free = [run for run in snap.runs if run["billing"] == "free"]
    local = [run for run in snap.runs if run["billing"] == "local"]
    if free:
        items.append(esc(f"{names(free)}. {FREE_RATE}"))
    if local:
        items.append(esc(f"{names(local)}. {NO_COST_LOCAL}."))
    return '<ul class="footnote price-list">' + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def build(site: Site) -> dict[str, str]:
    snap = snapshot(site)
    v = bp.values(snap)
    cite = Cites()
    pairs = reasoning_pairs(site, snap)
    smaller, live_total = average_cost(snap)
    study = bp.study_blocks(snap, {})
    held_out = bp.one_size({test["plan"]["held_out"] for test in bp.decider_tests(snap)}, "the live tests")
    limit = bp.one_size({test["plan"]["tolerance_points"] for test in bp.decider_tests(snap)}, "the loss limit")
    reruns = bp.rerun_frontiers(snap)
    if any(-100 * item["strict"]["difference"] > limit for item in reruns):
        raise ValueError("the worked example says no one-question-per-request row loses more than the loss limit")
    formats = snap.results["formats"]
    timing = bp.method_timing(snap)
    for old, new in (("response times", "latencies"), ("the measured rate", "the measured throughput")):
        if old not in timing:
            raise ValueError(f"build_page.method_timing no longer says {old!r}")
        timing = timing.replace(old, new)
    link = lambda target, text: f'<a href="{rel(PATH, target)}">{text}</a>'  # noqa: E731
    results_file = f'<a href="{up(PATH, "results.json")}">results file</a>'
    answer_file = f'<a href="{up(PATH, "answers.json")}">answer export</a>'
    calibration_alt = chart_alt(study["study-calibration"], "calibration-all")
    if "; the table keeps them." not in calibration_alt:
        raise ValueError("the calibration chart's description changed; check what it says about the table")
    calibration_alt = calibration_alt.replace("; the table keeps them.", ".")
    paired_figure = from_here(bp.chart_sizes(bp.method_paired_figure(snap)))

    sections = [
        ("main-findings", "What we found", f"""
<p>No model led on every measure: accuracy, ranking answers by confidence and confidence that matches the hit rate are
separate strengths. Gemma 4 31B, a chat model, scored higher than every decision model on Reading ({v['gemma_reading']})
and Grammar ({v['gemma_grammar']}), but its confidence matched its hit rate less closely than the best decision models'
did.</p>
<p>How a model gives its confidence matters. GPT-6 Luna through OpenAI's Decisions API ranked its answers better than Luna
writing its confidence (ranking score {v['luna_api_auroc']} against {v['luna_stated_auroc']}) but got fewer right
({v['luna_api_accuracy']} against {v['luna_stated_accuracy']}), with a different access method and request size. Among
decision models, it had the smallest calibration gap: {v['luna_api_ece_points']} points.</p>
<p>Cheaper chat models remain alternatives. GPT-6.1 Sol scored {v['sol_accuracy']} at an estimated cost {v['sol_saving']}
below GPT-6 Astra's ({v['astra_accuracy']}). Gemini 3.8 Flash at high reasoning scored {v['gemini_high_accuracy']}, and the
test over all pairs did not establish a difference from Astra.</p>
<p>Erk-14B is Qwen3-14B with extra Turkish training by eCloud. Its calibration gap was {v['erk_ece_points']} points against
{v['qwen3_14b_ece_points']} for its base, with no accuracy difference detected ({v['erk_accuracy']} against
{v['qwen3_14b_accuracy']}); the training may have changed more than language knowledge.</p>
<p>On Artificial Analysis' <a href="https://artificialanalysis.ai/articles/artificial-analysis-decision-index">Decision Index</a>
(English tasks), Jev 1.13 leads with 58, ahead of GLiDE and Microsoft-Decision-1 (54). Our order differs. In both tests,
confidence is less reliable on some question types: knowledge and reasoning there, grammar here.</p>"""),
        ("tests", "The questions", f"""
<p>The test has {v['reading_questions']} Reading and {v['grammar_questions']} Grammar questions in {v['study_units']} topics,
so {v['grammar_share']} are Grammar. Reading asks about the meaning of words, sentences and passages; Grammar asks about word
endings, word types and sentence structure. We report the two separately.</p>
<p>Topics {v['study_reading_units']} are Reading and {v['study_grammar_units']} Grammar; the {link('topics/', 'Topics page')}
gives each one's results. Each question has {v['baseline_options']} options: guessing averages {v['baseline_random']}, and
always choosing {v['baseline_letter']}, the most common right letter, scores {v['baseline_letter_share']}. Models can favour
some letters whatever the question says.{cite(8)}</p>
<p>An optional exam mix reweights the scores to the Turkish section of the first stage of Turkey's 2026 university entrance
exam (TYT): {v['exam_reading']} Reading and {v['exam_grammar']} Grammar questions. It is not a score on the exam itself.</p>
<p>TurkishMMLU{cite(3)} covers more than 10,000 Turkish questions in nine school subjects, and HELM{cite(4)} sets accuracy
beside calibration and efficiency. We study the decision models' own option scores, and using them to decide when another
model should answer. We do not know what most models saw in training, so we cannot test whether less familiar tasks cause
more mistakes.</p>"""),
        ("repair", "How we checked the questions and answer key", f"""
<p>We use version 2 of the question set. Our first copy of the book lost the underline in {v['method_underline_lost']} of
{v['method_underline_questions']} questions that point to underlined words, and the numbers attached to words in
{v['method_numbers_lost']} more; we copied flagged questions again and checked them against the page images. Version 2
changes the text or key of {v['method_text_or_key_changed']} questions and makes {v['method_added']} more possible to
score.</p>
<p>Wrong keys are common in test sets and can change rankings.{cite(20)} We reviewed {v['method_review_cases']} disputed
cases (confident mistakes, and questions where several strong models disagreed with the key), confirmed
{v['method_review_confirmed']} keys and removed {v['method_excluded']} questions: in {v['method_review_unsettled']} the page
image did not settle the answer, and in {v['method_review_disputed']} the printed key could not be established. We score
{v['questions']} questions; {v['method_suspect']} stay marked uncertain, and {v['method_verified']} carry a verified
label.</p>
<p>The removal raised most models' accuracy by at most about {v['method_review_rise']} points but mattered more for confident
mistakes. Among wrong answers at {v['threshold']} or more, it removed {v['method_audit_qwen_yes_no_removed']} of
{v['method_audit_qwen_yes_no_before']} for Qwen's yes or no scoring, {v['method_audit_astra_removed']} of
{v['method_audit_astra_before']} for Astra, {v['method_audit_jev_removed']} of {v['method_audit_jev_before']} for Jev and
{v['method_audit_d1_removed']} of {v['method_audit_d1_before']} for d1. Later runs did not get this targeted review.</p>
<p>For models tested on both versions, accuracy on the repaired questions rose {v['method_repair_low']} to
{v['method_repair_high']} points{v['method_repair_others']}. Removed questions stay out of accuracy and confidence, but their
time, tokens and money stay in the totals.</p>
<p>Every setup is scored on the same frozen key, {v['key_version']}. A fix needs a check against the book's key or a second
reviewer, and it rescores every run under a new version; the
<a href="{REPO_URL}/blob/main/decision-models/key-changelog.md">key changelog</a> lists every change.</p>
<p>The source is the practice book <i>TYT IQ Turkish Question Library</i> (title translated) from Paraf, ISBN
978-625-7423-18-2 (© 2022, no edition number). We do not publish its copyrighted questions; with the book, the scripts in the
repository's <code>runner</code> folder rebuild a matching set, matched by each question's ID, topic, page and number.</p>"""),
        ("setups", "Models and setups", f"""
<p>A decision model scores the options we give it, and we used only its pick and its scores. A chat model writes its answer,
and some reason first. Luna through the Decisions API counts as a decision model, because the service gives a probability
for each option.</p>
<p>A setup is one way of running a model: access, reasoning setting, questions per request and other settings. We tested
{v['configs']} setups of {v['models']} models. Each name links to its setup's page; the results file keeps each identifier,
server and hardware.</p>
{setups_table(site, snap)}"""),
        ("sending", "What we sent and which settings we used", f"""
<p>Each question went with its lettered options. Chat models were asked, in Turkish, for their answer's letter and, where
needed, a confidence score, in a structured reply (JSON); a connector turned the same question into each decision service's
format. Most chat setups got {v['batch_size']} questions per request; decision models, Luna through the Decisions API,
GLiNER and the Qwen 3.8 setups got one.</p>
<p>Claude Code and Codex runs were closed-book: no web search, no file or command tools, and an empty folder for each
request. Earlier trial runs could find the source book online.</p>
<p>A missing answer, a refusal or a letter outside the options counts as wrong. The Decisions API declined
{v['luna_api_unanswered']} questions; GLM 5.3 Flash with reasoning left {v['glm_on_unanswered']} unanswered when it hit the
65,536-token output limit; DeepSeek's reasoning run had the same limit and left {v['deepseek_on_unanswered']}.</p>
<div class="table-wrap"><table class="settings"><thead><tr><th scope="col">Setup</th><th scope="col">How it chose each token</th></tr></thead><tbody>
<tr><td>Chat models on our hardware, reasoning off</td><td>Greedy decoding: the most likely next token</td></tr>
<tr><td>DeepSeek, reasoning on</td><td>Sampling, temperature 1.0, top p 1.0 (greedy decoding made its reasoning loop)</td></tr>
<tr><td>GLM 5.3 Flash, reasoning on</td><td>Server default: temperature 1.0, top p 0.95 (Z.ai's settings), top k 20; TensorFold's high reasoning</td></tr>
<tr><td>Qwen, ten answers</td><td>Temperature 0.7, top p 0.8, top k 20, presence penalty 1.5</td></tr>
<tr><td>GPT, Claude and Gemini</td><td>Lowest reasoning setting, plus high reasoning for Sonnet and Gemini Flash; temperature not always settable; Gemini reported no reasoning tokens at low</td></tr>
</tbody></table></div>
<p class="table-note">Sampling picks the next token at random by its probability. Temperature sets how strongly it favours
likely tokens, top p and top k limit the candidates, and a presence penalty discourages repeats.</p>"""),
        ("format", "Does one question per request change the answers?", f"""
<p>Every decision model got one question per request; the chat models' main runs got {v['batch_size']}. So we asked
{bp.in_words(len(formats))} chat setups all {v['questions']} questions again, one per request, with the same prompt and
settings.</p>
{bp.format_table(snap)}
<p class="table-note">The exact McNemar test uses only the questions one run got right; Holm's correction covers this table.
Each run with one question per request is a setup of its own.</p>
<p>An earlier test on {v['method_single_questions']} questions found no difference: Astra got
{v['method_single_astra_correct']} right with one question per request and {v['method_single_astra_compared']} in
{v['method_single_astra_runs']} runs with {v['batch_size']}, and Gemma {v['method_single_gemma_correct']} against
{v['method_single_gemma_compared']} in {v['method_single_gemma_runs']} runs from an earlier server session.</p>"""),
        ("confidence-sources", "Where each confidence score comes from", f"""
<dl class="sources">
<dt>Option score</dt><dd>The probability a decision model, GLiNER or Qwen's yes or no scoring gives the chosen option.</dd>
<dt>Written estimate</dt><dd>A number GPT, Claude, Gemini, GLM or Qwen writes next to its answer.</dd>
<dt>Answer letter probability</dt><dd>For Gemma, DeepSeek, Qwen 3 14B and Erk, the probability of writing the chosen letter,
rescaled over the option letters to 100%; with reasoning on, it comes after the reasoning.</dd>
<dt>Agreement across ten answers</dt><dd>The share of Qwen's ten answers that agree with the most common one (eight of ten
gives 80%).</dd>
</dl>
<p>We test each mechanism against the real answers before we trust it. Some services round: Luna through the Decisions API
gave {v['method_luna_api_distinct']} distinct scores across {v['method_luna_api_scored']} answered questions, and Celeris
{v['method_celeris_distinct']} across {v['method_celeris_scored']}, none above {v['method_celeris_top']}; our calculations
handle tied scores.</p>
<h3 id="open-jev">How Open Jev turns option scores into probabilities</h3>
<p>Open Jev adds a LoRA adapter, 15.5 million adjustable values (about 0.06% of the base model), and a scoring head to a
Qwen model. Each option gets its own prompt, and the head starts from Qwen's preference for "Yes" over "No". Softmax turns
the scores into probabilities after dividing them by 2.53, the calibration temperature (see the
<a href="https://huggingface.co/ZefanCai/Open-Jev-27B-v1.1">model card</a>).</p>
<p>Another positive temperature never changes the winning option within a question, but it can reorder confidence across
questions. We use the chosen option's ordinary probability, not the rescaled score Jev and Open Jev also offer. Open Jev
scored {v['pair_open_jev_qwen_yes_no_difference']} points above Qwen's yes or no scoring (p =
{v['pair_open_jev_qwen_yes_no_p_holm']} after adjustment), with ranking scores of {v['open_jev_auroc']} and
{v['qwen_yes_no_auroc']}.</p>
<p>Its probabilities were too low here. Its highest confidence was {v['method_open_jev_top']}, yet
{v['method_open_jev_band_result']} {v['method_open_jev_band_answers']} answers scored {v['method_open_jev_band']} were
right. On version 1 of the question set, a separate refit of the temperature cut the calibration gap from
{v['method_refit_ece_before']} to {v['method_refit_ece_after']} points, while the ranking score moved from
{v['method_refit_auroc_before']} to {v['method_refit_auroc_after']}; the main results use the released model.</p>"""),
        ("measures", "How we measure accuracy and confidence", f"""
<p>Accuracy is the share of scored questions a model got right. The ranking score (AUROC) is how often a randomly chosen right
answer has higher confidence than a randomly chosen wrong one, with half credit for ties: 0.50 is chance, 1.00 perfect.</p>
<p>Keeping only the most confident answers is called selective prediction.{cite(10)} The most confident
{v['study_coverage_first']} takes that share of answers with the highest scores and checks how many are right; the
{v['study_coverage_rest']} shares work the same way. They describe the kept answers only.</p>
{chart("coverage", chart_alt(study["study-coverage"], "coverage"), CHARTS["coverage"])}
<p>Calibration asks whether the percentages match the hit rate: of 100 answers scored near 80%, about 80 should be right.
The calibration gap (ECE){cite(11)} sorts answers into {v['study_confidence_groups']} confidence groups (0% to below 10%, and
so on) and compares each group's average confidence with its share right. It averages these gaps, weighting larger groups
more, in points. Zero means a match within the groups, not that every score is right; the chart leaves out groups with
fewer than {v['study_calibration_min']} answers.</p>
{chart("calibration-all", calibration_alt, CHARTS["calibration-all"])}
<h3 id="sure">What a score of {v['threshold']} or more meant</h3>
<p>At {v['threshold']} or more, Jev got {v['jev_correct']} of {v['jev_accepted']} right, d1 {v['d1_correct']} of
{v['d1_accepted']}, Decider v1 {v['decider_v1_correct']} of {v['decider_v1_accepted']} and GLiDE {v['glide_correct']} of
{v['glide_accepted']}; Luna got {v['luna_api_correct']} of {v['luna_api_accepted']} through the Decisions API and
{v['luna_stated_correct']} of {v['luna_stated_accepted']} writing its confidence. Few answers leave wide intervals: the 95%
interval for the error rate is {v['decider_v1_error_span']} for Decider v1 and {v['glide_error_span']} for GLiDE.</p>
<p>Gemma's letter probability reached {v['threshold']} on {v['study_gemma_sure_kept']} answers, {v['study_gemma_sure_correct']}
of them right (about {v['study_gemma_sure_accuracy']}). DeepSeek with reasoning gave every answer at least
{v['threshold']}, and about {v['study_deepseek_on_sure_accuracy']} were right.</p>
<h3 id="sources">Can another confidence method make the same answers easier to judge?</h3>
<p>We scored one fixed set of Qwen 3.8 27B answers, {v['study_sources_correct']} right of {v['study_sources_questions']},
four ways. The ranking score was about {v['study_source_qwen_stated_auroc']} for written confidence,
{v['study_source_qwen_yes_no_auroc']} for Qwen's option score, {v['study_source_qwen_votes_auroc']} for agreement across ten
answers and {v['study_source_open_jev_auroc']} for Open Jev, a separately trained model. Written confidence tends to bunch at
high values,{cite(12)} while large models' answer probabilities can match their hit rates well.{cite(13)}</p>
<p>The most common of ten answers scored {v['qwen_votes_accuracy']}, against {v['qwen_stated_accuracy']} for written
confidence, and only about {v['study_qwen_votes_sure_accuracy']} were right when all ten agreed. Several answers can repeat one
mistake.</p>
{chart("sources", chart_alt(study["study-sources"], "sources"), CHARTS["sources"])}"""),
        ("differences", "How we tell a score gap from ordinary variation", f"""
<p>Both models answer the same questions, so we look at the questions only one got right. The exact McNemar test{cite(17)}
asks whether that split is too uneven for equal accuracy. Holm's method adjusts the p values for the number of tests: across
{v['comparisons']} selected comparisons, and across all {v['pairs']} pairs for the comparison groups (setups sharing a
letter). A result from one set does not carry over to the other.</p>
<p>Astra scored {v['pair_astra_sol_difference']} points above Sol: of {v['method_pair_astra_sol_split']} questions only one
got right, Astra had {v['pair_astra_sol_first_only']} and Sol {v['pair_astra_sol_second_only']}. The adjusted p was
{v['pair_astra_sol_p_holm']} among the selected comparisons and {v['pair_astra_sol_p_holm_all']} across all pairs, below and
above {v['method_alpha']}. A p value says how unusual so uneven a split would be at equal accuracy, not the chance that the
models are equal.</p>
<p>DeepSeek with reasoning scored {v['pair_deepseek_on_opus_difference']} points above Opus with low reasoning (adjusted p
{v['pair_deepseek_on_opus_p_holm']}). Not establishing a difference does not show equal accuracy: many language comparisons
have too few questions to detect gaps this small.{cite(18)}</p>
{paired_figure}"""),
        ("statistical-methods", "How we measure uncertainty", f"""
<p>A result from one question set is an estimate. For the ranking score and the accuracy of kept answers, we draw
{v['method_bootstrap']} bootstrap samples of the questions with replacement, keeping the {v['method_passage_questions']}
questions of {v['method_passages']} shared passages together. For small groups, such as answers at {v['threshold']} or
more, a Wilson interval gives an error rate above zero even with no mistakes. A 95% interval comes from a method that covers
the true value in about 95% of repeated studies, under its assumptions; it is not a model's confidence.</p>
<p>The live tests report their comparisons without Holm's adjustment. Replays with a cutoff chosen on half the questions
average {v['method_splits']} random splits of this one question set, not new question sets.</p>"""),
        ("routing", "How we chose which answers to keep", f"""
<p>A cheap model answers first; we keep its answer when its confidence reaches a cutoff, and a stronger model answers the
rest. FrugalGPT{cite(5)} and RouteLLM{cite(6)} study related routing. We count the first model's cost on every question.</p>
<p>Three rules set the cutoff. The cutoff chosen on half the questions is chosen on one random half (a passage's questions
together) and tested on the other, {v['method_splits']} times. The most confident quarter keeps the first model's
{v['surest_rule']} surest answers, and the fixed {v['threshold']} rule every answer at {v['threshold']} or more.</p>
<p>These are replays of recorded answers, with no new calls. The accuracy change compares the combined answers with the
second model alone on the same questions. The estimated cost adds both models' calls, without the hardware of a first
model we ran ourselves.</p>
<div class="caveat" id="average-cost">
<h3>The average-cost caveat</h3>
<p>Replay savings give every question passed to the second model the same average cost. In the live tests, the passed
questions cost more, so the savings were smaller in {smaller} of {live_total} tests.</p>
</div>
<p>In the live tests, the second model answered the passed questions with new calls, on one split of
{bp.count(held_out)} questions, and separately answered all of them alone. One split checks the replay; it cannot replace
the average over {v['study_splits']}.</p>
<p>The second model changes the result: in front of Claude Sonnet 5.5 at high reasoning, GLiDE answered
{v['route_glide_sonnet_high_share']} of the questions and Gemma {v['route_gemma_sonnet_high_share']}. The best pair depends
on the task and the loss you accept.</p>
<p>Does a decision model's uncertainty (entropy over its option scores) point to the questions a stronger model gets wrong?
Weakly: its most uncertain {v['study_doubt_random']} of questions held {v['study_doubt_found']} of those where Opus, Sonnet or
Astra erred, against about {v['study_doubt_random']} by chance.</p>"""),
        ("cost-section", "Cost and reasoning", f"""
<p>We report output tokens, total run time and money separately. Services charge by tokens, but token counts of different
models do not stand for equal computation.</p>
<h3 id="reasoning">What changes when a model does more reasoning?</h3>
{bp.reasoning_table(snap)}
<p>Reasoning helped grammar much more than reading. In all four pairs we tested, the grammar gain was larger, and every 95%
interval of the difference is above 0. Claude Sonnet 5.5, low to high reasoning: +32.7 points on grammar, +2.3 on reading.
For DeepSeek and GLM, turning on reasoning also turns on random sampling, so those pairs mix two changes.</p>
{pairs_table(pairs)}
<p class="table-note">Each interval is a paired bootstrap over the scored questions ({site.results['reasoning']['resamples']:,}
resamples, each shared passage's questions kept together). The {results_file} holds them, and <code>reproduce.py</code>
recomputes them.</p>
<p>Short output can go with high accuracy: GPT-6 Astra reached {v['astra_accuracy']} with about {v['astra_tokens']} output
tokens per question, and GPT-6.1 Sol {v['sol_accuracy']} with {v['sol_tokens']}. Other research finds that more computation
while answering helps on some problems;{cite(7)} we show it only for these settings.</p>
<h3 id="cost-estimates">How we estimate the money cost</h3>
<p>We multiply each run's recorded tokens by published prices, in US dollars per 1,000 questions asked, including the
{v['study_excluded']} questions later removed. We use the token counts services reported, without checking invoices; GPT and
Claude ran on subscriptions, so we price the same use at API rates. Rates for new, reused and stored input apply
separately.</p>
<p>Most rates date from {v['study_price_date']}. Perplexity's price changed between its two Decider runs, so their cost
difference is not only a model improvement. Gemini 3.8 Flash's price is introductory: it
{v['study_price_gemini_low_change']}.</p>
<p>Models on our own GPUs get no dollar estimate, which does not make them free. Liquid's d1 used a free tier, so its replay
counts d1's charge as zero. Fixed output token charges of some decision services follow pricing rules, not written
reasoning.</p>
{price_list(snap)}"""),
        ("understanding", "What can these results tell us about understanding?", f"""
<p>A model may answer a passage question correctly and miss a grammar rule in the same language: performance changes by task,
which does not settle whether it understands. These tests measure skills models have, not how fast they learn; Mitchell and
Krakauer discuss meanings of understanding,{cite(1)} and Chollet separates a skill from the ability to learn new
ones.{cite(2)}</p>
<p>Reading may draw on patterns shared across languages, and school grammar more on local rules; training, difficulty and
format could also explain the gap. Confidence changes too: Jev's ranking score fell from {v['method_jev_auroc_reading']} on
Reading to {v['method_jev_auroc_grammar']} on Grammar, and Open Jev's from {v['method_open_jev_auroc_reading']} to
{v['method_open_jev_auroc_grammar']}. An <a href="https://arize.com/blog/jev-llm-judge-consistency/">Arize evaluation</a>
reports a stronger score for Jev on two-label English tasks, a different test.</p>
<p>Stronger evidence would change a question's words but not the relationship the answer depends on, then change that
relationship and check the answer follows (CheckList{cite(9)}; McCoy, Pavlick and Linzen{cite(14)}). Teaching an unfamiliar
rule would test learning directly. Other work looks inside models{cite(15)} or tests generalisation across wording and
reasoning problems.{cite(16)}</p>"""),
        ("repeats-section", "What changed when we repeated the same questions?", f"""
<p>We ran {v['repeated_whole_bank']} of the {v['one_question_configs']} one-question-per-request setups
{v['method_repeat_times']} times on all {v['questions']} questions, and {v['repeated_sample']} of the
{v['batched_configs']} setups with {v['batch_size']} per request {v['method_repeat_times']} times on a fixed
{v['sample_questions']}-question set.</p>
<p>On all questions, Open Jev changed {v['method_open_jev_changed_text']}, Decider v1 {v['method_decider_v1_changed_text']}
and SubQ Snap {v['method_subq_changed_text']}; Jev changed about {v['jev_changed_share']}, d1 {v['d1_changed_share']},
Celeris 1 {v['celeris_changed_share']}, Qwen's yes or no scoring {v['qwen_yes_no_changed_share']} and Qwen with written
confidence {v['qwen_stated_changed']} answers ({v['qwen_stated_changed_share']}). On the {v['sample_questions']}-question
set, Astra changed {v['method_sample_astra_changed']}, Opus {v['method_sample_opus_changed']} and Sonnet with high reasoning
{v['method_sample_sonnet_high_changed']}. A model can repeat the same wrong answer, so stability alone proves little.</p>
<p>Gemma's stored repeats, in one server session, changed {v['method_sample_gemma_changed']}; an unsaved rerun after a
restart changed some. The Gemma and DeepSeek repeats have no confidence scores.</p>"""),
        ("latency", "How we measure latency and throughput", f"""
<p>Latency is the time from sending one request to receiving its answer, measured from our computer, network and retries
included; a request holds one question or {v['batch_size']}. Throughput is answered questions per minute of active request
time, overlaps counted once. Total run time is the whole run.</p>
{timing}
<p>Astra's typical latency is {v['astra_median']} seconds for {v['batch_size']} questions (from the
{v['sample_questions']}-question repeats) and {v['astra_single_median']} for one; Gemma's is {v['gemma_median']} and
{v['gemma_single_median']} seconds.</p>"""),
        ("limits", "What these results do not establish", f"""
<p>The questions are online, so models may have seen them in training (contamination, which few tests measure{cite(19)});
turning off web access cannot undo that. On the {v['method_exam_questions']} Turkish questions of Turkey's June 2026
university entrance exam, public before our October test, {v['method_exam_models']} models got {v['method_exam_lowest']} to
{v['method_exam_highest']} right.</p>
<p>When we replaced the correct option's text with a copy of a wrong one, Astra chose the original letter
{v['method_copy_original']} of the time and the copy {v['method_copy_copy']}, with no established preference (p =
{v['method_copy_p']}). That checks one form of recall, not whether the model knew the question.</p>
<p>Reasoning, sampling, request size, precision, server software and server state can change answers. This is one language
and one question source; a confidence cutoff for a new task needs its own test.</p>"""),
        ("data", "Download the data and check our calculations", f"""
<p class="versions">Results updated {v['results_updated']} · Results snapshot {v['results_version']} · Question set
{v['dataset_version']} · Answer key {v['key_version']}</p>
<p>The {results_file} holds the summary numbers; the {answer_file} holds the recorded choices, confidence scores, settings,
prompt templates and question IDs, without the copyrighted questions. The
<a href="{REPO_URL}/blob/main/decision-models/benchmark_metrics.py">metric code</a> computes each statistic; the
{link('data/', 'Data page')} describes the files.</p>
<p>This snapshot holds {v['configs']} main setups, {v['repeat_runs']} extra repeat runs, {v['method_live_runs']} runs from
the {v['method_live_tests']} live tests, {v['method_alone_runs']} cheaper models tested alone and
{v['method_single_runs']} more runs with one question per request on {v['method_single_questions']} questions.</p>
<p>From the <a href="{REPO_URL}/tree/main/decision-models">repository</a>, <code>reproduce.py</code> recomputes every main
setup's accuracy, ranking score, calibration gap and answers at {v['threshold']} or more (before and after the key review),
the {v['comparisons']} selected comparisons, comparison groups, request format comparisons, reasoning pairs, repeats, prices,
replays with their {v['method_splits']} splits and live tests: all {v['checks']} checks match. It does not yet check the
bootstrap intervals of the ranking score and the accuracy of kept answers.</p>
<p>The {v['method_exam_questions']} exam questions stay private, and the raw replies behind token counts are not exported.
The <code>runner</code> folder holds the test code, run scripts and server wrappers.</p>"""),
    ]
    example = f"""
<aside class="worked-example" aria-labelledby="worked-example-title">
<h2 id="worked-example-title">Worked example: Decider v1.1</h2>
<p>Perplexity's Decider v1.1 is a decision model; this box follows it through the two-step setup. Its typical latency was
{v['decider_v11_median']} seconds, at {v['decider_v11_cost']} per 1,000 questions, against {v['opus_cost']} for Claude Opus
5.5 alone.</p>
<p>At {v['threshold']}, it kept {v['cut_99_kept']} answers with {v['cut_99_wrong']} wrong (error rate interval
{v['decider_v11_error_span']}), and none of the {v['method_suspect']} uncertain questions reached that confidence. Its most
confident quarter held {v['surest_correct']} right answers of {v['surest_kept']}.</p>
<p>The table replays recorded answers, Decider v1.1 first and each LLM second. With one question per request, no cutoff
chosen on half the questions loses more than the {limit:g}-point limit set before the live tests.</p>
{bp.savings_table(snap)}
<p>In the live tests, the loss exceeded that limit in {v['study_live_beyond']}, and in {v['study_live_open']} the 95%
interval allows a larger loss. {v['study_live_established']} Live savings were smaller (see
<a href="#average-cost">the average-cost caveat</a>).</p>
<p>Across {v['study_repeats']} full runs it changed {v['decider_v11_changed']} answers, yet repeated the same wrong answer on
{v['decider_v11_same_wrong']} of the {v['decider_v11_wrong_any']} questions it ever missed. Its ranking score was
{v['decider_v11_auroc']}. Fastino's GLiDE scored {v['glide_accuracy']} against its {v['decider_v11_accuracy']}, a
difference not established, at about {v['study_glide_times']} times its cost for the first model's calls.</p>
<p>It scored {v['pair_decider_v11_decider_v1_difference']} points above
<a href="https://docs.sglang.io/cookbook/autoregressive/Perplexity/pplx-decider-v1-27b">Decider v1</a>, which shares a Qwen
base with <a href="https://blog.cloudflare.com/clef-decision-models/">Clef</a> and
<a href="https://huggingface.co/ZefanCai/Open-Jev-27B-v1.1">Open Jev</a>.
<a href="https://huggingface.co/perplexity-ai/pplx-decider-v1.1-27b">v1.1</a> changed both training data and input handling,
so the test cannot say which change helped.</p>
</aside>"""
    toc = "".join(f'<li><a href="#{anchor}">{esc(title)}</a></li>' for anchor, title, _ in sections)
    cards = "".join(
        f'<section class="card prose" id="{anchor}" aria-labelledby="{anchor}-title"><h2 id="{anchor}-title">{esc(title)}</h2>{body}\n</section>\n'
        for anchor, title, body in sections
    )
    references = (f'<section class="card prose" id="references" aria-labelledby="references-title"><h2 id="references-title">'
                  f'Sources and related research</h2><p>These sources explain the methods and the earlier research above; our '
                  f'measurements come from the recorded runs.</p>{cite.references()}</section>')
    body = f"""<div class="method-page">
<header class="v2-hero">
<p class="kicker">Method</p>
<h1>How we tested confidence, cost and accuracy</h1>
<p class="intro">We tested {v['models']} models in {v['configs']} setups on a reading comprehension and grammar test in native Turkish
(not translated): {v['questions']} questions. A setup is one model with one set of settings. We measured four things: how often
each was right, whether its confidence found the answers worth keeping, whether it answered the same way again, and its
cost and time.</p>
<nav class="toc" aria-label="Sections of this page"><ul>{toc}<li><a href="#references">Sources</a></li></ul></nav>
</header>
{example}
{cards}{references}
</div>"""
    return {PATH: site.page(PATH, TITLE, DESCRIPTION, body)}
