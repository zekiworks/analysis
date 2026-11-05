"""What every page of the site shares: the data, setup names, links between pages and the page shell (head, navigation
bar, footer). The site is this folder: results.json, answers.json and page_config.json, with charts/ and share/ drawn
from the results."""

from __future__ import annotations

import hashlib
import html
import json
import math
from collections.abc import Callable, Iterable
from functools import cache, cached_property
from pathlib import Path
from typing import Any

import benchmark_metrics as bm
import build_page as bp

# The site's folder: the data, page_config.json, key-changelog.md and every page.
ROOT = Path(__file__).resolve().parent.parent
KICKER = "Hilde · Decision models · answer key v2"
ISSUE_URL = "https://github.com/zekiworks/analysis/issues/new?template="
REPO_URL = "https://github.com/zekiworks/analysis"
esc = html.escape

# The navigation bar of every page, in order: (path inside the site, label). The brand links to the home page. The two
# benchmarks beside the Text one (the home page) come first; their links keep the view bar's group (GROUP_PAGES).
MENU = (
    ("vision/", "Page images"),
    ("dont-know/", "Hallucination"),
    ("questions/", "Every question"),
    ("disagreements/", "Where models disagree"),
    ("topics/", "Topics"),
    ("compare/", "Compare"),
    ("method/", "Method"),
    ("data/", "Data"),
)
# The view bar under the top bar of every page. Row 1, the test, picks the page: (path inside the site, label).
VIEW_TESTS = (("english/", "English reading"), ("", "Turkish reading and grammar"), ("turkish-vs-english/", "English and Turkish"))
# Row 2, the models, picks the group with ?models= on the page in view when it reads it (FILTER_PAGES), else on the home
# page (site.js marks the current one and shows each element whose data-models lists it): (value of ?models=, label).
VIEW_GROUPS = (("all", "All models"), ("decision", "Decision models"), ("chat", "Chat models"))
# Row 3, the measure: on each page of row 1 a link to the part of the page with that id, in every group (the query, so
# the group, stays); on any other page a link to that part of the home page with the group (site.js marks the key of the
# part in view): (id of the part, label).
VIEW_MEASURES = (("accuracy", "Accuracy"), ("non-hallucination", "Non-hallucination"), ("cost", "Cost"),
                 ("latency", "Latency"))
# The pages of the navigation bar that read ?models=: site.js keeps the group in their links, as in the view bar's row 1.
GROUP_PAGES = ("vision/", "dont-know/")
# Every page that shows its parts by group (data-models): row 2 of the view bar stays on it.
FILTER_PAGES = (*(target for target, _ in VIEW_TESTS), *GROUP_PAGES, "web-grounding/")
# A value nobody measured reads as words; a value a filter leaves out is a dash with its reason; a zero is a number.
NOT_MEASURED = '<span class="nm">Not measured</span>'
# A cost with no estimate because the setup ran on our own hardware and its maker lists no price for the same model
# (billing 'local'): "No list price", not "Not measured" (cost_missing).
NO_LIST_PRICE = '<span class="nm">No list price</span>'


def cost_missing(run: dict[str, Any]) -> str:
    """What a cost cell or cost value shows where a run has no cost: No list price for a run on our own hardware whose
    maker lists no price (billing 'local'), else Not measured."""
    return NO_LIST_PRICE if run.get("billing") == "local" else NOT_MEASURED


# The view bar's groups (?models=), the first shown without JavaScript.
GROUPS = tuple(key for key, _ in VIEW_GROUPS)
# The attribute of a part about decision models only: shown for the all and decision groups, a note for chat.
DECISION_ONLY = 'data-models="all decision"'


def shown(group: str) -> str:
    """The attributes of a part of one group's copy: the all group's is shown without JavaScript, the others hidden."""
    return f'data-models="{group}"' + ("" if group == GROUPS[0] else " hidden")


def chat_note(text: str) -> str:
    """The one note the chat group shows instead of a page's parts about decision models only."""
    return f'<p class="note" data-models="chat" hidden>{text}</p>'


def experiments(results: dict[str, Any], path: str) -> str:
    """The line on the experiments beside the ranking, on the home page and both English pages: the web grounding page,
    when results.json has it, and the PWS-Decisions page, when pws-decisions.json is there; each link keeps the view
    bar's group (data-keep-group, site.js)."""
    link = lambda target, text: f'<a href="{rel(path, target)}" data-keep-group>{text}</a>'  # noqa: E731
    grounding = results.get("web_grounding")
    pws = (f"{link('pws-decisions/', 'PWS-Decisions')}, the decision models on Parallel's benchmark of dated web facts."
           if (ROOT / "pws-decisions.json").exists() else "")
    if grounding is None:
        return f"Beside the ranking: {pws}" if pws else ""
    return (f"Beside the ranking: {link('web-grounding/', 'Web grounding')}, {esc(grounding['names']['off'])} against "
            f"{esc(grounding['names']['on'])}." + (f" {pws}" if pws else ""))


