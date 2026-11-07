"""The Method page (method/): how we ran the test, the request format check, the full study and its limits.

Its numbers come from results.json through build_page.py's Snapshot (site.snapshot; the values the earlier page, v1/,
showed), from page_config.json's method_records, and from answers.json where results.json holds no count; its charts
come from charts/. One table is new: the reasoning pairs' gains on Reading and Grammar with the 95% interval of their
difference, from results.json's reasoning. Build checks raise ValueError when the copy no longer fits the data.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

import benchmark_metrics as bm
import build_page as bp
from sitebuild.site import MENU, REPO_URL, ROOT, VIEW_GROUPS, VIEW_MEASURES, VIEW_TESTS, Site, esc, rel

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
    "TypeSafe's hosted decision model, versions 1.13 and 1.14; Open Jev compares with 1.13.",
    "Perplexity's Decisions API (three versions) and Liquid's API (d1, d1-ultra and d1.1); d1 ran on the free tier, its cost "
    "estimated at Liquid's list price.",
    "Cloudflare's model, on our hardware: it adapts Qwen 3.8 27B and scores all options in one pass.",
    "Cloudflare's smaller model: Qwen 3.5 9B, with Clef's scoring method and release code.",
    "It adapts Qwen 3.5 4B and lists Turkish among its training languages.",
    "blockbrain-ai's recipe on an unchanged Gemma 4 12B IT, served by vLLM: answer letter probabilities rescaled with a "
    "temperature of 3.4.",
    "Gemma 4 12B IT trained for decisions, published only as GGUF files: the recommended Q8_0 file (eight bits per weight) "
    "on its author's llama.cpp-based server.",
    "Fastino's System One API. GLiDE reasons more on uncertain cases, which we could not switch off.",
    "Celeris's System One API: probabilities rounded to whole points, no model size or design published.",
    "SubQ's Decisions API, in public preview, with no model size or design published; Snap 1.1's 32-bit probabilities "
    "passed our check within 32-bit rounding, an experimental rule of ours.",
    "meraGPT's System One API: its own model, with no size or design published; the name serves meraGPT's current "
    "version, here the one of 19 October 2026.",
    "Microsoft's and Inception's decision models via OpenRouter's System One route (paid); request times include OpenRouter's.",
    "Perplexity's released v1.2 checkpoints, run on our hardware: additional local setups; v1.2 also ran through the API.",
    "Fastino's released v1.2 checkpoint on our hardware, with the server it ships: one pass per question, nothing "
    "generated. The hosted GLiDE gave the same answers on 20 sample questions on 22 October; the other GLiDE row is the "
    "hosted model of 6 October.",
    "The vLLM Semantic Router's released checkpoint on our hardware, served by a vLLM nightly through its System One "
    "endpoint (with --max-num-seqs 256, as the default did not fit the GPU at start-up).",
    "The vLLM Semantic Router's released d3-ultra checkpoint on our hardware, through the server its repository ships "
    "(its own Transformers runtime): vLLM does not serve it yet.",
    "OmniJev's released checkpoint on our hardware, through the server its package ships, with its default settings.",
    "Nace.AI's hosted Drex Max 1.1 and Drex 2.0, and its released Drex Max v1 on our hardware through Nace's own loader; "
    "Drex Max 1.1 and v1 are different checkpoints.",
    "Liquid AI's released d1-2B on our hardware, through its model card's own call; Turkish is not among the languages "
    "Liquid lists for it.",
    "Base Labs' released elephant-1 and mammoth-1 on our hardware, through their model cards' loader, text only; their "
    "cards list English only.",
    "REAX's released REAX 1.3 on our hardware in FP8, through the maker's own engine: the 50/50 mean of two parts' "
    "option probabilities (Gemma and Qwen lines), text only; its card lists English only.",
    "Amazon's released model: an adapter and a scoring part on Qwen 3.5 2B Base, with its own server.",
    "Both released models, on our hardware; each scores all options in one pass.",
    "Fastino's {size} parameter text classifier, scoring the options as labels: a much smaller baseline.",
    "The same {size} parameter model, trained by Fastino for decisions.",
    "The released open model, with its own scoring part and calibration setting.",
    "Open Jev's base model and prompts without its trained parts: the preference for Yes over No, with a calibration "
    "temperature of 1.",
    "The base model chooses an option and writes its confidence.",
    "Ten sampled answers: the most common one, with the share that agrees as confidence.",
    "Chat models for comparison; each writes a confidence estimate. Several ran at more than one reasoning setting.",
    "OpenAI's Decisions API, in beta, {per_request} question per request. The other Luna run writes its confidence "
    "through Codex, {other_per_request} questions per request.",
    "On our hardware, with answer letter probabilities. The DeepSeek and Qwen reasoning runs also sample.",
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
    ("Platt, J. (1999). Probabilistic Outputs for Support Vector Machines and Comparisons to Regularized Likelihood "
     "Methods. In Advances in Large Margin Classifiers, MIT Press.", "https://doi.org/10.7551/mitpress/1113.003.0008"),
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
    """A figure as build_page.py writes it (links to charts/…), linked from this page to charts/."""
    charts = rel(PATH, "charts/")
    return figure.replace('href="charts/', f'href="{charts}').replace('src="charts/', f'src="{charts}')


def chart(name: str, alt: str, caption: str) -> str:
    """A chart from charts/ in both themes, sized from its SVG."""
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


def refit_table(site: Site, snap: bp.Snapshot) -> str:
    """Calibration after the refit for every setup with a confidence score, by Better than a flat guess, highest first:
    the calibration gap as shipped and after the refit, both Brier scores and Better than a flat guess. The page shows the
    gap after refit here only."""
    heads = ("Setup", "Calibration gap (points)", "Gap after refit (points)", "Brier after refit", "Brier of the flat guess",
             "Better than a flat guess (%)")
    rows = []
    scored = sorted((run for run in snap.runs if run.get("confidence")), key=lambda run: -bp.flat_gain(run))
    shown = site.names(scored)
    for run in scored:
        confidence = run["confidence"]
        settings = site.detail(run)
        tip = f' title="{esc(settings)}"' if settings else ""
        gain = f"{bp.flat_gain(run):.1f}" + ('<span class="small">reversed</span>' if bp.reversed_refit(run) else "")
        cells = (f"{100 * confidence['ece']:.1f}", f"{100 * confidence['ece_refit']:.1f}", f"{confidence['brier_refit']:.3f}",
                 f"{confidence['brier_base']:.3f}", gain)
        rows.append(
            f'<tr><td data-label="{heads[0]}"{tip}><a href="{rel(PATH, site.model_path(run))}">{esc(shown[run["run"]])}</a></td>'
            + "".join(f'<td class="num" data-label="{head}">{cell}</td>' for head, cell in zip(heads[1:], cells)) + "</tr>"
        )
    head = "".join(f'<th scope="col"{"" if index == 0 else " class=\"num\""}>{text}</th>' for index, text in enumerate(heads))
    return (f'<div class="table-wrap"><table class="overview cards"><caption>Calibration before and after the refit, every '
            f'setup, by Better than a flat guess, highest first</caption><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


# The three questions the Calibration section separates: what each asks, its column and which direction is better.
CALIBRATION_QUESTIONS = (
    ("Does the confidence put right answers above wrong ones?", "Ranking score", "Higher"),
    ("Do the probabilities match the hit rate, as shipped?", "Calibration gap", "Lower"),
    ("After a refit, do the probabilities beat one fixed probability for every answer?", "Better than a flat guess", "Higher"),
)


def calibration_questions() -> str:
    heads = ("Question", "Column", "Better")
    rows = "".join(
        "<tr>" + "".join(f'<td data-label="{head}">{esc(text)}</td>' for head, text in zip(heads, row)) + "</tr>"
        for row in CALIBRATION_QUESTIONS
    )
    head = "".join(f'<th scope="col">{text}</th>' for text in heads)
    return f'<div class="table-wrap"><table class="overview cards"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'


def share_text(value: float) -> str:
    """A share in percent with one decimal, and 100% without one."""
    text = f"{100 * value:.1f}"
    return "100%" if text == "100.0" else f"{text}%"


def refit_example(site: Site, snap: bp.Snapshot) -> dict[str, str]:
    """The worked refit: Open-Jev 27B v1.1 fitted on all its scored answers with a score (bm.platt_fit, as each fold is
    fitted), its ranking score, stretch and shift, a table of its answers by raw score band (answers, average raw score,
    average after the refit, share right), and from results.json the range of its five held-out stretches and its
    calibration gap before and after the refit. The build stops unless its probabilities were too low in every band and
    the bands hold every answer, as the text says."""
    run = snap.named["open_jev"]
    answer = next(item for item in site.answers["runs"] if item["run"] == run["run"])
    pairs = [(float(answer["score"][index]), int(answer["correct"][index])) for index in site.scored if answer["score"][index] is not None]
    clipped = [min(max(score, bm.REFIT_SCORE_CLIP), 1 - bm.REFIT_SCORE_CLIP) for score, _ in pairs]
    features = [math.log(value / (1 - value)) for value in clipped]
    stretch, shift, converged = bm.platt_fit(features, [correct for _, correct in pairs])
    if not converged or stretch <= 0:
        raise ValueError("the refit example needs Open-Jev's fit on all questions to converge with a positive stretch")
    bands: dict[int, list[tuple[float, int, float]]] = {}
    for (score, correct), feature in zip(pairs, features):
        bands.setdefault(min(int(10 * score), 9), []).append((score, correct, bm.sigmoid(stretch * feature + shift)))
    heads = ("Raw score", "Answers", "Raw average", "Average after refit", "Actually right")
    rows = []
    for band, members in sorted(bands.items()):
        raw, right = sum(item[0] for item in members) / len(members), sum(item[1] for item in members) / len(members)
        if raw >= right:
            raise ValueError("the refit example says Open-Jev's probabilities were too low in every band")
        cells = (f"{10 * band}–{10 * band + 10}%", bp.count(len(members)), share_text(raw),
                 share_text(sum(item[2] for item in members) / len(members)), share_text(right))
        rows.append("<tr>" + "".join(f'<td{"" if index == 0 else " class=\"num\""} data-label="{head}">{cell}</td>'
                                     for index, (head, cell) in enumerate(zip(heads, cells))) + "</tr>")
    if sum(len(members) for members in bands.values()) != run["confidence"]["refit_questions"]:
        raise ValueError("the refit example's bands must hold every answer the refit used")
    slopes = [slope for slope in run["confidence"]["refit_slopes"] if slope is not None]
    head = "".join(f'<th scope="col"{"" if index == 0 else " class=\"num\""}>{text}</th>' for index, text in enumerate(heads))
    return {
        "auroc": f"{run['confidence']['auroc']:.2f}",
        "stretch": f"{stretch:.2f}",
        "shift": f"{shift:.2f}",
        "table": f'<div class="table-wrap"><table class="overview cards"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>',
        "fold_low": f"{min(slopes):.2f}",
        "fold_high": f"{max(slopes):.2f}",
        "gap": f"{100 * run['confidence']['ece']:.1f}",
        "gap_after": f"{100 * run['confidence']['ece_refit']:.1f}",
    }


def flat_guess_examples(snap: bp.Snapshot) -> dict[str, str]:
    """The numbers the paragraph on high accuracy cites: GPT-6 Astra (its first setup) and Gemini 3.8 Flash at high
    reasoning, each one's settings (reasoning and questions per request), accuracy and Better than a flat guess, and
    Gemini's wrong answers out of the questions its refit used. The build stops unless Gemini is the more accurate and
    Astra scores higher, as the paragraph says."""
    total = snap.results["questions"]
    astra, gemini = snap.named["astra"], snap.named["gemini_high"]
    if (astra["name"], gemini["name"]) != ("GPT-6 Astra", "Gemini 3.8 Flash"):
        raise ValueError("the paragraph on high accuracy names GPT-6 Astra and Gemini 3.8 Flash")

    def setting(run: dict[str, Any]) -> str:
        size = run["questions_per_request"]
        parts = [bp.reasoning_label(run["reasoning"])] if run.get("reasoning") else []
        return ", ".join([*parts, f"{bp.count(size)} question{'' if size == 1 else 's'} per request"])

    if not (gemini["correct"] > astra["correct"] and bp.flat_gain(astra) > bp.flat_gain(gemini)):
        raise ValueError("the paragraph on high accuracy says Gemini 3.8 Flash is the more accurate and GPT-6 Astra scores higher")
    if gemini["confidence"]["refit_questions"] != total:
        raise ValueError("the paragraph on high accuracy counts Gemini's wrong answers out of every question")
    return {
        "astra_setting": setting(astra),
        "astra_accuracy": f"{100 * astra['correct'] / total:.1f}",
        "astra_gain": f"{bp.flat_gain(astra):.1f}",
        "gemini_setting": setting(gemini),
        "gemini_accuracy": f"{100 * gemini['correct'] / total:.1f}",
        "gemini_gain": f"{bp.flat_gain(gemini):.1f}",
        "gemini_wrong": bp.count(total - gemini["correct"]),
        "questions": bp.count(total),
    }


def display_name(run: dict[str, Any], runs: list[dict[str, Any]]) -> str:
    """A setup's name with its format and, where it tells it apart from another run of the same model ID, its variant (a
    route or access note; one of a model with one run stays on its model page)."""
    variant = run.get("variant") if any(other["run"] != run["run"] and other["model"] == run["model"] for other in runs) else None
    details = [item for item in (variant, run.get("format")) if item]
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
        return ", ".join(dict.fromkeys(display_name(run, snap.runs) for run in runs))

    items = []
    tokens = [price for price in snap.results["prices"] if price["applies_to"] != "gpu"]
    if any(part.startswith(("reused", "saving")) for price in tokens for part in rate_parts(price)):
        items.append(esc(REUSE_EXPLAINED))
    for price in snap.results["prices"]:
        runs = [run for run in snap.runs if run["provider"] == price["provider"] and run["model"] == price["model"]]
        change = f" Provider update: {esc(price['change'])}." if price.get("change") else ""
        extra = price.get("extra_input_per_request") or 0
        billed = f" Billed input: {extra} tokens per request more than our count, which we add." if extra else ""
        rates = (f"GPU time: {price['text']}" if price["applies_to"] == "gpu"
                 else f"Per one million tokens: {'; '.join(rate_parts(price))}")
        items.append(f"{esc(names(runs) or price['model'])}. Prices recorded {bp.long_date(price['date'])}. "
                     f"{esc(rates)}. Source: "
                     f'<a href="{esc(price["source"])}">{esc(price["basis"])}</a>.{change}{esc(billed)}')
    free = [run for run in snap.runs if run["billing"] == "free" and run["api_equivalent_usd"] is None]
    local = [run for run in snap.runs if run["billing"] == "local" and run["api_equivalent_usd"] is None]
    if free:
        items.append(esc(f"{names(free)}. {FREE_RATE}"))
    if local:
        items.append(esc(f"{names(local)}. {NO_COST_LOCAL}."))
    return '<ul class="footnote price-list">' + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def maker_priced(snap: bp.Snapshot) -> str:
    """The setups on our hardware estimated at their maker's list price for the same model, by maker ("Perplexity for A
    and B; Cloudflare for C"), then the makers that bill input tokens per request beyond our count."""
    prices = {bp.price_key(price): price for price in snap.results["prices"]}
    makers: dict[str, list[str]] = {}
    extra: dict[str, int] = {}
    for run in snap.runs:
        if run.get("cost_basis") != "maker":
            continue
        price = prices[bp.price_key(run)]
        maker = price["basis"].split("'s list price for the same model")[0]
        makers.setdefault(maker, [])
        if run["name"] not in makers[maker]:
            makers[maker].append(run["name"])
        if price.get("extra_input_per_request"):
            extra[maker] = price["extra_input_per_request"]
    groups = [f"{maker} for {bp.and_list(names)}" for maker, names in makers.items()]
    listed = groups[0] if len(groups) == 1 else "; ".join(groups[:-1]) + "; and " + groups[-1]
    billed = "".join(f" {maker} bills {count} input tokens per request more than our servers count, so we add them." for maker, count in extra.items())
    return f"{listed}.{billed}"


