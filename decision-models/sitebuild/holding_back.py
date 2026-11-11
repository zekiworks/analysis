"""The two kinds of holding back on the Non-hallucination parts (the home page's #non-hallucination, english/'s and the
Hallucination tab's first chart), side by side (pair), each under a plain heading (side): (A) by confidence at the
threshold (confidence_side: each setup's answers at page_config.json's threshold or more, results.json
runs[].confidence.sure, how many of them were wrong and its ranking score, confidence.auroc) and (B) with the option (the
page's own rates). Each side shows decision models and chat models as separate blocks (block, KINDS), never one mixed
ranking: under All models both blocks, under Decision models or Chat models that one. Under the decision models' option
rates, rare_note names the decision models that chose the option on fewer than results.json dont_know's
vs_confidence_share of the questions: what we observed, how often each chose it, never why."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sitebuild.site import NO_ANSWERS, Site, esc, family_legend, hbars, pct
from sitebuild.vision import joined

# The view bar's model groups as the two blocks of a side, in order: (group, heading).
KINDS = (("decision", "Decision models"), ("chat", "Chat models"))
# A run's kind of confidence (results.json runs[].confidence.source), as a block's line says it.
SOURCES = {"probability": "option probabilities", "stated": "the confidence the model states",
           "votes": "agreement across ten answers"}
NO_CONFIDENCE = "No confidence reported"


def measures(option: str, total: int) -> tuple[tuple[str, str], ...]:
    """The three numbers of a run with the option, shown together wherever its non-hallucination rate is, at the same
    size (Ümit #4665), with Logic & Math's labels, order and wording (bus #4685): each its label and what it is in one
    short phrase. option: the option as the page shows it, not escaped; total: the questions."""
    return (("Non-hallucination", f"of answers not right, % “{option}”"),
            ("Answered", f"not “{option}”: (right + wrong) / {total:,}"),
            ("Error rate", "of its answers: wrong / (right + wrong)"))


# The same three over a chart's value columns (Site hbars columns), in full and on a phone, as Logic & Math's.
COLUMNS = [("Non-hallucination", "Non-hall."), ("Answered", "Ans."), ("Error rate (wrong / answered)", "Error")]


def error_rate(counts: dict[str, Any]) -> float | None:
    """The error rate among the answers: wrong / (right + wrong), None without an answer."""
    answered = counts["right"] + counts["wrong"]
    return counts["wrong"] / answered if answered else None


def kinds(group: str) -> list[tuple[str, str]]:
    """The blocks a view bar group shows: both under all, else its own kind's."""
    return [kind for kind in KINDS if group in ("all", kind[0])]


def kind_of(site: Site, run: dict[str, Any]) -> str:
    return "decision" if site.decision(run) else "chat"


def block(title: str, body: str, level: int = 4) -> str:
    """One group's block: its heading (h4 inside a side, h3 directly in a chart card or a section), then its chart,
    notes and legend."""
    return f'<div class="hold-block"><h{level}>{esc(title)}</h{level}>{body}</div>'


def side(title: str, sub: str, blocks: str) -> str:
    """One kind of holding back: its plain heading, what it shows, then its blocks."""
    return f'<div class="hold-side"><h3>{esc(title)}</h3><p class="chart-sub">{sub}</p>{blocks}</div>'


def pair(first: str, second: str) -> str:
    """The two sides, (A) by confidence first: side by side on a wide screen, one under the other on a narrow one."""
    return f'<div class="hold-pair">{first}{second}</div>'


def option_title(option: str) -> str:
    """(B)'s heading: “Bilmiyorum” takes a, “I don't know” an."""
    return f"Holding back with {'an' if option[:1].lower() in 'aeiou' else 'a'} “{option}” option"


def sure_of(run: dict[str, Any]) -> dict[str, Any] | None:
    """A run's answers at the threshold or more (confidence.sure), None without a confidence."""
    return (run.get("confidence") or {}).get("sure")


def confidence_side(site: Site, setups: list[tuple[dict[str, Any], str, str]], group: str, scope: str,
                    title: str = "Holding back by confidence") -> str:
    """(A) for a group's setups, each (Text tab run, label, href): per block, the answers at the threshold or more (the
    bar, as a share of the questions, and the count), the wrong ones among them and the ranking score; no wrong answer at
    the threshold first, by answers kept, then the others by the share wrong among the kept answers, and a setup with no
    answers at the threshold last, muted, reading NO_ANSWERS. Each block says its
    kind of confidence (SOURCES; a row of another kind than its block's most common names its own under it); a setup
    without a confidence is named under its block. scope: where the numbers come from, said after the threshold."""
    total = site.total
    sure = pct(site.config["threshold"], 0)
    digits = site.config["percent_digits"]
    blocks = []
    # One axis for both blocks, so their bars compare: a quarter, a half or all of the questions, whichever first holds
    # the most kept.
    most = max((held["questions"] / total for run, _, _ in setups if (held := sure_of(run)) is not None), default=0.0)
    top = next(limit for limit in (0.25, 0.5, 1.0) if most <= limit)
    for kind, heading in kinds(group):
        members = [item for item in setups if kind_of(site, item[0]) == kind]
        if not members:
            continue
        missing = [label for run, label, _ in members if sure_of(run) is None]
        rated = []
        for run, label, href in members:
            if (held := sure_of(run)) is not None:
                rated.append((run, label, href, held["questions"], held["questions"] - held["correct"]))
        rated.sort(key=lambda item: (not item[3], item[4] > 0, item[4] / item[3] if item[4] else -item[3], item[1].casefold()))
        sources = Counter(item[0]["confidence"]["source"] for item in rated)
        main = sources.most_common(1)[0][0] if sources else None
        rows = [{"label": site.title(run), "tag": site.tag(run), "family": site.families[run["run"]]["name"], "href": href,
                 "class_key": site.model_class(run),
                 "note": " · ".join(filter(None, (None if run["confidence"]["source"] == main else SOURCES[run["confidence"]["source"]],
                                                  None if kept else NO_ANSWERS))) or None,
                 "muted": not kept,
                 "bars": [{"value": kept / total, "colour": site.families[run["run"]]["colour"]}],
                 "texts": [f"{kept:,}" if kept else "–", f"{wrong:,}" if kept else "–", f"{run['confidence']['auroc']:.3f}"],
                 "title": f"{site.plain(run)}: " + (f"{kept:,} of {total:,} answers at {sure} confidence or more, {wrong:,} of them "
                                                    f"wrong ({pct(wrong / kept, digits)})" if kept else
                                                    f"no answers at {sure} confidence or more")
                          + f"; ranking score {run['confidence']['auroc']:.3f} (run {run['run']})"}
                for run, label, href, kept, wrong in rated]
        said = ("; ".join(f"{SOURCES[source]} for {count}" for source, count in sources.most_common())
                if len(sources) > 1 else SOURCES[main] if main else "")
        line = f'<p class="hold-kind">Confidence: {esc(said)}.</p>' if said else ""
        legend = family_legend([site.families[item[0]["run"]] for item in rated])
        if missing:
            legend += f" <span>{NO_CONFIDENCE}: {esc(joined(missing))}.</span>"
        chart = hbars(rows, top=top, divisions=4 if top == 1.0 else 5,
                      columns=[(f"Kept at {sure}+", "Kept"), ("Wrong of kept", "Wrong"), ("Ranking score (AUROC)", "AUROC")]) \
            if rows else ""
        blocks.append(block(heading, f'{line}{chart}<p class="chart-legend">{legend}</p>'))
    sub = (f"The answers each setup gave at {sure} confidence or more{scope}, the bar their share of the {total:,} "
           "questions; how many of them were wrong; and its ranking score (AUROC: how often a right answer has higher "
           f"confidence than a wrong one, 0.5 chance, 1 perfect). No wrong answer at {sure} first, by answers kept, then "
           f"by the share wrong among the kept answers; a setup with no answers at {sure} last · more kept and fewer wrong "
           "is better")
    return side(title, sub, "".join(blocks))


def not_measured_side(group: str, language: str) -> str:
    """(A) where confidence is not measured in the page's language: the side and one line per block saying so."""
    return side("Holding back by confidence", f"Confidence at the threshold is not measured in {language}.",
                "".join(block(heading, f'<p class="note">Not measured in {esc(language)}.</p>') for _, heading in kinds(group)))


def rare_note(chosen: list[tuple[str, int, float | None]], total: int, share: float, option: str, digits: int,
              pointer: str = "the part Holding back by confidence shows how their confidence holds back wrong answers") -> str:
    """The note under the decision models' option rates: each decision model (label, times it chose the option, its
    rate) that chose the option on fewer than share of the total questions, how often, and where its confidence shows
    (pointer)."""
    rare = [item for item in chosen if item[1] < share * total]
    if not rare:
        return ""
    highest = max(rate or 0.0 for _, _, rate in rare)
    level = "near zero" if highest < 0.02 else "low"
    named = "; ".join(f"{label}, {count:,} time{'' if count == 1 else 's'}" for label, count, _ in rare)
    return (f'<p class="note hold-rare">Chose “{esc(option)}” on fewer than {100 * share:g}% of the {total:,} questions: '
            f"{esc(named)}. Their rate here is {level} ({pct(highest, digits)} or less) because they almost never chose the "
            f"option; {esc(pointer)}.</p>")