# The LLMs the home page's Routing tab puts behind a first model, in its order: (key in page_config.json's named_runs,
# label of its control, slug in the URL, the request sizes we ran it at). Each label names the reasoning level, so
# neighbouring choices are told apart; the slugs of the first five predate the labels and stay as they are.
ROUTE_LLMS: tuple[tuple[str, str, str, tuple[int, ...]], ...] = (
    ("opus", "Opus 5.5 low", "opus", (1, 16)),
    ("sonnet_high", "Sonnet 5.5 high", "sonnet", (1, 16)),
    ("astra", "Astra low", "astra", (1, 16)),
    ("sol", "Sol low", "sol", (1, 16)),
    ("gemini_low", "Gemini Flash low", "gemini-flash", (1, 16)),
    ("opus_high", "Opus 5.5 high", "opus-high", (16,)),
    ("astra_high", "Astra high", "astra-high", (16,)),
    ("sol_high", "Sol high", "sol-high", (16,)),
    ("terra_high", "Terra high", "terra-high", (16,)),
    ("terra_low", "Terra low", "terra-low", (16,)),
    ("gemini_high", "Gemini Flash high", "gemini-flash-high", (16,)),
)


def rel(origin: str, target: str) -> str:
    """A relative link from the page at origin to target, both inside the site ('' is the home page, 'models/145/')."""
    up = "../" * origin.count("/")
    return (up + target) or "./"


def asset(target: str) -> str:
    """A file inside the site ('v3.js', 'data/picks.json') with its content's version in the query, the start of its
    SHA-256 ('v3.js?v=1a2b3c4d'). A page links its scripts and stylesheet, and its scripts fetch their data, this way,
    so a page always gets the files it was built with: a browser or the CDN caches each file for 10 minutes on its own,
    and an unversioned link could pair a new page with an old cached script."""
    return f"{target}?v={hashlib.sha256((ROOT / target).read_bytes()).hexdigest()[:8]}"


def rank_fill(stops: list[str], value: float, worst: float, best: float) -> str:
    """The ranking scale's colour (page_config.json rank_scale) for value between the worst and best values shown, as a
    CSS colour, for a chart of one series."""
    share = 1.0 if best == worst else (value - worst) / (best - worst)
    red, green, blue = bp.rank_colour(stops, share)
    return f"rgb({red:.0f},{green:.0f},{blue:.0f})"


def scale_legend(stops: list[str], worst: str, best: str, higher: bool = True) -> str:
    """The legend of bars coloured by the ranking scale: the worst value, the scale, the best value and which way is
    better."""
    return (f'<span class="scale-legend"><span>Decision models: worst {esc(worst)}</span>'
            f'<i class="ramp" style="background:linear-gradient(to right, {", ".join(stops)})" aria-hidden="true"></i>'
            f'<span>best {esc(best)} ({"higher" if higher else "lower"} is better)</span></span>')


def run_families(config: dict[str, Any], runs: list[dict[str, Any]]) -> dict[int, dict[str, str]]:
    """Each run's model family (page_config.json model_families), by run id: its name and colour. A family's rule names a
    provider and, where one provider serves several families, a model. The build stops unless every run belongs to
    exactly one family."""
    found, problems = {}, []
    for run in runs:
        families = [family for family in config["model_families"]["families"]
                    if any(rule["provider"] == run["provider"] and rule.get("model", run["model"]) == run["model"]
                           for rule in family["runs"])]
        if len(families) == 1:
            found[run["run"]] = {"name": families[0]["name"], "colour": families[0]["colour"]}
        else:
            problems.append(f"run {run['run']} ({run['name']}): in {len(families)} families")
    if problems:
        raise SystemExit("page_config.json model_families:\n  " + "\n  ".join(problems))
    return found


def family_icon(name: str) -> str:
    """A model family's icon (family_sprite) for the left of a setup's name: 14 px, hidden from screen readers, so the
    name stays the accessible text."""
    return f'<svg class="fam-icon" aria-hidden="true" focusable="false"><use href="#{icon_id(name)}"/></svg>'


def icon_id(name: str) -> str:
    """The sprite id of a family's icon: 'fi-' and its name in lower-case letters and digits (as v3.js familyIconId)."""
    return "fi-" + "".join(char for char in name.lower() if char.isalnum())


@cache
def family_sprite() -> str:
    """Every model family's icon as an SVG symbol, hidden, once on every page (topbar): the maker's official mark
    (family_icons.MARKS, by its page_config.json icon), drawn in the colour of the text beside it, or otherwise the
    family's first letter on its colour, the letter dark or white, whichever reads better on it."""
    from sitebuild.family_icons import MARKS

    symbols = []
    for family in json.loads((ROOT / "page_config.json").read_text())["model_families"]["families"]:
        if family.get("icon"):
            inner = f'<path d="{MARKS[family["icon"]]}"/>'
        else:
            red, green, blue = (int(family["colour"][index:index + 2], 16) / 255 for index in (1, 3, 5))
            ink = "#111" if 0.2126 * red + 0.7152 * green + 0.0722 * blue > 0.45 else "#fff"
            inner = (f'<rect x="1" y="1" width="22" height="22" rx="5" fill="{family["colour"]}"/>'
                     f'<text x="12" y="17.5" text-anchor="middle" font-family="system-ui, sans-serif" font-size="15" '
                     f'font-weight="700" fill="{ink}">{esc(family["name"][0].upper())}</text>')
        symbols.append(f'<symbol id="{icon_id(family["name"])}" viewBox="0 0 24 24">{inner}</symbol>')
    return f'<svg class="family-sprite" aria-hidden="true" width="0" height="0">{"".join(symbols)}</svg>'