def local_estimates(snap: bp.Snapshot) -> str:
    """The setups on our hardware estimated at a public host's list price for the same weights, then those estimated
    from GPU time (first_cost_marks' gpu tip), each named, or nothing where there are none."""
    named = {basis: list(dict.fromkeys(run["name"] for run in snap.runs if run.get("cost_basis") == basis))
             for basis in ("weights", "gpu")}
    text = ""
    if named["weights"]:
        text += (" Where only another public host serves the same weights, we use its list price, with any precision "
                 f"difference in the price's name: {bp.and_list(named['weights'])}.")
    if named["gpu"]:
        text += f" Otherwise ({bp.and_list(named['gpu'])}): {snap.config['first_cost_marks']['gpu']['tip']}"
    return text


def gemma_lead(snap: bp.Snapshot) -> str:
    """What we found says Gemma 4 31B, a chat model, scored higher than every decision model on Reading and on Grammar
    except the ones it names, which scored higher than Gemma on both, and that its confidence matched its hit rate less
    closely than the best decision models' did; returns those decision models' short names, and the build stops when a
    part no longer holds."""
    decision = [run for run in snap.runs if snap.decision_model(run)]
    gemma = snap.named["gemma"]
    groups = ("reading", "grammar")
    ahead = [run for run in decision if all(bp.study_share(snap, run, group) > bp.study_share(snap, gemma, group)
                                            for group in groups)]
    if not ahead:
        raise ValueError("What we found names the decision models ahead of Gemma; there are none")
    for group in groups:
        share = bp.study_share(snap, gemma, group)
        if any(bp.study_share(snap, run, group) >= share for run in decision if run not in ahead):
            raise ValueError(f"What we found says Gemma beats every other decision model on {group}; it does not")
    if gemma["confidence"]["ece"] <= min(run["confidence"]["ece"] for run in decision):
        raise ValueError("What we found says Gemma's confidence matched its hit rate less closely than the best decision models'")
    return bp.and_list([run["name"].removeprefix("Liquid ") for run in ahead])


