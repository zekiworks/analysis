"""The Highlights tab (highlights/): a few short cards, one striking finding each, with a heading that states it, a line
or two with its numbers and a link to the page that shows the evidence. The page is about English reading
(results.json english_reading: its kept questions, its English "I don't know" runs and its English-only setups); one
last short card points to the Vision tab, the page's only word on the questions' original language. Every number and
comparison is computed from results.json and vision.json when the site is built; a card's heading makes a claim, and the
build stops when the data no longer supports it (finding), so the page never says what the data does not."""

from __future__ import annotations

import statistics
from typing import Any

import build_page as bp

from sitebuild import vision
from sitebuild.english_reading import (SIGNIFICANT, english_members, english_only, idk_key, setup_key, setup_run)
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


def setups(site: Site) -> dict[int, dict[str, Any]]:
    """Every English reading entry (english_reading.models and english_only) by setup_key."""
    data = site.results["english_reading"]
    return {setup_key(model): model for model in [*data["models"], *english_only(data)]}


def best_decision(site: Site) -> str:
    """The decision model with the most English right answers, and what english_reading.against_reference (its exact
    McNemar test against each other decision model, Holm-adjusted, on turkish-vs-english/) says about the others."""
    data = site.results["english_reading"]
    questions = data["questions"]
    decision = english_members(site, data, "decision")
    against = data["against_reference"]
    tested = {model["runs"][0]: model for model in decision}
    finding(against["reference_run"] in tested, "the test's reference is an English decision model run")
    top = tested[against["reference_run"]]
    run = setup_run(site, top)
    finding(top["english"]["right"] == max(model["english"]["right"] for model in decision),
            f"{site.plain(run)} has the most English right answers of the decision models")
    close = [model for model in against["models"] if model["p_holm"] >= SIGNIFICANT]
    behind = [model for model in against["models"] if model["p_holm"] < SIGNIFICANT
              and model["reference_only_right"] > model["other_only_right"]]
    finding(len(close) + len(behind) == len(against["models"]) and close,
            f"no decision model ahead of {site.plain(run)}, and some too close to call")
    named = ", ".join(site.shown(setup_run(site, tested[model["run"]])) for model in close)
    return card(f"{site.plain(run)} gets the most English reading questions right of the decision models",
                [f"{site.shown(run)} answered {top['english']['right']:,} of the {questions:,} questions right "
                 f"({pct(top['english']['accuracy'])}).",
                 f"Against each of the {len(against['models'])} other decision models in the paired test (Holm-adjusted): "
                 f"{len(close)} {'is' if len(close) == 1 else 'are'} too close to call ({named}); the other {len(behind)} "
                 "got fewer right."],
                "turkish-vs-english/#against-reference", f"Each decision model against {site.plain(run)}")


def chat_ahead(site: Site) -> str:
    """The best chat model setup in English against the best decision model: right answers, and how many chat setups
    got more right; no test on the site compares a chat model with a decision model, and the card says so."""
    data = site.results["english_reading"]
    questions = data["questions"]
    decision, chat = english_members(site, data, "decision"), english_members(site, data, "chat")
    best_chat, best_dec = chat[0], decision[0]
    finding(best_chat["english"]["right"] > best_dec["english"]["right"], "the best chat setup gets more right than the best decision model")
    above = sum(model["english"]["right"] > best_dec["english"]["right"] for model in chat)
    said = lambda model: f"{site.shown(setup_run(site, model))}, {model['english']['right']:,} ({pct(model['english']['accuracy'])})"  # noqa: E731
    return card("In English, the best chat models get more questions right than any decision model",
                [f"Right answers of the {questions:,} questions: the best chat model, {said(best_chat)}; the best decision "
                 f"model, {said(best_dec)}. {above} of the {len(chat)} chat model setups got more right than "
                 f"{site.shown(setup_run(site, best_dec))}.",
                 "No test on the site compares a chat model with a decision model, so these gaps are counted, not tested."],
                "english/#accuracy", "English reading: accuracy")