def family_legend(families: list[dict[str, str]]) -> str:
    """The legend of bars in their model family's colour: each family once, in the order given (the chart's), with its
    icon, on one compact line of its own that wraps (v3.css .families)."""
    named = dict.fromkeys((family["name"], family["colour"]) for family in families)
    return '<span class="families">' + " ".join(
        f'<span><i class="swatch" style="background:{colour}"></i>{family_icon(name)}{esc(name)}</span>'
        for name, colour in named) + "</span>"


def hbars(rows: list[dict[str, Any]], top: float = 1.0, tick: Callable[[float], str] | None = None,
          head: tuple[str, str] | None = None, divisions: int = 4, columns: list[tuple[str, str]] | None = None) -> str:
    """A horizontal bar chart in HTML, the face of the pages without a script (the Hallucination and Page images tabs):
    readable at any width and in both themes. Each row: label, family (optional, whose icon goes before it), href (optional), bars (each a value from 0 to top, with a
    colour, a kind (a CSS class) or both: a kind's pattern, as the English bar's stripes, goes over the colour; a bar with
    a start runs from start to value, as a difference from a middle line), marker (optional, a value drawn as a line),
    text (the value as shown; or html, the value as HTML, as a cost in both units) or texts (one value per bar, each
    beside its bar) and title (the tooltip). The axis runs from 0 to top, with a tick and a line at each quarter (or each
    of the divisions), in percent unless tick writes a value its way, as HTML (aa-decision-index/ writes dollars;
    cost_tick both cost units). head names the value column above it: (in full, on a phone), as ("Turkish · English",
    "TR · EN"). With columns, several value columns, each named so: a row's texts then give one value per column
    instead. A row's group (optional) heads it and the rows after it of the same group, as a small line across the chart
    (web-grounding/ names each set of questions so)."""
    share = lambda value: 100 * min(max(value, 0.0), top) / top  # noqa: E731
    place = lambda value: f"{share(value):.4g}%"  # noqa: E731
    write = tick or (lambda value: f"{100 * value:.0f}%")
    ticks = "".join(f'<span class="hbar-tick" style="left:{place(top * index / divisions)}">'
                    f"{write(top * index / divisions)}</span>" for index in range(divisions + 1))
    # The track's lines are a background a quarter wide (v3.css); other divisions set its width, and past four a phone
    # labels every second tick (v3.css .dense).
    lines = "" if divisions == 4 else f' style="background-size:{100 / divisions:.4g}% 100%"'
    dense = " dense" if divisions > 4 else ""
    items = []
    group = None
    for row in rows:
        if row.get("group") and row["group"] != group:
            group = row["group"]
            items.append(f'<li class="hbar-group">{esc(group)}</li>')
        label = f'<a href="{row["href"]}">{esc(row["label"])}</a>' if row.get("href") else esc(row["label"])
        if row.get("family"):
            label = family_icon(row["family"]) + label
        fills = "".join(
            f'<span class="hbar-fill{" " + bar["kind"] if bar.get("kind") else ""}" style="'
            + (f'margin-left:{place(bar["start"])};width:{share(bar["value"]) - share(bar["start"]):.4g}%' if "start" in bar
               else f'width:{place(bar["value"])}')
            + f'{";background-color:" + bar["colour"] if bar.get("colour") else ""}"></span>' for bar in row["bars"])
        marker = f'<span class="hbar-marker" style="left:{place(row["marker"])}"></span>' if row.get("marker") is not None else ""
        if columns:
            values = "".join(f'<span class="hbar-value">{esc(text)}</span>' for text in row["texts"])
        elif "texts" in row:
            values = f'<span class="hbar-value stack">{"".join(f"<span>{esc(text)}</span>" for text in row["texts"])}</span>'
        else:
            values = f'<span class="hbar-value">{row["html"] if "html" in row else esc(row["text"])}</span>'
        items.append(f'<li class="hbar" title="{esc(row["title"])}"><span class="hbar-label">{label}</span>'
                     f'<span class="hbar-track"{lines}>{fills}{marker}</span>{values}</li>')
    named = "".join(f'<span class="hbar-head"><span class="head-long">{esc(long)}</span><span class="head-short">{esc(short)}'
                    "</span></span>" for long, short in (columns or ([head] if head else []))) or "<span></span>"
    # A chart with named value columns right-aligns each name and every value on the column's right edge (v3.css
    # .headed); several columns (.cols, their number in --cols) take a fixed width each, so they line up row to row.
    headed = " headed" if head or columns else ""
    cols = " cols" if columns else ""
    count = f' style="--cols:{len(columns)}"' if columns else ""
    return (f'<div class="hbar hbar-axis{headed}{dense}{cols}"{count} aria-hidden="true"><span></span>'
            f'<span class="hbar-track">{ticks}</span>{named}</div>'
            f'<ol class="hbars{headed}{cols}"{count}>{"".join(items)}</ol>')