def and_list(items: tuple[tuple[str, str], ...]) -> str:
    """The labels of a navigation list (path or value, label), as "a, b and c"."""
    return esc(bp.and_list([label for _, label in items]))


def glance(site: Site) -> str:
    """At a glance, as Artificial Analysis's methodology page opens: the tests in one table, how the site is laid out
    (the view bar's rows and the top links, from sitebuild/site.py), how the models are asked, and for three tests short items (what it measures, its questions, how it is scored, where the details are);
    every count from results.json and vision.json. The long sections below are the details."""
    v = site.values
    subset = site.vision["subset"]
    dont_know = site.results["dont_know"]
    option = esc(dont_know["option"])
    english = site.results["english_reading"]["questions"]
    pws = json.loads((ROOT / "pws-decisions.json").read_text(encoding="utf-8"))
    table_rows = (
        ("", "Turkish reading and grammar", v["questions"], "Reading comprehension and grammar, in native Turkish", "Accuracy: right answers over the questions"),
        ("english/", "English reading", f"{english:,}", "The Turkish test's kept reading questions, translated into English",
         "Accuracy in English"),
        ("turkish-vs-english/", "English and Turkish", f"{english:,}", "The same setups on the same reading questions in both languages",
         "The change in accuracy from Turkish to English"),
        ("vision/", "Page images", f"{subset['questions']:,}",
         "Questions that point at underlined or numbered words: from the text (A), a picture of the page (B), both (C) or an OCR model's reading (D)",
         "Accuracy in each condition"),
        ("dont-know/", "Hallucination", f"{dont_know['questions']:,}", f"The Turkish test's questions with a sixth option, “{dont_know['option']}” (I don't know)",
         f"Non-hallucination rate: “{dont_know['option']}” over “{dont_know['option']}” plus wrong answers"),
        ("web-grounding/", "Web grounding", v["questions"], "One model with web search off and on",
         "Accuracy, non-hallucination, latency and cost, off against on"),
        ("pws-decisions/", "PWS-Decisions", f"{pws['questions']:,}", "Parallel Web Systems' benchmark of dated web facts, asked of the decision models",
         "Accuracy over three runs per setup; not part of the Turkish ranking"),
    )
    rows = "".join(
        f'<tr><td data-label="Benchmark"><a href="{rel(PATH, path)}">{esc(name)}</a></td><td class="num" data-label="Questions">{esc(count)}</td>'
        f'<td data-label="What it measures">{esc(what)}</td><td data-label="Main measure">{esc(measure)}</td></tr>'
        for path, name, count, what, measure in table_rows)
    return f"""<section class="card prose" id="at-a-glance" aria-labelledby="at-a-glance-title">
<h2 id="at-a-glance-title">At a glance</h2>
<p>Each test has its own page and its own ranking; no score combines them.</p>
<div class="table-wrap"><table class="board list stack"><thead><tr><th scope="col">Benchmark</th><th scope="col" class="num">Questions</th>
<th scope="col">What it measures</th><th scope="col">Main measure</th></tr></thead><tbody>{rows}</tbody></table></div>
<h3>How the site is laid out</h3>
<ul>
<li><strong>The view bar</strong>, under the top bar, has three rows. Test picks the page: {and_list(VIEW_TESTS)}. Models picks the group: {and_list(VIEW_GROUPS)}. Measure goes to a part of the page: {and_list(VIEW_MEASURES)}.</li>
<li><strong>The top links</strong> lead to {and_list(MENU)}. Page images and Hallucination are tests of their own, each ranked on its own page.</li>
<li><strong>Web grounding</strong>: <a href="{rel(PATH, 'web-grounding/')}">its page</a> is linked from the home page, both English pages and the Perplexity model pages.</li>
<li><strong>PWS-Decisions</strong>: <a href="{rel(PATH, 'pws-decisions/')}">its own page</a>, linked from the web grounding page, the home page and both English pages.</li>
</ul>
<h3>How we ask the models</h3>
<ul>
<li><strong>Decision models</strong>: each question goes to the model with its lettered options; we use only its pick and its score for each option (<a href="#setups">Models and setups</a>).</li>
<li><strong>Chat models</strong>: asked in Turkish for their answer's letter and, where needed, a confidence score, in a structured reply (<a href="#sending">What we sent</a>).</li>
</ul>
<h3>Turkish reading and grammar</h3>
<ul>
<li><strong>Measures</strong>: how often each setup was right, whether its confidence found the answers worth keeping, whether it answered the same way again, and its cost and time.</li>
<li><strong>Questions</strong>: {v['reading_questions']} Reading and {v['grammar_questions']} Grammar questions in {v['study_units']} topics, answer key {v['key_version']} (<a href="#tests">The questions</a>).</li>
<li><strong>Scoring</strong>: accuracy with its 95% interval; the ranking score and the calibration gap for confidence; cost per 1,000 questions at list prices; median latency per request (<a href="#measures">How we measure</a>).</li>
<li><strong>Details</strong>: the sections below.</li>
</ul>
<h3>Page images</h3>
<ul>
<li><strong>Questions</strong>: {subset['questions']:,} of the Turkish test's questions: {subset['by_reason']['underline']:,} at underlined words and {subset['by_reason']['numbered']:,} at numbered words.</li>
<li><strong>Scoring</strong>: accuracy in each condition over the {subset['questions']:,} questions; two conditions of a model compared with the exact McNemar test on the same questions.</li>
<li><strong>Details</strong>: <a href="{rel(PATH, 'vision/')}#method">How the benchmark was run</a>, on its page.</li>
</ul>
<h3>Hallucination</h3>
<ul>
<li><strong>Questions</strong>: the Turkish test's {dont_know['questions']:,} questions, each with “{option}” as option F, never correct, and one added sentence in the instructions.</li>
<li><strong>Scoring</strong>: accuracy, attempt rate and the non-hallucination rate; for comparison, the same model's five-option run held back by its own confidence at about the same attempt rate.</li>
<li><strong>Details</strong>: <a href="{rel(PATH, 'dont-know/')}#method">Our method</a>, on its page.</li>
</ul>
<h3>Version history</h3>
<p>Every results version and what changed: the <a href="{rel(PATH, 'data/')}#results-changelog">results changelog</a>; changes to the answer key: the <a href="{rel(PATH, 'data/')}#key-changelog">key changelog</a>.</p>
</section>"""