def idk_entries(site: Site, group: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """The setups of a kind (decision or chat) with an English “I don't know” run (english_reading.dont_know's models
    and English-only setups), each as (its English side, its setup as a run for its name), by non-hallucination rate,
    highest first."""
    data = site.results["english_reading"]["dont_know"]
    known = setups(site)
    entries = [model for model in data["models"] + data["english_only"] if model["group"] == group and model["english"]
               and model["english"]["non_hallucination"] is not None]
    finding(all(idk_key(model) in known for model in entries), "each English “I don't know” setup has an English reading entry")
    return sorted(((model["english"], setup_run(site, known[idk_key(model)])) for model in entries),
                  key=lambda entry: -entry[0]["non_hallucination"])


def holding_back(site: Site) -> str:
    """The decision model with the highest non-hallucination rate with “I don't know” offered in English, and the next."""
    data = site.results["english_reading"]["dont_know"]
    rated = idk_entries(site, "decision")
    finding(len(rated) >= 2, "two decision models with an English “I don't know” run")
    (mine, top), (theirs, second) = rated[:2]
    finding(mine["non_hallucination"] > theirs["non_hallucination"], f"{site.plain(top)} alone has the highest rate")
    best, most = max(rated, key=lambda entry: entry[0]["right"])
    finding(mine["right"] < best["right"], f"{site.plain(top)} gets fewer right than the most accurate of them")
    total = data["questions"]
    return card(f"With “I don't know” offered in English, {site.plain(top)} holds back a wrong answer most often",
                [f"With an “I don't know” option in English, it chose it for {mine['dont_know']:,} of its "
                 f"{mine['dont_know'] + mine['wrong']:,} answers that were not right ({pct(mine['non_hallucination'])}), "
                 f"and got {mine['right']:,} of {total:,} right ({pct(mine['accuracy'])}), against {best['right']:,} "
                 f"for {site.shown(most)}, the most accurate decision model with that run.",
                 f"Next of the {len(rated)} decision models with that run: {site.shown(second)}, "
                 f"{pct(theirs['non_hallucination'])}, with {theirs['right']:,} right ({pct(theirs['accuracy'])})."],
                "dont-know/#english-option", "Hallucination: the English questions")


def kinds_holding_back(site: Site) -> str:
    """Decision models against chat model setups with “I don't know” in English: the median non-hallucination rate of
    each kind, and how many decision models are above the best chat setup."""
    decision, chat = idk_entries(site, "decision"), idk_entries(site, "chat")
    finding(bool(decision and chat), "decision and chat setups with an English “I don't know” run")
    rate = lambda entry: entry[0]["non_hallucination"]  # noqa: E731
    middle = {kind: statistics.median(rate(entry) for entry in entries) for kind, entries in (("decision", decision), ("chat", chat))}
    finding(middle["decision"] > middle["chat"], "the decision models' median rate is above the chat setups'")
    above = sum(rate(entry) > rate(chat[0]) for entry in decision)
    return card("In English, decision models choose “I don't know” over a wrong answer more often than chat models",
                [f"The median non-hallucination rate is {pct(middle['decision'])} for the {len(decision)} decision models "
                 f"and {pct(middle['chat'])} for the {len(chat)} chat model setups with an “I don't know” option in English.",
                 f"The best chat setup, {site.shown(chat[0][1])}, reaches {pct(rate(chat[0]))}; {above} decision models are "
                 "above it."],
                "english/#non-hallucination", "English reading: non-hallucination")


def small_english(site: Site) -> str:
    """The best small open-weights chat model run on our GPU in English only, against every English setup."""
    data = site.results["english_reading"]
    small = [model for model in data["english_only"] if model["group"] == "chat" and model["billing"] == "local"
             and model["parameters"] is not None and model["parameters"] <= site.small_max]
    finding(bool(small), "a small open-weights chat model run in English only")
    best = max(small, key=lambda model: model["english"]["right"])
    finding((best["hardware"] or "").startswith("1 × "), f"{site.plain(setup_run(site, best))} ran on one GPU")
    everyone = data["models"] + data["english_only"]
    above = sum(model["english"]["right"] > best["english"]["right"] for model in everyone)
    top = max(model["english"]["right"] for model in everyone)
    questions = data["questions"]
    return card(f"A {billions(best['parameters'])} open model on one GPU gets {pct(best['english']['accuracy'])} of the English reading questions",
                [f"{site.shown(setup_run(site, best))} answered {best['english']['right']:,} of {questions:,} right, the best of the "
                 f"{len(small)} small open chat models run in English only.",
                 f"{above} of all {len(everyone)} English setups got more right; the best got {top:,} ({pct(top / questions)})."],
                "english/", "English reading")


def page_images(site: Site) -> str:
    """A short pointer to the Vision tab: its picture-alone average (vision.differences' B), with the one note on the
    questions' language."""
    found = vision.differences(site.vision)
    finding("B" in found, "Vision has results for the picture alone")
    picture, images = found["B"]
    finding(picture < 0, "the picture alone scores lower than the text on average")
    return card(f"From a page picture alone, models score {-picture:.1f} points lower than from the text",
                [f"Averaged over {images} image models. Vision's questions are original Turkish page images; the Vision "
                 "tab has every result."],
                vision.PATH, "The Vision tab")


def build(site: Site) -> dict[str, str]:
    english = (best_decision(site), chat_ahead(site), holding_back(site), kinds_holding_back(site), small_english(site))
    cards = (*english, page_images(site))
    count = bp.in_words(len(english))
    body = f"""    <section class="card">
      <h1>Highlights</h1>
      <p>{count.capitalize()} findings from the English reading results, on its {site.results["english_reading"]["questions"]:,} questions, and one from the Vision tab, each computed when the site is built; each card links to its evidence.</p>
      <ul class="exp-cards highlights">{"".join(cards)}</ul>
    </section>"""
    return {PATH: site.page(PATH, TITLE, f"{count.capitalize()} English reading findings and one from the Vision tab, each with its "
                                         "numbers and a link to the evidence.", body)}