def log_axis(values: list[float], write: Callable[[float], str]) -> tuple[Callable[[float], float], dict[str, Any]]:
    """A log scale for hbars, whose axis is linear, as the home page's Cost and Latency charts: the length of a value's
    bar, and the axis to pass to hbars (top, tick, divisions) with a tick at each power of ten (every second one past six
    decades), written by write. values: the positive values the chart shows."""
    low = math.floor(math.log10(min(values)) - 0.1)
    high = math.ceil(math.log10(max(values)))
    step = math.ceil((high - low) / 6)
    divisions = math.ceil((high - low) / step)
    return (lambda value: math.log10(value) - low,
            {"top": divisions * step, "divisions": divisions, "tick": lambda offset: write(10.0 ** round(low + offset))})


def dollars_tick(value: float) -> str:
    """A power of ten in dollars, with as many decimals as it needs: $0.01, $1, $100."""
    return f"${value:,.{max(0, -round(math.log10(value)))}f}"


def seconds_tick(value: float) -> str:
    """A power of ten in seconds, with as many decimals as it needs: 0.1 s, 1 s, 100 s."""
    return f"{value:,.{max(0, -round(math.log10(value)))}f}\u00a0s"


# The marker shapes of line_plot(), each a path around (0, 0) about 10 pixels across.
MARKERS = {
    "circle": "M -5 0 A 5 5 0 1 0 5 0 A 5 5 0 1 0 -5 0 Z",
    "square": "M -4.5 -4.5 H 4.5 V 4.5 H -4.5 Z",
    "triangle": "M 0 -6 L 5.5 4 H -5.5 Z",
}


def marker_path(shape: str, x: float, y: float) -> str:
    return f'<path transform="translate({x:.1f} {y:.1f})" d="{MARKERS[shape]}"/>'


def line_plot(series: list[dict[str, Any]], x_title: str, y_title: str, y_top: float, label: str,
              guides: tuple[tuple[float, str, str], ...] = ()) -> str:
    """An inline SVG plot without a script, readable in both themes (axes and text in the site's CSS variables, inside
    .chart-box): x from 0 to 1 and y from 0 to y_top, both in percent, a tick at each fifth of x and each quarter of y.
    Each series: colour, title (its tooltip), points [(x, y, tooltip)], and either line=True (drawn as a line through
    its points in order, dashed by its optional dash, an SVG stroke-dasharray) or shape (a MARKERS key, one marker per
    point, each with its own tooltip). A value above y_top is drawn at the top edge. Each guide: (x, short label,
    tooltip), a dashed vertical line with its label at the top."""
    width, height, left, right, top, bottom = 440, 340, 54, 16, 12, 48
    plot_w, plot_h = width - left - right, height - top - bottom
    px = lambda value: left + plot_w * min(max(value, 0.0), 1.0)  # noqa: E731
    py = lambda value: top + plot_h * (1 - min(max(value, 0.0), y_top) / y_top)  # noqa: E731
    parts = []
    for index in range(6):
        x = px(index / 5)
        parts.append(f'<line class="grid" x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}"/>'
                     f'<text class="tick" x="{x:.1f}" y="{top + plot_h + 16}" text-anchor="middle">{100 * index / 5:.0f}%</text>')
    for index in range(5):
        y = py(y_top * index / 4)
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}"/>'
                     f'<text class="tick" x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{100 * y_top * index / 4:.4g}%</text>')
    parts.append(f'<line class="axis" x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}"/>'
                 f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}"/>'
                 f'<text class="axis-title" x="{left + plot_w / 2:.1f}" y="{height - 8}" text-anchor="middle">{esc(x_title)}</text>'
                 f'<text class="axis-title" transform="translate(14 {top + plot_h / 2:.1f}) rotate(-90)" '
                 f'text-anchor="middle">{esc(y_title)}</text>')
    for x, text, tip in guides:
        anchor, shift = ("end", -4) if x > 0.75 else ("start", 4)
        parts.append(f'<g><title>{esc(tip)}</title><line x1="{px(x):.1f}" y1="{top}" x2="{px(x):.1f}" y2="{top + plot_h}" '
                     'stroke="var(--text-2)" stroke-width="1.2" stroke-dasharray="5 4"/>'
                     f'<text class="tick" x="{px(x) + shift:.1f}" y="{top + 12}" text-anchor="{anchor}">{esc(text)}</text></g>')
    for item in (item for item in series if item.get("line")):
        points = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y, _ in item["points"])
        dash = f' stroke-dasharray="{item["dash"]}"' if item.get("dash") else ""
        parts.append(f'<polyline fill="none" stroke="{item["colour"]}" stroke-width="1.8" stroke-linejoin="round"{dash} '
                     f'points="{points}"><title>{esc(item["title"])}</title></polyline>')
    for item in (item for item in series if not item.get("line")):
        marks = "".join(f'<g><title>{esc(tip)}</title>{marker_path(item["shape"], px(x), py(y))}</g>'
                        for x, y, tip in item["points"])
        parts.append(f'<g fill="{item["colour"]}" stroke="var(--panel)" stroke-width="1.2">{marks}</g>')
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" style="max-width:600px" role="img" aria-label="{esc(label)}" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(parts)}</svg>')


