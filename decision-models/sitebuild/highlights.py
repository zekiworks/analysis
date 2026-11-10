"""The Highlights tab (highlights/): a few short cards, one striking finding each, with a heading that states it, a line
or two with its numbers and a link to the page that shows the evidence. Every number and comparison is computed from
results.json and vision.json when the site is built; a card's heading makes a claim, and the build stops when the data
no longer supports it (finding), so the page never says what the data does not."""

from __future__ import annotations

import statistics
from typing import Any

import build_page as bp

from sitebuild import vision
from sitebuild.english_reading import SIGNIFICANT
from sitebuild.site import Site, billions, esc, pct, rel

PATH = "highlights/"
TITLE = "Highlights"


def finding(holds: bool, what: str) -> None:
    """Stop the build when a card's claim no longer fits the data."""
    if not holds:
        raise SystemExit(f"highlights/: the data no longer supports this card ({what}); rewrite it in sitebuild/highlights.py")


def card(heading: str, lines: list[str], href: str, link: str) -> str:
    """One finding: its heading, its lines (HTML) and the link to its evidence."""
    text = "".join(f"<p>{line}</p>" for line in lines)
    return (f'<li class="panel exp-card highlight"><h2>{esc(heading)}</h2>{text}'
            f'<p class="highlight-link"><a href="{rel(PATH, href)}">{esc(link)}</a></p></li>')


def one_run(site: Site, provider: str, model: str) -> dict[str, Any]:
    runs = [run for run in site.runs if run["provider"] == provider and run["model"] == model]
    finding(len(runs) == 1, f"one Text tab run of {provider}/{model}, found {len(runs)}")
    return runs[0]


def glide(site: Site) -> str:
    """Fastino's released GLiDE 27B against the earlier GLiDE rows on the Text tab, with what the leaderboard's letters
    (the all-pairs test) say about each gap."""
    total = site.total
    new, old, hosted = (one_run(site, *key) for key in (("glide", "glide-27b"), ("glide", "glide-v1.2"), ("fastino", "fastino/GLiDE")))
    finding(new["correct"] > max(old["correct"], hosted["correct"]), f"{site.plain(new)} has the most right answers of the GLiDE rows")
    said = lambda run: f"{site.shown(run)}: {run['correct']:,} ({pct(run['correct'] / total)})"  # noqa: E731
    apart = lambda run: not set(new["group"]) & set(run["group"])  # noqa: E731
    separated = [site.shown(run) for run in (old, hosted) if apart(run)]
    shared = [site.shown(run) for run in (old, hosted) if not apart(run)]
    if separated and shared:
        test = (f"The leaderboard's letters separate it from {separated[0]}; it shares a letter with {shared[0]}, "
                "so the paired test does not separate those two.")
    elif separated:
        test = "The leaderboard's letters separate it from both."
    else:
        test = "It shares a letter with both on the leaderboard, so the paired test does not separate them."
    return card(f"{site.plain(new)} gets more questions right than the earlier GLiDE rows",
                [f"Right answers of the {total:,} Turkish questions: {said(new)}; {said(old)}; {said(hosted)}.", test],
                site.model_path(new), f"{site.plain(new)} on the Text tab")


def page_images(site: Site) -> str:
    """The Vision tab's three averages (vision.differences), as its summary lines give them."""
    data = site.vision
    found = vision.differences(data)
    finding(set(found) == {"B", "C", "D"}, "Vision has results for B, C and D")
    (picture, images), (both, _), (route, routes) = found["B"], found["C"], found["D"]
    finding(picture < 0, "the picture alone scores lower than the text on average")
    return card(f"From a page picture alone, models score {-picture:.1f} points lower than from the text",
                [f"On the {data['subset']['questions']:,} Turkish questions with underlined or numbered words, against the "
                 f"text alone (A): the picture alone (B) {vision.signed(picture)} and the text plus the picture (C) "
                 f"{vision.signed(both)}, averaged over {images} image models; the best OCR route (D) {vision.signed(route)}, "
                 f"over {routes} models."],
                vision.PATH, "The Vision tab")