def build(site: Site) -> dict[str, str]:
    snap = site.snapshot
    v = site.values
    gemma_ahead = gemma_lead(snap)
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
    results_file = f'<a href="{rel(PATH, "results.json")}">results file</a>'
    answer_file = f'<a href="{rel(PATH, "answers.json")}">answer export</a>'
    calibration_alt = chart_alt(study["study-calibration"], "calibration-all")
    if "; the table keeps them." not in calibration_alt:
        raise ValueError("the calibration chart's description changed; check what it says about the table")
    calibration_alt = calibration_alt.replace("; the table keeps them.", ".")
    paired_figure = from_here(bp.chart_sizes(bp.method_paired_figure(snap)))
    refit = refit_example(site, snap)
    flat = flat_guess_examples(snap)
    if bm.REFIT_FOLDS != 5:
        raise ValueError("the Method page describes the refit's five parts")

    sections = [
        ("main-findings", "What we found", f"""
<p>No model led on every measure: accuracy, ranking answers by confidence and confidence that matches the hit rate are
separate strengths. Gemma 4 31B, a chat model, scored higher than every decision model except {esc(gemma_ahead)} on Reading
({v['gemma_reading']}) and Grammar ({v['gemma_grammar']}), but its confidence matched its hit rate less closely than the
best decision models' did.</p>
<p>How a model gives its confidence matters. GPT-6 Luna through OpenAI's Decisions API ranked its answers better than Luna
writing its confidence (ranking score {v['luna_api_auroc']} against {v['luna_stated_auroc']}) but got fewer right
({v['luna_api_accuracy']} against {v['luna_stated_accuracy']}), with a different access method and request size. Among
decision models, its calibration gap ({v['luna_api_ece_points']} points) was second only to Liquid d1.1's
({v['d1_1_ece_points']} points).</p>
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
so {v['grammar_share']} are Grammar. These results cover this question bank only. We did not test whether they hold in other
languages or for other tasks. Reading asks about the meaning of words, sentences and passages; Grammar asks about word
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
{v['method_audit_astra_before']} for Astra, {v['method_audit_jev_removed']} of {v['method_audit_jev_before']} for Jev 1.13 and
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
65,536-token output limit; DeepSeek's first release with reasoning had the same limit and left {v['deepseek_on_unanswered']}.</p>
<div class="table-wrap"><table class="settings"><thead><tr><th scope="col">Setup</th><th scope="col">How it chose each token</th></tr></thead><tbody>
<tr><td>Chat models on our hardware, reasoning off</td><td>Greedy decoding: the most likely next token</td></tr>
<tr><td>DeepSeek, reasoning on</td><td>Sampling, temperature 1.0, top p 1.0 (greedy decoding made its reasoning loop)</td></tr>
<tr><td>GLM 5.3 Flash, reasoning on</td><td>Server default: temperature 1.0, top p 0.95 (Z.ai's settings), top k 20; TensorFold's high reasoning</td></tr>
<tr><td>Qwen 3.8 27B, reasoning on</td><td>Server default: temperature 1.0, top p 0.95, top k 20 (Qwen's settings); the chat template's low reasoning effort</td></tr>
<tr><td>Qwen, ten answers</td><td>Temperature 0.7, top p 0.8, top k 20, presence penalty 1.5</td></tr>
<tr><td>Hosted chat models</td><td>The reasoning setting each setup names, in its provider's words; the provider's own sampling where temperature cannot be set, temperature 1.0 through OpenRouter; Gemini reported no reasoning tokens at low</td></tr>
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
<h3 id="calibration">Calibration</h3>
<p>Calibration means that a model's confidence matches how often its answers are right. When a calibrated model says 80%,
it is right about 80% of the time. Calibration matters when someone uses the number itself, for example to decide how
much to risk on an answer.</p>
<p>Calibration is separate from accuracy: a model can be right often and still give probabilities that are too high or too
low. It is also separate from ranking: a model can usually put right answers above wrong ones and still give
probabilities of the wrong size.</p>
{calibration_questions()}
<p>Calibration asks whether the percentages match the hit rate: of 100 answers scored near 80%, about 80 should be right.
The calibration gap (ECE){cite(11)} sorts answers into {v['study_confidence_groups']} confidence groups (0% to below 10%, and
so on) and compares each group's average confidence with its share right. It averages these gaps, weighting larger groups
more, in points. Zero means a match within the groups, not that every score is right; the chart leaves out groups with
fewer than {v['study_calibration_min']} answers.</p>
{chart("calibration-all", calibration_alt, CHARTS["calibration-all"])}
<h3 id="refit">What a refit is</h3>
<p>A refit changes the confidence scores, not the model's answers. The published ranking score still uses the original
scores.</p>
<p>The refit has three steps. Before the conversion, probabilities are clipped to between {bm.REFIT_SCORE_CLIP:.6f} and
{1 - bm.REFIT_SCORE_CLIP:.6f}. First, each confidence p becomes log-odds: ln(p / (1 − p)). Second, the new log-odds are a
stretch times the old log-odds, plus a shift. Third, the result becomes a probability again. This is Platt
scaling.{cite(21)} Logistic regression chooses the stretch and the shift. With a positive stretch, the refit keeps the order
of the scores it is applied to. With a negative stretch, it flips that order; these models are marked "reversed".</p>
<p>Example: Open-Jev 27B v1.1. Its confidence usually ranked right answers above wrong ones (ranking score
{refit['auroc']}), but its probabilities were too low. Fitted on all questions, its stretch is {refit['stretch']} and its
shift is {refit['shift']}. The table refits each answer, then averages within each band:</p>
{refit['table']}
<p>This table illustrates a fit on all questions. The published results come from a different calculation. We divide the
questions into five parts, keeping questions from the same passage together; each question without a shared passage
forms its own group. We fit on four parts and measure on the fifth, and rotate until each part has been measured once.
Each part has its own stretch and shift; for Open-Jev the stretch ranges from {refit['fold_low']} to {refit['fold_high']}.
On those held-out questions, Open-Jev's calibration gap falls from {refit['gap']} to {refit['gap_after']} points.</p>
<p>A refit cannot raise accuracy.</p>
<h3 id="flat-guess">Better than a flat guess</h3>
<p>Better than a flat guess compares two probability errors on those held-out questions (5 folds by passage). The Brier
score is the mean squared difference between a probability and the outcome (1 if right, 0 if wrong); lower is better.
The flat guess gives every answer the same probability: the model's accuracy on the questions used for fitting. Better
than a flat guess = 100 × (1 − Brier after refit ÷ Brier of the flat guess), so 0% means no improvement over the flat
guess and below 0% means worse. Every model uses the same five parts, and questions without a score are left out, as in
the calibration gap. Hamel Husain's <a href="https://hamel.dev/blog/posts/decision-model-evals/">post on decision
models</a> also found that calibration did not improve every model.</p>
<p>High accuracy does not by itself force this score to be low. The score measures how much the refitted probabilities
reduce Brier error compared with the model's own flat baseline. Example: GPT-6 Astra ({flat['astra_setting']}) is right
{flat['astra_accuracy']}% of the time and scores {flat['astra_gain']}%, while Gemini 3.8 Flash ({flat['gemini_setting']}) is
right {flat['gemini_accuracy']}% of the time and scores {flat['gemini_gain']}%. For models with few wrong answers, the score
rests on few cases (Gemini 3.8 Flash: {flat['gemini_wrong']} of {flat['questions']}), so it can vary more between test sets.
A score near 0% means this refit gave no improvement in this test. It does not prove that no method could make the
confidence useful.</p>
<details class="show-table"><summary>All calibration results</summary>
{refit_table(site, snap)}
</details>
<h3 id="sure">What a score of {v['threshold']} or more meant</h3>
<p>At {v['threshold']} or more, Jev 1.13 got {v['jev_correct']} of {v['jev_accepted']} right ({v['jev_skipped']} skipped), d1
{v['d1_correct']} of {v['d1_accepted']} ({v['d1_skipped']} skipped), Decider v1 {v['decider_v1_correct']} of
{v['decider_v1_accepted']} ({v['decider_v1_skipped']} skipped) and GLiDE {v['glide_correct']} of {v['glide_accepted']}
({v['glide_skipped']} skipped); Luna got {v['luna_api_correct']} of {v['luna_api_accepted']} through the Decisions API
({v['luna_api_skipped']} skipped) and {v['luna_stated_correct']} of {v['luna_stated_accepted']} writing its confidence
({v['luna_stated_skipped']} skipped). Few answers leave wide intervals: the 95%
interval for the error rate is {v['decider_v1_error_span']} for Decider v1 and {v['glide_error_span']} for GLiDE.</p>
<p>Gemma's letter probability reached {v['threshold']} on {v['study_gemma_sure_kept']} answers, {v['study_gemma_sure_correct']}
of them right (about {v['study_gemma_sure_accuracy']}), and fell short of it on {v['study_gemma_sure_skipped']}, which the
{v['threshold']} cutoff skips.
DeepSeek's first release with reasoning gave every answer at least {v['threshold']} ({v['study_deepseek_on_sure_kept']} kept,
{v['study_deepseek_on_sure_skipped']} skipped), and about {v['study_deepseek_on_sure_accuracy']} were right.</p>
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
<p>GPT-6 Astra with medium reasoning scored {v['pair_astra_medium_sol_difference']} points above GPT-6.1 Sol with low reasoning:
of {v['method_pair_astra_medium_sol_split']} questions only one got right, Astra had {v['pair_astra_medium_sol_first_only']} and Sol
{v['pair_astra_medium_sol_second_only']}. The p value was {v['pair_astra_medium_sol_p']} before adjustment; adjusted, it was
{v['pair_astra_medium_sol_p_holm']} among the selected comparisons and {v['pair_astra_medium_sol_p_holm_all']} across all pairs,
{v['method_pair_astra_medium_sol_relation']} {v['method_alpha']}. A p value says
how unusual so uneven a split would be at equal accuracy, not the chance that the models are equal.</p>
<p>DeepSeek-V4.1-Flash 1017 with reasoning scored {v['pair_deepseek_1017_on_terra_low_difference']} points above GPT-6.1 Terra with low reasoning
(adjusted p {v['pair_deepseek_1017_on_terra_low_p_holm']}). Not establishing a difference does not show equal accuracy: many
language comparisons have too few questions to detect gaps this small.{cite(18)}</p>
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
<p>We report output tokens, request time and money separately. Services charge by tokens, but token counts of different
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
<p>Most rates date from {v['study_price_date']}. Perplexity's price changed between its Decider v1 and v1.1 runs, so their cost
difference is not only a model improvement. Gemini 3.8 Flash's price is introductory: it
{v['study_price_gemini_low_change']}.</p>
<p>Every cost of a model on our own GPUs is an estimate, not measured spending. Where the model's maker lists a price for the
same model, the estimate uses it: {esc(maker_priced(snap))} Each is estimated at its maker's list price for the same model,
from our recorded tokens; our hardware cost is not measured.{esc(local_estimates(snap))} Liquid d1:
the run used the free tier (d1:free); its cost is now estimated at Liquid's list price for the same model. Fixed output
token charges of some decision services follow pricing rules, not written reasoning.</p>
{price_list(snap)}"""),
        ("understanding", "What can these results tell us about understanding?", f"""
<p>A model may answer a passage question correctly and miss a grammar rule in the same language: performance changes by task,
which does not settle whether it understands. These tests measure skills models have, not how fast they learn; Mitchell and
Krakauer discuss meanings of understanding,{cite(1)} and Chollet separates a skill from the ability to learn new
ones.{cite(2)}</p>
<p>Reading may draw on patterns shared across languages, and school grammar more on local rules; training, difficulty and
format could also explain the gap. Confidence changes too: Jev 1.13's ranking score fell from {v['method_jev_auroc_reading']} on
Reading to {v['method_jev_auroc_grammar']} on Grammar, and Open Jev's from {v['method_open_jev_auroc_reading']} to
{v['method_open_jev_auroc_grammar']}. An <a href="https://arize.com/blog/jev-llm-judge-consistency/">Arize evaluation</a>
reports a stronger score for Jev 1.13 on two-label English tasks, a different test.</p>
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
and SubQ Snap Preview {v['method_subq_changed_text']}; Jev 1.13 changed about {v['jev_changed_share']}, d1 {v['d1_changed_share']},
Celeris 1 {v['celeris_changed_share']}, Qwen's yes or no scoring {v['qwen_yes_no_changed_share']} and Qwen with written
confidence {v['qwen_stated_changed']} answers ({v['qwen_stated_changed_share']}). Decider v1.2 (local) changed
{v['method_decider_v12_changed_text']}, Decider Flash v1.2 (local) {v['method_decider_flash_v12_changed_text']}, Mercury Decide
about {v['mercury_decide_changed_share']} and Microsoft-Decision-1 about {v['microsoft_decision_1_changed_share']}. On the
{v['sample_questions']}-question
set, Astra changed {v['method_sample_astra_changed']}, Opus {v['method_sample_opus_changed']} and Sonnet with high reasoning
{v['method_sample_sonnet_high_changed']}. A model can repeat the same wrong answer, so stability alone proves little.</p>
<p>Gemma's stored repeats, in one server session, changed {v['method_sample_gemma_changed']}; an unsaved rerun after a
restart changed some. The Gemma and DeepSeek repeats have no confidence scores.</p>"""),
        ("latency", "How we measure latency and throughput", f"""
<p>Latency is the time from sending one request to receiving its answer, measured from our computer, network and any retries
within the request included; a request holds one question or {v['batch_size']}. Request time is the time at least one
request was in flight, over the requests whose answers were kept, overlaps counted once. It is not a run's elapsed time: it
leaves out requests that failed and any pause before a run was resumed. Throughput is answered questions per minute of
request time.</p>
{timing}
<p>Astra's typical latency is {v['astra_median']} seconds for {v['batch_size']} questions (from the
{v['sample_questions']}-question repeats) and {v['astra_single_median']} for one; Gemma's is {v['gemma_median']} and
{v['gemma_single_median']} seconds.</p>"""),
        ("limits", "What these results do not establish", f"""
<p>The questions are online, so models may have seen them in training (contamination, which few tests measure{cite(19)});
turning off web access cannot undo that. On the {v['method_exam_questions']} Turkish questions of Turkey's June 2026
university entrance exam, public before our October test, {v['method_exam_models']} models got {v['method_exam_lowest']} to
{v['method_exam_highest']} right. Of the five we added in October and checked this way, d1-ultra got
{v['method_exam_d1_ultra']}, Jev 1.14 {v['method_exam_jev_114']}, Decider v1.2 (local) {v['method_exam_decider_v12']},
Decider Flash v1.2 (local) {v['method_exam_decider_flash_v12']} and GLiDE v1.2 (local) {v['method_exam_glide_v12']}. These
{v['method_exam_questions']} questions are a separate check, not part of the
{v['questions']}.</p>
<p>When we replaced the correct option's text with a copy of a wrong one, Astra chose the original letter
{v['method_copy_original']} of the time and the copy {v['method_copy_copy']} on the {v['method_copy_text_questions']} questions
whose options are text, with no established preference (p = {v['method_copy_p']}). On the same questions, d1-ultra
({v['method_copy_d1_ultra_original']} and {v['method_copy_d1_ultra_copy']}), Jev 1.14 ({v['method_copy_jev_114_original']} and
{v['method_copy_jev_114_copy']}), Decider v1.2 (local; {v['method_copy_decider_v12_original']} and
{v['method_copy_decider_v12_copy']}), Decider Flash v1.2 (local; {v['method_copy_decider_flash_v12_original']} and
{v['method_copy_decider_flash_v12_copy']}) and GLiDE v1.2 (local; {v['method_copy_glide_v12_original']} and
{v['method_copy_glide_v12_copy']}) showed no established preference either (p from
{v['method_copy_added_p_low']} to {v['method_copy_added_p_high']}). On the {v['method_copy_numeral_questions']} questions whose
options are single numerals, Astra, d1-ultra and Decider v1.2 chose the original letter more often, which the numerals'
fixed order can explain. That checks one form of recall, not whether the model knew the question.</p>
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
setup's accuracy, ranking score, calibration gap before and after the refit, Brier scores and answers at {v['threshold']} or
more (before and after the key review),
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
<p>At {v['threshold']}, it kept {v['cut_99_kept']} answers with {v['cut_99_wrong']} wrong and passed {v['cut_99_passed']} to
the second model (error rate interval {v['decider_v11_error_span']}), and none of the {v['method_suspect']} uncertain
questions reached that confidence. Its most confident quarter held {v['surest_correct']} right answers of
{v['surest_kept']} and passed {v['surest_passed']}.</p>
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
    # The notes behind the home page's charts and cost table, which the home page folds into one caveat line per part
    # and links here (build_site.py METHOD_NOTES).
    marks = site.config["first_cost_marks"]
    sure = f"{100 * site.results['sure_threshold']:g}%"
    sections.append(("home-notes", "Notes behind the home page charts", f"""
<ul>
<li><strong>Accuracy.</strong> Each bar is a setup's share of the questions answered right, with the filters in force;
beside it the setup's cost and median latency, as in the Cost and Latency charts. Ranks show observed scores; small gaps
need not be meaningful. The paired tests behind the ranking's letters are described above.</li>
<li><strong>Cost.</strong> An estimate in dollars, not a bill, on a log scale. API setups: list prices and recorded
token use. Setups on our own GPUs: the maker's list price for the same model (each value's tooltip names it; our
hardware cost is not measured). {esc(marks['weights']['note'])} {esc(marks['gpu']['note'])} No list price: on our own
GPUs, with no estimate. {esc(marks['upper']['mark'])} {esc(marks['upper']['note'])}</li>
<li><strong>The cost table.</strong> × cheapest: a setup's cost over the cheapest setup's in the table, from the
unrounded costs; empty where there is no list price. Pareto: no other setup with a cost in the table is both at most as
costly and at least as accurate, one of them strictly. Kept at {sure}: the answers given with at least {sure} confidence,
how many of them were right, and how many questions were skipped. Non-hallucination: from the Hallucination tab's runs
with the “Bilmiyorum” option; read it with its attempt rate.</li>
<li><strong>Latency.</strong> The median time per request, from our machine, on a log scale. Local setups ran on our
hardware, listed on each setup's page; API latency includes the network, and through OpenRouter, OpenRouter's time. A
latency measured on a sample of the questions carries a mark that names the sample.</li>
<li><strong>Non-hallucination.</strong> “Bilmiyorum” among the answers that were not right, with it offered as a sixth
option; read it with the share answered. The <a href="{rel(PATH, 'dont-know/')}">Hallucination tab</a> has the full
table and its method.</li>
</ul>"""))
    toc = '<li><a href="#at-a-glance">At a glance</a></li>' + "".join(f'<li><a href="#{anchor}">{esc(title)}</a></li>' for anchor, title, _ in sections)
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
<p class="intro">This page covers the Turkish reading and grammar test. Page images and Hallucination explain their own methods on their pages: Page images under
<a href="{rel(PATH, 'vision/')}#method">How the benchmark was run</a> and Hallucination under
<a href="{rel(PATH, 'dont-know/')}#method">Our method</a>.</p>
<nav class="toc" aria-label="Sections of this page"><ul>{toc}<li><a href="#references">Sources</a></li></ul></nav>
</header>
{glance(site)}
{example}
{cards}{references}
</div>"""
    return {PATH: site.page(PATH, TITLE, DESCRIPTION, body)}