def legend_mark(colour: str, shape: str | None = None, dash: str | None = None) -> str:
    """A line_plot() legend key: a short line (dashed when dash is given), or a marker of that shape, in the series'
    colour."""
    dashed = f' stroke-dasharray="{dash}"' if dash else ""
    inner = (f'<line x1="1" y1="7" x2="19" y2="7" stroke="{colour}" stroke-width="2.5"{dashed}/>' if shape is None
             else f'<g fill="{colour}">{marker_path(shape, 10, 7)}</g>')
    return f'<svg width="20" height="14" viewBox="0 0 20 14" aria-hidden="true" style="vertical-align:middle">{inner}</svg>'


def topbar(path: str) -> str:
    """The top of every page: first the view bar, which stays at the top of the window: row 1 the test (a page, the
    current one marked here from the path), row 2 the models (?models=, marked by site.js, which also keeps the group in
    the row 1 links), row 3 the measure (a part of the page, marked by site.js); then the bar with the brand, which links
    home, the navigation bar and the theme switch, which scrolls away. On a page that shows its parts by group
    (FILTER_PAGES) the row 2 links stay on it, elsewhere they open the home page with that group; on a page of row 1 the
    row 3 links go to its parts, elsewhere to the home page's. On a wide screen rows 1 and 2 share a line (v3.css)."""
    current = ' aria-current="page"'
    links = "".join(
        f'<li><a href="{rel(path, target)}"{" data-keep-group" if target in GROUP_PAGES else ""}'
        f'{current if path.startswith(target) else ""}>{esc(label)}</a></li>' for target, label in MENU
    )
    tests = "".join(f'<li><a class="view-key" href="{rel(path, target)}" data-view-test{current if path == target else ""}>'
                    f"{esc(label)}</a></li>" for target, label in VIEW_TESTS)
    base = "" if path in {target for target, _ in VIEW_TESTS} else rel(path, "")
    # Row 2's keys add the word "models" only where each row has a line of its own and room for it (v3.css .view-more).
    groups = "".join(f'<li><a class="view-key" href="{"" if path in FILTER_PAGES else rel(path, "")}?models={value}" '
                     f'data-view-group="{value}"><span>{esc(label.removesuffix(" models"))}<span class="view-more"> models</span></span></a></li>'
                     for value, label in VIEW_GROUPS)
    measures = "".join(f'<li><a class="view-key" href="{base + "?models=all" if base else ""}#{key}" data-view-measure="{key}">'
                       f"{esc(label)}</a></li>" for key, label in VIEW_MEASURES)
    return (
        '<nav class="view-bar" aria-label="View: test, models and measure"><div class="view-rows">\n'
        '    <div class="view-row view-tests"><span class="view-label" id="view-test">Test</span>'
        f'<ul aria-labelledby="view-test">{tests}</ul></div>\n'
        '    <div class="view-row view-groups"><span class="view-label" id="view-models">Models</span>'
        f'<ul aria-labelledby="view-models">{groups}</ul></div>\n'
        '    <div class="view-row view-measures"><span class="view-label" id="view-measure">Measure</span>'
        f'<ul aria-labelledby="view-measure">{measures}</ul></div>\n'
        "  </div></nav>\n"
        '  <header class="topbar">\n'
        f'    <a class="brand" href="{rel(path, "")}">{esc(KICKER)}</a>\n'
        f'    <nav class="nav" aria-label="Pages"><ul>{links}</ul></nav>\n'
        '    <div class="theme-switch" role="group" aria-label="Colour theme" hidden><button type="button" class="key" '
        'data-theme-choice="dark" aria-pressed="true" aria-label="Dark background"><span class="lamp" aria-hidden="true"></span>'
        'Dark</button><button type="button" class="key" data-theme-choice="light" '
        'aria-pressed="false" aria-label="Light background"><span class="lamp" aria-hidden="true"></span>Light</button></div>\n'
        "  </header>\n"
        f"  {family_sprite()}"
    )


# The cost unit, one choice for the whole site: every cost reads per 1,000 questions or per 1M questions. site.js keeps
# the choice (?cost-unit=, then localStorage "costUnit") in <html data-cost-unit>, which a line in each page's <head>
# sets before it renders; each value and unit name below carries both units, and v3.css shows the chosen one (per 1,000
# without the script). The scripts' charts and tables write the chosen unit themselves (site.js costUnit, costNumber).
COST_UNITS = (("1k", "per 1,000 questions"), ("1m", "per 1M questions"))


def cost_text(per_thousand: float, unit: str) -> str:
    """A cost in dollars in one unit ('1k' or '1m'), as site.js costNumber writes it: per 1,000 questions with three
    decimals (two significant figures where that reads $0.000); per 1M questions with cents below $100, whole dollars
    from there."""
    if unit == "1m":
        value = per_thousand * 1000
        return f"${value:,.2f}" if value < 100 else f"${value:,.0f}"
    text = f"{per_thousand:.3f}"
    return f"${per_thousand:.2g}" if text == "0.000" and per_thousand else f"${text}"


def cost_value(per_thousand: float, prefix: str = "", dollar: bool = True) -> str:
    """A cost (dollars per 1,000 questions) as HTML in both units, the chosen one shown; prefix (a mark such as "≤ ")
    goes before each. Without dollar, the number alone, for a table whose header has the $."""
    return "".join(f'<span class="cost-{unit}">{esc(prefix)}{cost_text(per_thousand, unit)[0 if dollar else 1:]}</span>'
                   for unit, _ in COST_UNITS)