def holding_back(site: Site) -> str:
    """The decision model with the highest non-hallucination rate with “Bilmiyorum” offered, and the next one."""
    data = site.results["dont_know"]
    option = data["option"]
    rated = sorted((model for model in data["models"] if model["group"] == "decision" and model["non_hallucination"] is not None),
                   key=lambda model: -model["non_hallucination"])
    finding(len(rated) >= 2, "two decision models with a non-hallucination rate")
    top, second = rated[:2]
    top_run, second_run = site.by_id[top["original_run"]], site.by_id[second["original_run"]]
    finding(top["attempt_rate"] < 0.5, f"{site.plain(top_run)} answers fewer than half of the questions")
    total = data["questions"]
    return card(f"{site.plain(top_run)} holds back the most, but answers few questions",
                [f"Offered “{esc(option)}”, it chose it for {top['dont_know']:,} of its {top['dont_know'] + top['wrong']:,} "
                 f"answers that were not right ({pct(top['non_hallucination'])}), and got {top['right']:,} of {total:,} right "
                 f"({pct(top['accuracy'])}).",
                 f"Next of the {len(rated)} decision models: {site.shown(second_run)}, {pct(second['non_hallucination'])}, with "
                 f"{second['right']:,} right ({pct(second['accuracy'])})."],
                "dont-know/#findings", "What we found with “I don't know”")


def languages(site: Site) -> str:
    """The same reading questions in Turkish and in English: how many setups got more right in each language, the median
    difference, and the paired tests that pass."""
    data = site.results["english_reading"]
    models = data["models"]
    gap = lambda model: model["english"]["right"] - model["turkish"]["right"]  # noqa: E731
    english, turkish = sum(gap(model) > 0 for model in models), sum(gap(model) < 0 for model in models)
    tied = len(models) - english - turkish
    median = 100 * statistics.median(model["english"]["accuracy"] - model["turkish"]["accuracy"] for model in models)
    finding(turkish > english and median < 0, "more setups score higher in Turkish than in English, and the median favours Turkish")
    passed = [model for model in models if model["paired"]["p_holm"] < SIGNIFICANT]
    up = sum(gap(model) > 0 for model in passed)
    if not passed:
        test = "No setup's difference passes the paired test."
    else:
        side = ("all of them higher in English" if up == len(passed) else "all of them higher in Turkish" if up == 0
                else f"{up} higher in English and {len(passed) - up} in Turkish")
        test = f"Only {len(passed)} setups' differences pass the paired test (Holm-adjusted), {side}."
    return card("Most setups do a little better in Turkish than in English",
                [f"On the same {data['questions']:,} reading questions, machine-translated into English: {turkish} of "
                 f"{len(models)} setups got more right in Turkish, {english} in English ({tied} tied); the median difference "
                 f"is {-median:.1f} points in Turkish's favour.", test],
                "turkish-vs-english/", "Turkish vs English")


def small_english(site: Site) -> str:
    """The best small open-weights chat model run on our GPU in English only, against every English setup."""
    data = site.results["english_reading"]
    small = [model for model in data["english_only"] if model["group"] == "chat" and model["billing"] == "local"
             and model["parameters"] is not None and model["parameters"] <= site.small_max]
    finding(bool(small), "a small open-weights chat model run in English only")
    best = max(small, key=lambda model: model["english"]["right"])
    finding((best["hardware"] or "").startswith("1 × "), f"{site.plain(best)} ran on one GPU")
    everyone = data["models"] + data["english_only"]
    above = sum(model["english"]["right"] > best["english"]["right"] for model in everyone)
    top = max(model["english"]["right"] for model in everyone)
    questions = data["questions"]
    return card(f"A {billions(best['parameters'])} open model on one GPU gets {pct(best['english']['accuracy'])} of the English reading questions",
                [f"{site.shown(best)} answered {best['english']['right']:,} of {questions:,} right, the best of the "
                 f"{len(small)} small open chat models run in English only.",
                 f"{above} of all {len(everyone)} English setups got more right; the best got {top:,} ({pct(top / questions)})."],
                "english/", "English reading")


def build(site: Site) -> dict[str, str]:
    cards = (glide(site), page_images(site), holding_back(site), languages(site), small_english(site))
    count = bp.in_words(len(cards))
    body = f"""    <section class="card">
      <h1>Highlights</h1>
      <p>{count.capitalize()} findings from this site's results, each computed when the site is built; each card links to its evidence.</p>
      <ul class="exp-cards highlights">{"".join(cards)}</ul>
    </section>"""
    return {PATH: site.page(PATH, TITLE, f"{count.capitalize()} findings from the site's results, each with its numbers and a link to the "
                                         "evidence.", body)}