def cost_per(k: str = "per 1,000 questions", m: str = "per 1M questions") -> str:
    """A cost's unit as HTML for a header, a chart's subtitle or a note: k with per 1,000 questions chosen, m with per
    1M (plain text, escaped here)."""
    return f'<span class="cost-1k">{esc(k)}</span><span class="cost-1m">{esc(m)}</span>'


def cost_unit_in(html_text: str) -> str:
    """HTML text (already escaped) with each "per 1,000 questions" in it in both cost units (cost_per), for a header,
    subtitle or note that names the unit."""
    return html_text.replace("per 1,000 questions", cost_per())


def cost_words(per_thousand: float, prefix: str = "") -> str:
    """A cost in both units as plain text, for a tooltip: "$0.014 per 1,000 questions ($14.10 per 1M)"."""
    return (f"{prefix}{cost_text(per_thousand, '1k')} per 1,000 questions "
            f"({prefix}{cost_text(per_thousand, '1m')} per 1M)")


def cost_tick(per_thousand: float) -> str:
    """An axis tick of a cost chart (dollars per 1,000 questions, a power of ten) in both units, for hbars."""
    return (f'<span class="cost-1k">{dollars_tick(per_thousand)}</span>'
            f'<span class="cost-1m">{dollars_tick(per_thousand * 1000)}</span>')


def cost_switch() -> str:
    """The cost unit's keys, beside every cost chart and table; they need the script (site.js marks the chosen one)."""
    keys = "".join(f'<button type="button" class="key" data-cost-unit-choice="{unit}" aria-pressed="{str(unit == "1k").lower()}">'
                   f"{esc(label)}</button>" for unit, label in COST_UNITS)
    return f'<span class="cost-unit needs-js" role="group" aria-label="Cost unit">{keys}</span>'


def route_labels(runs: Iterable[dict[str, Any]], decision: Callable[[dict[str, Any]], bool]) -> dict[int, str]:
    """The route of each run whose model ID has runs among the decision models and among the other models, by run id, so
    that its rows read "GPT-6 Luna (Decisions API)" and "GPT-6 Luna (chat API)": the run's variant up to its first comma,
    else "chat API" for a run that is not a decision model. decision is page_config.json's rule (Site.decision)."""
    runs = list(runs)
    kinds: dict[str, set[bool]] = {}
    for run in runs:
        kinds.setdefault(run["model"], set()).add(decision(run))
    labels = {}
    for run in runs:
        if len(kinds[run["model"]]) < 2:
            continue
        if run.get("variant"):
            labels[run["run"]] = run["variant"].split(",")[0]
        elif not decision(run):
            labels[run["run"]] = "chat API"
        else:
            raise ValueError(f"run {run['run']} ({run['name']}) is a decision model whose model ID also has runs among the "
                             "other models; give it a variant that names its route")
    return labels


def pct(fraction: float, digits: int = 1) -> str:
    return f"{100 * fraction:.{digits}f}%"


def interval(correct: int, total: int) -> str:
    low, high = bm.wilson_interval(correct, total)
    return f"{pct(low)} to {pct(high)}"


def latency_text(seconds: float | None) -> str | None:
    """A latency with its unit, in the site's one format (build_page.seconds): "0.223 s", "7.10 s", "53.7 s"."""
    if seconds is None:
        return None
    return f"{bp.seconds(seconds)}\u00a0s"


def request_size(size: int) -> str:
    return f"{bp.count(size)} question{'' if size == 1 else 's'} per request"


class Site:
    """results.json and page_config.json; when a page needs them, answers.json and build_page.py's snapshot and values
    over the results."""

    def __init__(self) -> None:
        self.results: dict[str, Any] = json.loads((ROOT / "results.json").read_text())
        self.config: dict[str, Any] = json.loads((ROOT / "page_config.json").read_text())
        self.runs: list[dict[str, Any]] = self.results["runs"]
        self.by_id = {run["run"]: run for run in self.runs}
        self.total: int = self.results["questions"]
        self.units: list[dict[str, Any]] = self.results["units"]

    @cached_property
    def answers(self) -> dict[str, Any]:
        return json.loads((ROOT / "answers.json").read_text())

    @cached_property
    def scored(self) -> list[int]:
        """Indices into answers.json's question columns of the scored questions: all but the key audit's exclusions."""
        status = self.answers["questions"]["status"]
        return [index for index, value in enumerate(status) if value != "excluded"]

    @cached_property
    def answer_runs(self) -> dict[int, dict[str, Any]]:
        """Each leaderboard run's per-question answers, by run id."""
        return {item["run"]: item for item in self.answers["runs"]}

    @cached_property
    def families(self) -> dict[int, dict[str, str]]:
        """Each leaderboard run's model family, by run id (run_families)."""
        return run_families(self.config, self.runs)

    def icon(self, run: dict[str, Any]) -> str:
        """The icon of a leaderboard run's model family, for the left of its name (family_icon)."""
        return family_icon(self.families[run["run"]]["name"])

    @cached_property
    def snapshot(self) -> bp.Snapshot:
        """build_page.py's Snapshot over a copy of results.json (it adds request size labels to the runs it holds), with
        the count of checks from running reproduce.py (bp.reproduce), which stops the build unless every check matches."""
        return bp.Snapshot(json.loads(json.dumps(self.results)), self.config, bp.reproduce())

    @cached_property
    def values(self) -> dict[str, str]:
        """build_page.py's values over the snapshot: the Method page's numbers and the citation's counts."""
        return bp.values(self.snapshot)

    @cached_property
    def vision(self) -> dict[str, Any]:
        """vision.json: the Page images benchmark (sitebuild/vision.py)."""
        return json.loads((ROOT / "vision.json").read_text(encoding="utf-8"))

    @cached_property
    def route_labels(self) -> dict[int, str]:
        return route_labels(self.runs, self.decision)

    def row_name(self, run: dict[str, Any]) -> str:
        """A setup's name in a leaderboard row, with its route where the same model ID runs as both kinds of model."""
        label = self.route_labels.get(run["run"])
        return f"{run['name']} ({label})" if label else run["name"]

    def decision(self, run: dict[str, Any]) -> bool:
        return run["provider"] in self.config["decision_model_providers"] and run["model"] not in self.config["not_decision_models"]

    def kind(self, run: dict[str, Any]) -> str:
        return "Decision model" if self.decision(run) else "Chat model"

    def part(self, unit_number: int) -> str:
        return "reading" if unit_number in self.config["reading_units"] else "grammar"

    def unit(self, number: int) -> dict[str, Any]:
        return next(unit for unit in self.units if unit["number"] == number)

    def names(self, runs: Iterable[dict[str, Any]]) -> dict[int, str]:
        """Each run's name where runs show together (a chart, a table), by run id: its full name (row_name, with its route
        where the same model ID runs as both kinds of model), then, only where two of them would read the same, what
        tells them apart in parentheses: the variant, the reasoning setting, the request size ("Gemini 3.8 Flash (high
        reasoning, 16 per request)"). The rest of the settings stay on the model page and in tooltips. As v3.js
        chartLabels."""
        groups: dict[str, list[dict[str, Any]]] = {}
        for run in runs:
            groups.setdefault(self.row_name(run), []).append(run)
        labels = {}
        for base, same in groups.items():
            differs = lambda field: len({other.get(field) for other in same}) > 1  # noqa: E731
            for run in same:
                parts = [run["variant"]] if run.get("variant") and differs("variant") else []
                if run.get("reasoning") and differs("reasoning"):
                    parts.append(bp.reasoning_label(run["reasoning"]))
                if differs("questions_per_request"):
                    parts.append(f"{run['questions_per_request']} per request")
                labels[run["run"]] = f"{base} ({', '.join(parts)})" if parts else base
        return labels

    def cost_basis_text(self, run: dict[str, Any]) -> str:
        """How a run's cost was counted, in the model page's "Basis" words: the maker's or the same weights' list price
        for a setup on our hardware, the GPU-time estimate, the free tier's list price, else its billing's basis."""
        price = next((item for item in self.results["prices"] if bp.price_key(item) == bp.price_key(run)), None)
        basis = run.get("cost_basis")
        if basis == "maker" and price:
            return f"Estimated at {price['basis']}; our hardware cost is not measured."
        if basis == "weights" and price:
            return f"Estimated at {price['basis']}: an API-equivalent estimate; the setup ran on our GPUs, so not measured spending."
        if basis == "gpu" and "gpu" in self.config["first_cost_marks"]:
            return self.config["first_cost_marks"]["gpu"]["tip"]
        if basis == "free tier" and price:
            return f"The run used the free tier ({run['model']}); its cost is now estimated at {price['basis']}."
        return self.config["billing"][run["billing"]]["cost_basis"]

    def cost_tip(self, run: dict[str, Any]) -> str | None:
        """How a run's cost was counted, for its value's tooltip, where it is not plain API list price: a setup on our own
        hardware priced at its maker's list price for the same model or a host's for the same weights names that price;
        a GPU-time estimate gives its rate; an upper-bound estimate says so."""
        parts = []
        marks = self.config["first_cost_marks"]
        price = next((item for item in self.results["prices"] if bp.price_key(item) == bp.price_key(run)), None)
        if run.get("cost_basis") == "maker":
            parts.append(f"Estimated at {price['basis'] if price else 'its maker’s list price for the same model'}; "
                         "our hardware cost is not measured.")
        elif run.get("cost_basis") == "weights":
            parts.append(f"{marks['weights']['tip']} Price: {price['basis']}, read {price['date']}.")
        elif run.get("cost_basis") == "gpu":
            parts.append(marks["gpu"]["tip"])
        if run.get("cost_upper_bound"):
            parts.append(marks["upper"]["tip"])
        return " ".join(parts) or None

    def cost_note(self, runs: Iterable[dict[str, Any]]) -> str:
        """The one line on how the costs were counted, under a cost chart or a table with costs, for the runs it shows:
        list prices and token use; the maker's list price for a setup on our own hardware (no mark beside the value: its
        tooltip names the price), a host's for the same weights or the GPU time (first_cost_marks' notes); No list price
        where a setup has no estimate; the upper-bound mark where one shows."""
        runs = list(runs)
        note = "Costs: API list prices and recorded token use."
        if any(run.get("cost_basis") == "maker" and run.get("api_equivalent_usd") is not None for run in runs):
            note += (" Setups on our own GPUs: the maker's list price for the same model (each value's tooltip names it); "
                     "our hardware cost is not measured.")
        for basis in ("weights", "gpu"):
            if any(run.get("cost_basis") == basis for run in runs):
                note += f" {self.config['first_cost_marks'][basis]['note']}"
        if any(run.get("api_equivalent_usd") is None and run.get("billing") == "local" for run in runs):
            note += " No list price: on our own GPUs, with no estimate."
        if any(run.get("cost_upper_bound") for run in runs):
            upper = self.config["first_cost_marks"]["upper"]
            note += f" {upper['mark']} {upper['note']}"
        return note

    @staticmethod
    def accuracy(run: dict[str, Any]) -> tuple[int, int]:
        groups = run["groups"]
        return groups["reading"]["correct"] + groups["grammar"]["correct"], groups["reading"]["questions"] + groups["grammar"]["questions"]

    def ranked(self) -> list[dict[str, Any]]:
        """Every setup by accuracy on all questions, highest first."""
        return sorted(self.runs, key=lambda run: -self.accuracy(run)[0])

    def detail(self, run: dict[str, Any]) -> str:
        """A setup's variant, reasoning setting and request size: 'low reasoning · 16 questions per request'. The variant
        (a route or access note) shows only where it tells the setup apart from another run of the same model ID; an
        access note of a model with one run ("transformers, rev 52ba9e7") stays in its model page's How we called it."""
        shown = run.get("variant") and any(other["run"] != run["run"] and other["model"] == run["model"] for other in self.runs)
        parts = [run["variant"]] if shown else []
        if run.get("reasoning"):
            parts.append(bp.reasoning_label(run["reasoning"]))
        parts.append(request_size(run["questions_per_request"]))
        return " · ".join(parts)

    def full_name(self, run: dict[str, Any]) -> str:
        return f"{run['name']} · {self.detail(run)}"

    @staticmethod
    def model_path(run: dict[str, Any]) -> str:
        return f"models/{run['run']}/"

    def model_cell(self, origin: str, run: dict[str, Any], kind: bool = False, name: str | None = None) -> str:
        """A table cell naming a setup, linked to its page: its name (name, as Site.names gives it among the table's
        rows, else its full name), its settings and, with kind, its kind in the link's tooltip."""
        about = self.detail(run) + (f" · {self.kind(run)}" if kind else "")
        return (f'<td class="model"><a class="model-name" href="{rel(origin, self.model_path(run))}" title="{esc(about)}">'
                f'{esc(name or self.row_name(run))}</a></td>')

    def per_thousand(self, run: dict[str, Any]) -> float | None:
        return bp.per_thousand(run)

    def version(self) -> str:
        results = self.results
        return (f"Results {esc(results['results_version'])}, updated {bp.long_date(results['updated'])}; "
                f"answer key version {results['answer_key']['version']}.")

    def page(self, path: str, title: str, description: str, body: str, scripts: tuple[str, ...] = (),
             image: str | None = None) -> str:
        """A whole page at path (inside the site): head with its canonical address (and, with image, the key of its
        share/images.json link preview), top bar with the navigation bar, body, footer."""
        root = rel(path, "")
        preview = ""
        if image:
            url, size = esc(self.config["site_url"] + bp.current_images()[image]["dark"]), self.config["images"]["preview"]
            preview = "".join(f'\n  <meta {attr}="{name}" content="{value}">' for attr, name, value in (
                ("property", "og:title", esc(title)), ("property", "og:description", esc(description)),
                ("property", "og:type", "website"), ("property", "og:url", esc(self.config["site_url"] + path)),
                ("property", "og:image", url), ("property", "og:image:width", size["width"]),
                ("property", "og:image:height", size["height"]), ("name", "twitter:card", "summary_large_image"),
                ("name", "twitter:image", url)))
        extra = "".join(f'\n  <script src="{rel(path, asset(script))}" defer></script>' for script in scripts)
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} · Hilde</title>
  <link rel="canonical" href="{esc(self.config['site_url'] + path)}">
  <meta name="description" content="{esc(description)}">{preview}
  <script>document.documentElement.classList.add("js"); try {{ if (localStorage.getItem("theme") === "light") document.documentElement.dataset.theme = "light"; if ((new URLSearchParams(location.search).get("cost-unit") || localStorage.getItem("costUnit")) === "1m") document.documentElement.dataset.costUnit = "1m"; }} catch (e) {{}}</script>
  <link rel="stylesheet" href="{root}{asset("v3.css")}">
  <script src="{root}{asset("site.js")}" defer></script>{extra}
</head>
<body class="v3">
  <a class="skip" href="#main">Skip to content</a>
  {topbar(path)}
  <main id="main">
{body}
  </main>
  <footer class="footer">
    <p>Download: <a href="{rel(path, "results.json")}" download>results.json</a> · <a href="{rel(path, "answers.json")}" download>answers.json</a></p>
    <p>{self.version()}</p>
  </footer>
</body>
</html>
"""
