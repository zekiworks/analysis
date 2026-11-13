"""zw_ui: the markup of the Zeki Works bench kit, the one source of every bench page's results block.

One source of the kit's markup, written from plain data: the page head (short title, scope line), the phone's Filters
bar (the Filters button with its count and the one-line scope summary), the filter rows, the Measure keys, the result
panels (one per part and measure, swapped in place) with their Chart / Table views, the bar charts with their legends,
the compact tables, each row's model cell and details box, the cost cell with its label and tap-open calculation, and
Top N with its Show all button. zw-ui.css paints it, zw-ui.js runs it; zw-ui.md is the contract. The three files are
copied byte for byte (sha256) into every site; never edit a copy.

A bench plugs in through a Bench adapter (below): its keys, measures, columns, rows with their details lines, labels
and units. Nothing here names a bench, a part or a measure. Python 3.10+, standard library only.

Base: logic's kit-form draft (bus #4885) of the Logic & Math generator (shell.py keys_row/view_keys 519-538, site_bar
571-581; home.py leaderboard 414-452, row_html 329-348, details_box 246-274, score_cell 277-283; shell.py
estimate_cell/cost_marked 206-226), completed by turkce against the kit contract (Ümit #4862, Zeki #4879).
"""
from __future__ import annotations

import hashlib
import html
import itertools
import json
import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

# The URL parameters of the filter rows, in their fixed order (Part · Models · Class · Rows); 'measure' is the Measure
# keys' parameter, 'view' the Chart / Table keys' and 'top' the Show all button's, never filter rows.
FILTER_ORDER = ("part", "models", "class", "setups")
MEASURE = "measure"
VIEW = "view"
VIEWS = ("chart", "table")


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def attrs(values: Mapping[str, str | bool | None]) -> str:
    """' name="value"' for each value; True as a bare attribute, False and None left out."""
    out = []
    for name, value in values.items():
        if value is True:
            out.append(f" {name}")
        elif value not in (None, False):
            out.append(f' {name}="{esc(value)}"')
    return "".join(out)


def classes(*names: str | None) -> str | None:
    joined = " ".join(name for name in names if name)
    return joined or None


# --- Plain data -------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Key:
    value: str  # its URL value
    label: str  # its text
    summary: str | None = None  # its words in the phone's scope summary; None: the label, '': nothing (Class: All)


@dataclass(frozen=True)
class KeyRow:
    """One labelled key row: a filter (param in FILTER_ORDER), the Measure keys (param 'measure') or a panel's Chart /
    Table keys (param 'view')."""
    param: str
    label: str
    keys: Sequence[Key]
    default: str | None = None  # None: the first key
    any: str | None = None  # the value that matches every element ('all'); a second tap clears the row to it
    hide_empty: bool = False  # a key with no row in view goes out of view (the Class row)

    @property
    def chosen(self) -> str:
        """The default value: one key's, or on a row with an any-value several keys' joined by ',' ('tiny,small')."""
        return self.default if self.default is not None else self.keys[0].value

    @property
    def chosen_values(self) -> list[str]:
        """The keys the default presses (zw-ui.js parts())."""
        return values(self.chosen)


def values(state: str | None) -> list[str]:
    """The keys a state value names: 'tiny,small' -> ['tiny', 'small'] (zw-ui.js parts(): String(value ?? '').split(',')).
    A state of several values presses each of its keys, shows an element of any of them, and meets a note condition
    that lists any of them."""
    return ("" if state is None else str(state)).split(",")


@dataclass(frozen=True)
class Tab:
    href: str
    label: str
    current: bool = False
    keep: bool = True  # carries the view (data-zw-keep)


@dataclass(frozen=True)
class Column:
    label: str
    sub: str = ""  # the small line under the label (unit, interval, order)
    num: bool = False  # right-aligned
    unit: str = ""  # the unit after the value in the phone's details line ('per 1,000 q')
    sub_1m: str = ""  # sub and unit per 1M questions, for the site's cost-unit switch (data-cost-unit="1m")
    unit_1m: str = ""
    phone: bool = False  # a helper column that stays in the table on a phone (else its value moves into the details box)
    tip: str = ""  # what the column means (HTML), opened by hover, keyboard focus and tap on its head, as the rank head's
    # rank_note (v2.6); its head then explains and never sorts


@dataclass(frozen=True)
class Model:
    """The model cell's visible parts: the dot, the name, its tag (how the setup ran), the class label and an optional
    flag ('with web')."""
    name: str
    colour: str  # the dot (the maker's or family's colour)
    dot_title: str = ""  # the dot's tooltip and the legend's entry (the maker)
    class_label: str = ""
    href: str | None = None
    flag: str = ""
    tag: str = ""  # setting · route · snapshot, never part of the name
    icon: str = ""  # HTML after the dot: the family's icon (an inline <svg> or <img>), the site's own markup


@dataclass(frozen=True)
class Bar:
    """A row's measure as a bar for the chart view: share, low, high from 0 to 1 (low/high None: no interval); ref: a
    reference mark from 0 to 1 (a vertical line: '50 = always safe'), ref_label its words (the legend lists them);
    second: a second series in the same row, drawn striped under the first (Reading's Both: Turkish over English);
    label: the series' name in the legend ('Turkish', 'English'), where a row has two."""
    share: float
    text: str
    low: float | None = None
    high: float | None = None
    ref: float | None = None
    ref_label: str = ""
    second: "Bar | None" = None
    label: str = ""


@dataclass(frozen=True)
class Axis:
    """A chart's axis under its bars: ticks (share from 0 to 1, label) and its name ('$ per 1,000 questions, log
    scale'); log_axis() makes one with a tick at each power of ten."""
    ticks: Sequence[tuple[float, str]]
    label: str = ""


@dataclass(frozen=True)
class Cost:
    """A cost amount for cost_cell(): per 1,000 questions and, for the site's cost-unit switch, per 1M; a mark before
    it ('≤': an upper bound) or after it ('†'), what the mark means in title (hover, focus)."""
    per_1k: str
    per_1m: str = ""
    prefix: str = ""
    suffix: str = ""
    title: str = ""


@dataclass(frozen=True)
class Note:
    """A note under a panel's results: html in a block, or a closed details element (summary, then html as its body);
    raw: html written as it is (the note's own markup: its own <p>, <details>, '*' lines), no block around it; when: the
    filter state it shows in ('class!=all', 'part=a,b; models=chat'), always without JavaScript."""
    html: str
    summary: str = ""
    when: str = ""
    raw: bool = False


@dataclass
class Row:
    """One row. measure and helpers are HTML (bar(), value(), cost_cell(), or the bench's own); details are the box's
    lines (HTML), every value the row does not show (the helper columns are added by the kit for the phone). filters:
    this row's value per filter parameter ({'models': 'chat', 'class': 'small'}); tiers: its tier per joined value of the
    table's tier_by parameters ({'all.all': '1', 'chat.small': '2'}; tiers_from_letters() makes them from an all-pairs
    test's letters); untiered: shown with '–', passed over by the tiers and the ranks. chart: its bar in the chart view;
    series: its legend entry (default: the model's dot_title)."""
    model: Model
    measure: str
    helpers: tuple[str, str]
    details: Sequence[str]
    details_label: str = ""  # the box's aria-label; default '<name>: details'
    filters: Mapping[str, str] = field(default_factory=dict)
    tiers: Mapping[str, str] | None = None
    untiered: bool = False
    chart: Bar | None = None
    series: str = ""
    others: Sequence["Row"] = ()  # the model's other settings: sub-rows under it, opened by its 'N other settings' key
    missing: str = ""  # the chart's words where the row has no bar ('Not measured', 'Not run')
    box_key: str = ""  # rows with one key share one details box ('' : rows with the same box content share it)
    attrs: Mapping[str, str] = field(default_factory=dict)  # extra data-* attributes on the row ({'data-planned': 'x'})
    pinned: bool = False  # a reference row (a program, a baseline): always shown, never ranked, never counted in Top N
    group: str = ""  # its block's heading in the list ('Decision models'): a list's rows of one group run together, and
    # each group is ranked and cut to Top N on its own under its heading


@dataclass(frozen=True)
class Columns:
    rank: str  # 'Tier' where an all-pairs test stands behind it, else 'Rank'
    model: str  # 'Model'
    measure: Column
    helpers: tuple[Column, Column]
    rank_note: str = ""  # what the rank head means, opened by hover, focus and tap (HTML)


@dataclass(frozen=True)
class Labels:
    """The kit's own words, each a bench may change (or translate)."""
    filters: str = "Filters"  # the phone's Filters button
    active: str = "changed"  # after the count, for screen readers
    details: str = "Details"  # each row's button
    details_suffix: str = "details"  # the box's label: '<name>: details'
    nav: str = "Pages"
    empty: str = "No row of this kind yet."
    show_all: str = "Show all {n}"  # the Show all button; {n} the rows in view, filled by zw-ui.js
    show_top: str = "Show top {n}"  # the same button while every row shows; {n} the list's Top N
    view: str = "View"
    chart: str = "Chart"
    table: str = "Table"
    legend: str = "Makers"
    others: str = "{n} other settings"  # a row's expander of its sub-rows
    others_one: str = "{n} other setting"
    boxes: str = "Details of each setup"  # the boxes' heading without JavaScript, where they read in a list
    calcs: str = "How each cost is counted"  # the cost calculations' heading without JavaScript
    loading: str = "Loading…"  # a panel loaded on first show (Fragments), while it loads
    load_failed: str = "This panel did not load."
    reload: str = "Reload the page"
    open_panel: str = "Open this panel as its own page"  # its link, without JavaScript and after a failed load
    back: str = "Back to all results"  # a panel's own page (lazy_panels): its link to the main view in the same state


# --- The adapter ------------------------------------------------------------------------------------------------------
class Bench:
    """A bench's hooks. Override title, filter_rows, columns and rows; the others have defaults. part is None on a bench
    without a Part row, setups None without a Rows row, measure None without Measure keys."""
    labels = Labels()
    top: int | None = 10  # a list's first N rows in view; None: every row
    default_view = "chart"  # where a panel has both views
    # Opt-in (v2.1; default off, so every panel is in the page and readable without JavaScript, as before): only the
    # default view's panel(s) in the page, every other panel a page of its own (results(fragments=…)), which zw-ui.js
    # inserts in place on first show and which a measure key links to without JavaScript.
    lazy_panels: bool = False
    # Opt-in (v2.1; default off: one list per Rows choice, as before): each panel has one list, the default Rows choice's
    # (one row per model, with its 'N other settings' sub-rows), and the other choice (All setups) is that list shown flat
    # by zw-ui.js: sub-rows in place, rows in the other choice's order (rows(part, measure, other)), ranks and tiers as
    # that choice's rows give them. Needs a Rows row of two keys.
    one_list: bool = False

    def title(self) -> str:
        """The page's short title."""
        raise NotImplementedError

    def scope(self, part: str | None) -> str:
        """The scope line under the title for a part: questions, language, unit."""
        return ""

    def filter_rows(self) -> list[KeyRow]:
        raise NotImplementedError

    def measure_keys(self) -> KeyRow | None:
        return None

    def views(self, part: str | None, measure: str | None) -> tuple[str, ...]:
        """('table',), ('chart', 'table') or ('chart',): a panel with two gets the Chart / Table keys."""
        return ("table",)

    def panel_title(self, part: str | None, measure: str | None) -> tuple[str, str]:
        """A panel's title and its short scope (the measure, and the part with its count and unit)."""
        return (measure or "", part or "")

    def columns(self, part: str | None, measure: str | None) -> Columns:
        raise NotImplementedError

    def rows(self, part: str | None, measure: str | None, setups: str | None) -> list[Row]:
        """The rows of one list, in their ranked order."""
        raise NotImplementedError

    def tier_by(self, part: str | None, measure: str | None) -> tuple[str, ...]:
        """The parameters a row's tier depends on ('models', 'class'); () ranks the rows in view 1, 2, 3."""
        return ()

    def chart_rank(self, part: str | None, measure: str | None) -> bool:
        """Whether the chart view shows each bar's rank or tier, as its table does."""
        return False

    def axis(self, part: str | None, measure: str | None) -> Axis | None:
        """The chart view's axis (log_axis() for a log scale: costs, latencies), or None."""
        return None

    def measured(self, part: str | None, measure: str | None) -> bool:
        """False: the panel holds one line (empty_text), no table or chart (Reading: no calibrated confidence in English)."""
        return True

    def panel_group(self, part: str | None, measure: str | None) -> str | None:
        """Parts whose panels for a measure are the same give the same key: the panel is written once, for all of them
        (data-part="turkish turkish-reading"), from the first one's rows. None: the part's own panel."""
        return part

    def anchors(self) -> Mapping[str, Mapping[str, str]]:
        """Fragments the page answers to with a view, on load and on a later change of the fragment:
        {'cost': {'measure': 'cost'}, 'calibration': {'measure': 'confidence'}}."""
        return {}

    def empty_text(self, part: str | None, measure: str | None) -> str:
        return self.labels.empty

    def notes(self, part: str | None, measure: str | None) -> list[str | Note]:
        """Short lines under a panel's results (HTML, or a Note: a details element, shown in one filter state): method
        links, the class rule; never above the results."""
        return []


def log_share(value: float, low: float, high: float) -> float:
    """A value's place from 0 to 1 on a log scale from low to high (both above 0), clipped to the ends."""
    if value <= 0:
        return 0.0
    return max(0.0, min(1.0, (math.log10(value) - math.log10(low)) / (math.log10(high) - math.log10(low))))


def log_axis(low: float, high: float, fmt: Callable[[float], str] = lambda value: f"{value:g}", label: str = "") -> Axis:
    """A log-scale axis from low to high: a tick at each power of ten between them, and at both ends."""
    ticks = [low] + [10.0 ** power for power in range(math.ceil(math.log10(low)), math.floor(math.log10(high)) + 1)] + [high]
    seen: list[float] = []
    for tick in ticks:
        if not any(abs(math.log10(tick) - math.log10(other)) < .15 for other in seen):
            seen.append(tick)
    return Axis([(log_share(tick, low, high), fmt(tick)) for tick in sorted(seen)], label)


def tiers_from_letters(items: Sequence[tuple[Mapping[str, str], str | None]], by: Mapping[str, Sequence[str]],
                       any_value: str = "all") -> list[dict[str, str]]:
    """Each row's tier for every combination of the tier_by values (by: {'models': ['all', 'chat', …], 'class': […]}),
    from the letters an all-pairs test gave it (items: (filters, letters) in ranked order; letters None: untiered). In
    each view a row joins the tier of the tier's top row when they share a letter, else it starts the next tier (Reading's
    Turkish part)."""
    out: list[dict[str, str]] = [{} for _ in items]
    names = list(by)
    for combo in itertools.product(*(by[name] for name in names)):
        top: str | None = None
        tier = 0
        for index, (filters, letters) in enumerate(items):
            if letters is None or not all(value == any_value or filters.get(name) in (None, *value.split(","))
                                          for name, value in zip(names, combo)):
                continue
            if top is None or not set(letters) & set(top):
                top, tier = letters, tier + 1
            out[index][".".join(combo)] = str(tier)
    return out


# --- The page and its header (shell.py:583-639 page, 571-581 site_bar) -----------------------------------------------
def page(title: str, body: str, header_html: str = "", *, lang: str = "en", css: Iterable[str] = ("zw-ui.css",),
         js: Iterable[str] = ("zw-ui.js",), head_extra: str = "", theme: str | None = None) -> str:
    """A whole page: the kit's class set before the first paint (no flash of the no-JavaScript view), its stylesheet and
    script (deferred), then the header and <main>. css/js: the site's files, the kit's among them."""
    links = "".join(f'\n  <link rel="stylesheet" href="{esc(href)}">' for href in css)
    scripts = "".join(f'\n  <script src="{esc(src)}" defer></script>' for src in js)
    return (f'<!doctype html>\n<html lang="{esc(lang)}"{attrs({"data-theme": theme})}>\n<head>\n  <meta charset="utf-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'  <title>{esc(title)}</title>\n'
            '  <script>document.documentElement.classList.add("zw-js");</script>'
            f'{links}{scripts}{head_extra}\n</head>\n<body>\n{header_html}\n<main id="main">\n{body}\n</main>\n</body>\n</html>\n')


def header(tabs: Sequence[Tab], *, brand: Tab | None = None, end: str = "", labels: Labels = Labels()) -> str:
    """One row: the brand (out of view below 600 px), the page tabs (the current one aria-current="page"; the row
    scrolls inside itself, never the page), and end (HTML at the row's end: a theme switch). A site that keeps its own
    header leaves this out; the kit's Filters button sits in the results block (results())."""
    brand_html = f'<a class="zw-brand" href="{esc(brand.href)}">{esc(brand.label)}</a>' if brand else ""
    items = "".join(f'<li><a{attrs({"href": tab.href, "data-zw-keep": tab.keep, "aria-current": "page" if tab.current else None})}>'
                    f"{esc(tab.label)}</a></li>" for tab in tabs)
    return (f'<header class="zw-head"><div class="zw-head-in">{brand_html}'
            f'<nav class="zw-nav" aria-label="{esc(labels.nav)}"><ul>{items}</ul></nav>{end}</div></header>')


# --- Key rows (shell.py:519-538 keys_row/view_keys; home.py:415-426 the leaderboard's keys) -------------------------
def key_row(row: KeyRow, *, hidden_keys: Iterable[str] = (), label_id: str | None = None, cls: str | None = None) -> str:
    """A labelled row of toggle buttons (aria-pressed), the default's key(s) pressed; zw-ui.js marks the URL's choice.
    hidden_keys: keys out of the default view (a Class key with no row in it), so nothing moves on load."""
    label_id = label_id or f"zw-label-{row.param}"
    hidden = set(hidden_keys)
    pressed = row.chosen_values
    keys = "".join(f'<button type="button" class="zw-key" data-zw-value="{esc(key.value)}"'
                   f'{attrs({"data-zw-summary": key.summary if key.summary is not None else None, "hidden": key.value in hidden})}'
                   f' aria-pressed="{"true" if key.value in pressed else "false"}">{esc(key.label)}</button>'
                   for key in row.keys)
    row_cls = classes("zw-row", "zw-measures" if row.param == MEASURE else None, cls)
    return (f'<div{attrs({"class": row_cls, "data-zw-param": row.param, "data-zw-default": row.chosen, "data-zw-any": row.any, "data-zw-hide-empty": row.hide_empty})}'
            f' role="group" aria-labelledby="{esc(label_id)}"><span class="zw-row-label" id="{esc(label_id)}">{esc(row.label)}</span>'
            f'<div class="zw-keys">{keys}</div></div>')


def filter_rows(rows: Sequence[KeyRow], block_id: str = "zw-filters", hidden_keys: Mapping[str, Iterable[str]] | None = None,
                *, label_prefix: str = "zw-label") -> str:
    """The filter rows in the fixed order Part · Models · Class · Rows (an unknown parameter after them); label_prefix:
    the start of each row label's id (results() gives '<block id>-label', unique per block)."""
    order = lambda row: FILTER_ORDER.index(row.param) if row.param in FILTER_ORDER else len(FILTER_ORDER)  # noqa: E731
    return (f'<div class="zw-filters" id="{esc(block_id)}">'
            + "".join(key_row(row, hidden_keys=(hidden_keys or {}).get(row.param, ()), label_id=f"{label_prefix}-{row.param}")
                      for row in sorted(rows, key=order)) + "</div>")


def filter_bar(rows: Sequence[KeyRow], block_id: str = "zw-filters", labels: Labels = Labels()) -> str:
    """The phone's Filters bar (job8-look's Filters key, logic's count badge): the button that folds the filter rows,
    the count of rows away from their default (none in the default view), and the one-line summary of the scope."""
    words = []
    for row in sorted(rows, key=lambda r: FILTER_ORDER.index(r.param) if r.param in FILTER_ORDER else len(FILTER_ORDER)):
        pressed = row.chosen_values
        # each pressed key in the row's order, as zw-ui.js reads them
        words.extend(key.summary if key.summary is not None else key.label for key in row.keys if key.value in pressed)
    summary = " \u00b7 ".join(word for word in words if word)
    return (f'<div class="zw-filterbar"><button type="button" class="zw-filters-toggle" aria-controls="{esc(block_id)}" '
            f'aria-expanded="false">{esc(labels.filters)}<span class="zw-filter-count" hidden><span data-zw-n>0</span>'
            f'<span class="zw-sr"> {esc(labels.active)}</span></span></button>'
            f'<p class="zw-summary">{esc(summary)}</p></div>')


# --- Cells ---------------------------------------------------------------------------------------------------------
def value(text: str, interval: str = "") -> str:
    """A number in the mono face, its interval beside it (under it on a phone)."""
    return f'<span class="zw-val">{esc(text)}' + (f'<span class="zw-int">{esc(interval)}</span>' if interval else "") + "</span>"


def _ref_mark(ref: float | None, ref_label: str) -> str:
    """A reference mark inside a bar: a vertical line at ref (0 to 1), its words in its title (and in the legend)."""
    if ref is None:
        return ""
    return f'<span class="zw-bar-ref" style="left:{100 * max(0.0, min(1.0, ref)):.2f}%"{attrs({"title": ref_label or None})}></span>'


def _track(share: float, low: float | None, high: float | None, colour: str, ref: float | None = None, ref_label: str = "",
            second: Bar | None = None) -> str:
    """A bar's track: its fill, its interval whisker (none without low and high), its reference mark; with second, the
    second series' bar striped under it, both in one track."""
    def one(value: float, lo: float | None, hi: float | None, extra: str | None, mark: str) -> str:
        interval = f";--lo:{lo:.4f};--hi:{hi:.4f}" if lo is not None and hi is not None else ""
        return (f'<span class="{classes("zw-bar", extra, None if interval else "zw-bar-plain")}" '
                f'style="--v:{value:.4f}{interval};--c:{esc(colour)}" aria-hidden="true">{mark}</span>')
    first = one(share, low, high, None, _ref_mark(ref, ref_label))
    if second is None:
        return first
    return (f'<span class="zw-bar-pair">{first}'
            f'{one(second.share, second.low, second.high, "zw-bar-second", _ref_mark(second.ref, second.ref_label))}</span>')


def bar(share: float, low: float | None = None, high: float | None = None, colour: str = "", text: str = "", interval: str = "",
        *, ref: float | None = None, ref_label: str = "", second: Bar | None = None) -> str:
    """The measure as a bar (share, low, high from 0 to 1; the interval as a whisker, none where low and high are None)
    with its number (home.py:277-283); ref: a reference mark from 0 to 1 (a vertical line), ref_label what it stands
    for ('50 = always safe'); second: a second series (a Bar: Reading's English beside its Turkish), striped under the
    first, its number after the first's."""
    return (_track(share, low, high, colour, ref, ref_label, second) + value(text, interval)
            + (f'<span class="zw-val zw-val-second">{esc(second.text)}</span>' if second is not None else "")
            + (f'<span class="zw-sr"> ({esc(ref_label)})</span>' if ref is not None and ref_label else ""))


def units(per_1k: str, per_1m: str = "") -> str:
    """A text in the site's cost unit: per 1,000 questions, and per 1M where given (cost-1k / cost-1m; the site's switch
    sets data-cost-unit="1m" on <html>, as Reading's and Logic & Math's do)."""
    if not per_1m:
        return esc(per_1k)
    return f'<span class="cost-1k">{esc(per_1k)}</span><span class="cost-1m">{esc(per_1m)}</span>'


def cost_cell(amount: str | Cost, label: str, kind: str, method: str = "") -> str:
    """A cost: the amount and one short label ('List price', 'GPU estimate', 'Billed', 'Subscription', 'No list price').
    amount: a text, or a Cost (per 1,000 and per 1M questions, a mark such as '≤' or '†'). kind: 'list', 'estimate',
    'billed', 'subscription' or 'none' (an estimate's label in italics). method: how it was counted, opened by a tap on
    the label (a details element: Enter, Space and Escape too; in place without JavaScript)."""
    if isinstance(amount, Cost):
        def mark(text: str) -> str:
            return f'<span class="zw-cost-mark"{attrs({"title": amount.title or None})}>{esc(text)}</span>' if text else ""
        number = mark(amount.prefix) + units(amount.per_1k, amount.per_1m) + mark(amount.suffix)
    else:
        number = esc(amount)
    if method:
        label_html = (f'<details class="zw-calc"><summary class="zw-cost-label">{esc(label)}</summary>'
                      f'<span class="zw-calc-body">{esc(method)}</span></details>')
    else:
        label_html = f'<span class="zw-cost-label">{esc(label)}</span>'
    return f'<span class="zw-cost" data-kind="{esc(kind)}"><span class="zw-cost-num">{number}</span>{label_html}</span>'


def cost_method(text: str) -> str:
    """The method of a cost, for a details line ('Cost $0.42 per 1,000 questions · ' + cost_method(...))."""
    return f'<span class="zw-cost-method">{esc(text)}</span>'


def details_box(box_id: str, label: str, lines: Sequence[str], phone_lines: Sequence[str] = ()) -> str:
    """A row's details box (home.py:246-274): one <p> per line, the empty ones left out; phone_lines (the helper
    columns' values) only below 600 px, where those columns are out of the table."""
    return (f'<div class="zw-box" id="{esc(box_id)}" role="group" aria-label="{esc(label)}">'
            + "".join(f'<div class="zw-box-phone">{line}</div>' for line in phone_lines if line)
            + "".join(f"<p>{line}</p>" for line in lines if line) + "</div>")


class Boxes:
    """A block's details boxes, one per setup: rows with the same box_key, or else the same box content, share one box
    written once after the results (one box per row × list × panel took Logic & Math's page from 1.0 to 4.9 MB). Each row
    refers to its box by id; zw-ui.js moves the box into the row that opens it. Without JavaScript the boxes read as a
    list under the results, each row linking to its own."""

    def __init__(self, prefix: str = "zw-box"):
        self.prefix = prefix
        self.ids: dict[object, str] = {}
        self.html: list[str] = []
        self.by_id: dict[str, str] = {}
        self.used: set[str] = set()  # the ids asked for since results() last emptied it (one panel's)

    def box(self, row: Row, labels: Labels = Labels()) -> str:
        """The id of the row's box, written the first time it is asked for."""
        label = row.details_label or f"{row.model.name}: {labels.details_suffix}"
        key: object = row.box_key or (label, tuple(row.details))
        if key not in self.ids:
            self.ids[key] = f"{self.prefix}-{len(self.ids) + 1}"
            self.html.append(details_box(self.ids[key], label, row.details))
            self.by_id[self.ids[key]] = self.html[-1]
        self.used.add(self.ids[key])
        return self.ids[key]

    def section(self, labels: Labels = Labels(), ids: Iterable[str] | None = None) -> str:
        """The boxes after the results: all of them, or those with the given ids (in the order they were written)."""
        wanted = None if ids is None else set(ids)
        chosen = [markup for box_id, markup in self.by_id.items() if wanted is None or box_id in wanted]
        if not chosen:
            return ""
        return f'<div class="zw-boxes"><h2 class="zw-boxes-title">{esc(labels.boxes)}</h2>{"".join(chosen)}</div>'


class Calcs:
    """A block's cost calculations, each distinct text written once after the results (one per cell × list × panel was
    a third of Logic & Math's page): every cost label refers to its text by id (a.zw-calc-key, a link to it, drawn as a
    button) and zw-ui.js opens the text from the label on a tap, Enter or Space. results() turns the cost cells'
    calculations (cost_cell(method=...)) into these references."""

    PATTERN = re.compile(r'<details class="zw-calc"><summary class="zw-cost-label">(.*?)</summary>'
                         r'<span class="zw-calc-body">(.*?)</span></details>', re.S)

    def __init__(self, prefix: str = "zw-calc"):
        self.prefix = prefix
        self.ids: dict[str, str] = {}
        self.by_id: dict[str, str] = {}

    def share(self, markup: str, used: set[str] | None = None) -> str:
        """The markup with each calculation replaced by a reference to its one text; used collects the ids."""
        def reference(match: re.Match[str]) -> str:
            label, text = match.group(1), match.group(2)
            if text not in self.ids:
                calc_id = f"{self.prefix}-{len(self.ids) + 1}"
                self.ids[text] = calc_id
                self.by_id[calc_id] = f'<div class="zw-calc-body" id="{calc_id}" role="note">{text}</div>'
            calc_id = self.ids[text]
            if used is not None:
                used.add(calc_id)
            # A link to its text; zw-ui.js makes it a button (role, aria-expanded, aria-controls) as the page loads.
            return f'<a class="zw-calc-key" href="#{calc_id}">{label}</a>'
        return self.PATTERN.sub(reference, markup)

    def section(self, labels: Labels = Labels(), ids: Iterable[str] | None = None) -> str:
        """The calculations after the results: all, or those with the given ids."""
        wanted = None if ids is None else set(ids)
        chosen = [markup for calc_id, markup in self.by_id.items() if wanted is None or calc_id in wanted]
        if not chosen:
            return ""
        return f'<div class="zw-calcs"><h2 class="zw-calcs-title">{esc(labels.calcs)}</h2>{"".join(chosen)}</div>'


class Fragments:
    """The panels outside the default view as static files beside the page, loaded on first show (zw-ui.js), so the
    page carries only its default view (Bench.lazy_panels): give one to results(), which keeps the default panel(s) in the page and writes
    each other panel's stub there (its head and keys, a link to its file). Each file is a small page of its own (the
    panel, then the boxes and calculations its rows refer to), named <folder>/<panel id>.<8 hex of its sha256>.html, so
    a fresh page never meets a stale cached file. css: the stylesheets each file links (relative to the folder:
    '../v3.css', '../zw-ui.css'). write() puts the files in place and removes the folder's files of an earlier build.

    theme: None writes no data-theme; 'light' or 'dark' fixes it; 'auto' (v2.1) lets a page opened on its own follow the
    reader: a one-line script in its head sets data-theme from the site's stored choice (localStorage[theme_key], the
    site's Light / Dark switch), else the site's own default (theme_default: 'dark' for a site whose main page is dark
    until the reader chooses, as Reading's and Logic & Math's), else the system setting. Without the script the page
    shows theme_default (written as its data-theme), or with none, zw-ui.css paints it in the system's scheme
    (html.zw-panel-page, prefers-color-scheme). Inserted into the main page, a panel follows the page's theme.
    sprite: the main page's SVG sprite (its <symbol id=…> elements, as the page writes them); each file carries the
    symbols its own markup refers to (href="#id"), so the family icons (Model.icon) show on a page opened on its own;
    the main page is unchanged."""

    SYMBOL = re.compile(r'<symbol\b[^>]*?\bid="([^"]+)"[^>]*>.*?</symbol>', re.S)
    REFERENCE = re.compile(r'(?:xlink:)?href="#([^"]+)"|url\(#([^)]+)\)')

    def __init__(self, folder: str = "zw-panels", css: Iterable[str] = ("../zw-ui.css",), lang: str = "en",
                 theme: str | None = None, page: str = "../", *, sprite: str = "", theme_key: str = "theme",
                 theme_default: str | None = None):
        if theme_default not in (None, "light", "dark"):
            raise ValueError(f"zw_ui.Fragments: theme_default {theme_default!r}: 'light', 'dark' or None")
        self.folder = folder.strip("/")
        self.css = tuple(css)
        self.lang = lang
        self.theme = theme
        self.page = page  # the main page, from a file in the folder: the files' link back
        self.symbols = {match.group(1): match.group(0) for match in self.SYMBOL.finditer(sprite)}
        self.theme_key = theme_key
        self.theme_default = theme_default
        self.files: dict[str, str] = {}  # the path beside the page -> the file's text

    def _sprite(self, markup: str) -> str:
        """The sprite's symbols the markup refers to (and those they refer to), in a hidden <svg>."""
        wanted: list[str] = []
        todo = [ref for match in self.REFERENCE.finditer(markup) for ref in match.groups() if ref]
        while todo:
            ref = todo.pop(0)
            if ref in self.symbols and ref not in wanted:
                wanted.append(ref)
                todo += [r for match in self.REFERENCE.finditer(self.symbols[ref]) for r in match.groups() if r]
        if not wanted:
            return ""
        return ('<svg class="zw-sprite" aria-hidden="true" focusable="false" width="0" height="0" '
                'style="position:absolute;width:0;height:0;overflow:hidden">' + "".join(self.symbols[ref] for ref in wanted) + "</svg>")

    LINK = re.compile(r'<a\b[^>]*>')
    HREF = re.compile(r'\bhref="([^"]*)"')

    def _localise(self, markup: str, ids: set[str]) -> str:
        """The panel's links as the panel page needs them: a fragment with no target on it ('#method': a section of the
        main page) goes to the main page's ('../index.html#method'), and a relative address ('models/x/', written from
        the main page) to the same place from the folder ('../models/x/'). Each keeps its own href in data-zw-href,
        which zw-ui.js puts back when it inserts the panel into the main page; other links stay as they are."""
        main = re.split(r"[?#]", self.page, maxsplit=1)[0]
        folder_to_page = main.rsplit("/", 1)[0] + "/" if "/" in main else ""

        def link(match: re.Match[str]) -> str:
            tag = match.group(0)
            found = self.HREF.search(tag)
            if not found or "data-zw-href=" in tag:
                return tag
            href = html.unescape(found.group(1))
            if href.startswith("#"):
                if not href[1:] or href[1:] in ids:
                    return tag
                new = main + href
            elif not href or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:|/", href):
                return tag
            else:
                new = folder_to_page + href
            return tag[:found.start()] + f'href="{esc(new)}" data-zw-href="{esc(href)}"' + tag[found.end():]

        return self.LINK.sub(link, markup)

    def add(self, panel_id: str, title: str, panel_html: str, after: str = "", head: str = "") -> str:
        """A panel's file, a page of its own (its title, head: the bench's title, scope line and link back; the panel;
        after: its boxes and calculations): its path beside the page (the stub's data-zw-src)."""
        links = "".join(f'<link rel="stylesheet" href="{esc(href)}">' for href in self.css)
        auto = self.theme == "auto"
        theme_head = ""
        if auto:
            # Before the first paint: the reader's stored choice, else the system's; without it, zw-ui.css follows the system.
            stored = 'var t;try{t=localStorage.getItem(' + json.dumps(self.theme_key).replace("<", "\\u003c") + ')}catch(e){}'
            # with a site default (already the page's data-theme): only a stored choice changes it
            pick = ('if(t==="light"||t==="dark")' if self.theme_default else
                    'if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";')
            theme_head = ('<meta name="color-scheme" content="light dark"><script>(function(){' + stored + pick
                          + 'document.documentElement.setAttribute("data-theme",t)})();</script>')
        ids = set(re.findall(r'\bid="([^"]+)"', f"{head}{panel_html}{after}"))
        body = f"{head}{self._localise(panel_html, ids)}{self._localise(after, ids)}"
        text = (f'<!doctype html>\n<html lang="{esc(self.lang)}"{attrs({"class": "zw-panel-page" if auto else None, "data-theme": (self.theme_default if auto else self.theme)})}>\n'
                '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">'
                f'<title>{esc(title)}</title>{theme_head}{links}</head>\n<body>{self._sprite(body)}<main class="zw-fragment"><div class="zw-block">'
                f"{body}</div></main></body>\n</html>\n")
        path = f"{self.folder}/{panel_id}.{hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]}.html"
        self.files[path] = text
        return path

    def write(self, page_dir: str | Path) -> list[str]:
        """Writes the files beside the page (page_dir: the page's folder) and removes the folder's other files named as
        these are (an earlier build's); returns the paths written."""
        folder = Path(page_dir) / self.folder
        folder.mkdir(parents=True, exist_ok=True)
        current = {Path(path).name for path in self.files}
        for old in folder.glob("*.*.html"):
            if old.name not in current and re.fullmatch(r".+\.[0-9a-f]{8}\.html", old.name):
                old.unlink()
        for path, text in self.files.items():
            (Path(page_dir) / path).write_text(text, encoding="utf-8")
        return sorted(self.files)


def model_cell(model: Model, box_id: str, box_label: str, lines: Sequence[str], labels: Labels = Labels(),
               phone_lines: Sequence[str] = (), *, shared: bool = False, more: str = "") -> str:
    """The model cell (home.py:339-348): the dot, the family icon, the name (a link when href, else focusable), its tag,
    the flag, the class label, the expander of its other settings (more) and the details box: in the cell (its
    phone_lines on top below 600 px), or with shared, the box's id (Boxes) and a link to it without JavaScript; zw-ui.js
    then writes the row's helper values (each helper head's data-zw-label and data-zw-unit) on top of the box it opens.
    No Details button under the name (v2.4, Ümit via Zeki #5462): a tap on the name or the row opens the box, keyboard
    focus on the name shows it (zw-ui.js details)."""
    name = (f'<a class="zw-name" href="{esc(model.href)}">{esc(model.name)}</a>' if model.href
            else f'<span class="zw-name" tabindex="0">{esc(model.name)}</span>')
    if shared:
        tail = more + f'<a class="zw-details-link" href="#{esc(box_id)}">{esc(labels.details)}</a>'
    else:
        tail = more + details_box(box_id, box_label, lines, phone_lines)
    return (f'<td class="zw-model"><i class="zw-dot" style="--zw-dot:{esc(model.colour)}"{attrs({"title": model.dot_title or None})}></i>'
            + (f'<span class="zw-icon" aria-hidden="true">{model.icon}</span>' if model.icon else "") + name
            + (f' <span class="zw-tag">{esc(model.tag)}</span>' if model.tag else "")
            # A space before the flag and the class (v2.6): where the cell is narrow they move to the next line, the name
            # stays whole beside its icon.
            + (f' <span class="zw-flag">{esc(model.flag)}</span>' if model.flag else "")
            + (f' <span class="zw-class">{esc(model.class_label)}</span>' if model.class_label else "")
            + tail + "</td>")


# --- The compact table, the chart, a list, a panel ----------------------------------------------------------------
def head_cell(column: Column, cls: str = "", tip_id: str = "") -> str:
    """A column head; a helper's head also carries its label and unit for the phone's details line (zw-ui.js). With a tip
    (and its tip_id, unique in the page) the label is a key whose explanation opens by hover, focus and tap (v2.6)."""
    helper = "zw-help" in cls.split()
    label = esc(column.label)
    if column.tip and tip_id:
        label = _tip(label, column.tip, tip_id)
    return (f'<th scope="col"{attrs({"class": classes(cls, "zw-num" if column.num else None, "zw-keep-phone" if column.phone else None), "data-zw-label": column.label if helper else None, "data-zw-unit": units(column.unit, column.unit_1m) if helper and column.unit else None})}>'
            f'{label}' + (f'<span class="zw-sub">{units(column.sub, column.sub_1m)}</span>' if column.sub else "") + "</th>")


def _tip(label_html: str, tip_html: str, tip_id: str) -> str:
    """A key (label_html) whose explanation (tip_html) opens by hover, keyboard focus and tap (zw-ui.js, .zw-tip)."""
    return (f'<span class="zw-tip"><button type="button" class="zw-tip-key" aria-expanded="false" aria-controls="{esc(tip_id)}" '
            f'aria-describedby="{esc(tip_id)}">{label_html}</button>'
            f'<span class="zw-tip-body" id="{esc(tip_id)}" role="tooltip">{tip_html}</span></span>')


def rank_head(columns: Columns, tip_id: str) -> str:
    """The rank head (Tier or Rank); with rank_note, a key whose explanation opens by hover, focus and tap."""
    if not columns.rank_note:
        return f'<th scope="col" class="zw-rank">{esc(columns.rank)}</th>'
    return f'<th scope="col" class="zw-rank">{_tip(esc(columns.rank), columns.rank_note, tip_id)}</th>'


def _row_attrs(row: Row, extra: Mapping[str, str | bool | None], cls: str | None) -> str:
    """A row's or bar's attributes: its class, its filter values (data-<param>), the kit's own, the adapter's (attrs)."""
    return attrs({"class": cls, **{f"data-{k}": v for k, v in row.filters.items()}, **extra,
                  "data-zw-pinned": row.pinned, **row.attrs})



def _setup_key(row: Row, labels: Labels) -> object:
    """Which setup a row shows: its box_key, else its box's label and lines (as Boxes shares boxes)."""
    return row.box_key or (row.details_label or f"{row.model.name}: {labels.details_suffix}", tuple(row.details))


def _one_list(rows: Sequence[Row], flat_rows: Sequence[Row], flat_value: str, labels: Labels) -> list[Row]:
    """Bench.one_list: the default list's rows and sub-rows, each marked with its place in the flat list (the other Rows
    choice: data-zw-flat-order) and that list's tier (data-zw-flat-tier, data-zw-flat-untiered); a setup of the flat list
    the default list does not hold comes last, shown only for that choice (data-setups)."""
    place: dict[object, tuple[int, Row]] = {}
    for index, row in enumerate(flat_rows):
        place.setdefault(_setup_key(row, labels), (index, row))

    def flat_attrs(index: int, row: Row) -> dict[str, str]:
        extra = {"data-zw-flat-order": str(index)}
        if row.untiered:
            extra["data-zw-flat-untiered"] = ""
        elif row.tiers:
            extra["data-zw-flat-tier"] = " ".join(f"{key}={value}" for key, value in row.tiers.items())
        return extra

    def placed(row: Row) -> Row:
        found = place.pop(_setup_key(row, labels), None)
        return row if found is None else replace(row, attrs={**row.attrs, **flat_attrs(*found)})

    out = [replace(placed(row), others=[placed(other) for other in row.others]) for row in rows]
    for index, row in sorted(place.values(), key=lambda item: item[0]):
        out.append(replace(row, filters={**row.filters, "setups": flat_value}, others=(),
                           attrs={**row.attrs, **flat_attrs(index, row)}))
    return out

def _numbers(rows: Sequence[Row], tier_by: Sequence[str], state: Mapping[str, str | None],
             marks: Sequence[str | None]) -> list[tuple[str, bool]]:
    """Each rank cell as the default view shows it, and whether its row starts a new tier (zw-ui.js writes the same
    digits, so nothing changes on load): 1, 2, 3 among the ranked rows in view, or each row's tier for the view's
    values, counted again in each group (Row.group); '–' for an untiered row; nothing for a pinned row or a row out of
    the view, which shows only without JavaScript."""
    key = ".".join(str(state.get(name) or "") for name in tier_by)
    out: list[tuple[str, bool]] = []
    place: dict[str, int] = {}
    last: dict[str, str] = {}
    for row, mark in zip(rows, marks):
        if mark == "zw-away" or row.pinned:
            out.append(("", False))
        elif row.untiered:
            out.append(("\u2013", False))
        elif not tier_by:
            place[row.group] = place.get(row.group, 0) + 1
            out.append((str(place[row.group]), False))
        else:
            tier = str((row.tiers or {}).get(key, "\u2013"))
            out.append((tier, row.group in last and tier != last[row.group]))
            last[row.group] = tier
    return out


def _group_heads(rows: Sequence[Row], marks: Sequence[str | None]) -> dict[int, bool]:
    """The index of each group's first row (a heading goes before it) and whether the group has an unpinned row in the
    default view (else its heading starts out of view, as zw-ui.js treats it)."""
    first: dict[str, int] = {}
    heads: dict[int, bool] = {}
    for index, (row, mark) in enumerate(zip(rows, marks)):
        if not row.group:
            continue
        if row.group not in first:
            first[row.group] = index
            heads[index] = False
        if mark != "zw-away" and not row.pinned:
            heads[first[row.group]] = True
    return heads


def _phone_lines(columns: Columns, row: Row) -> list[str]:
    """The helper columns' values with their units, for the details box below 600 px."""
    return [f"{esc(column.label)}: {cell}" + (f" {units(column.unit, column.unit_1m)}" if column.unit else "")
            for column, cell in zip(columns.helpers, row.helpers)]


def compact_table(columns: Columns, rows: Sequence[Row], ids: Iterable[str], *, tier_by: Sequence[str] = (),
                  labels: Labels = Labels(), marks: Sequence[str | None] = (), any_values: Mapping[str, str] | None = None,
                  label_id: str | None = None, state: Mapping[str, str | None] | None = None, boxes: Boxes | None = None,
                  row_prefix: str = "zw-row") -> str:
    """rank/tier · model · the measure · two helpers. ids: one unique box id per row, used without boxes (a Boxes:
    one shared box per setup). marks: each row's state class in the default view ('zw-away', 'zw-cut'); state: that
    view's filter values (the ranks and tiers are written for it; None: every parameter at its any-value). Without
    tier_by the rank cell holds the place among the rows in view (1, 2, 3); with it, each row's tier for the chosen
    filters. A row's others follow it as closed sub-rows behind its 'N other settings' key."""
    marks = list(marks) or [None] * len(rows)
    view = dict(state) if state is not None else {name: (any_values or {}).get(name) or "all" for name in tier_by}
    numbers = _numbers(rows, tier_by, view, marks)
    head = (f'<thead><tr>{rank_head(columns, f"{row_prefix}-tip")}<th scope="col">{esc(columns.model)}</th>'
            + head_cell(columns.measure, "zw-measure", f"{row_prefix}-tip-m")
            + "".join(head_cell(column, "zw-help", f"{row_prefix}-tip-{index}") for index, column in enumerate(columns.helpers))
            + "</tr></thead>")
    ids = iter(ids)

    def cells(row: Row, box_id: str, more: str = "") -> str:
        label = row.details_label or f"{row.model.name}: {labels.details_suffix}"
        helpers = "".join(f'<td class="{classes("zw-help", "zw-num" if column.num else None, "zw-keep-phone" if column.phone else None)}">{cell}</td>'
                          for column, cell in zip(columns.helpers, row.helpers))
        phone = [] if boxes is not None else [line for column, line in zip(columns.helpers, _phone_lines(columns, row))
                                              if not column.phone]
        return (model_cell(row.model, box_id, label, row.details, labels, phone, shared=boxes is not None, more=more)
                + f'<td class="zw-measure{" zw-num" if columns.measure.num else ""}">{row.measure}</td>{helpers}')

    body = []
    heads = _group_heads(rows, marks)
    for index, (row, (number, starts), mark) in enumerate(zip(rows, numbers, marks)):
        if index in heads:
            body.append(f'<tr{attrs({"class": classes("zw-group-head", None if heads[index] else "zw-away"), "data-zw-group-head": row.group})}>'
                        f'<th scope="colgroup" colspan="{3 + len(columns.helpers)}">{esc(row.group)}</th></tr>')
        row_id = f"{row_prefix}-{index + 1}"
        box_id = boxes.box(row, labels) if boxes is not None else next(ids)
        tier = " ".join(f"{key}={value}" for key, value in row.tiers.items()) if row.tiers and not row.untiered else None
        sub_ids = [f"{row_id}-{j + 1}" for j in range(len(row.others))]
        more = ""
        if row.others:
            words = (labels.others_one if len(row.others) == 1 else labels.others).format(n=len(row.others))
            more = (f'<button type="button" class="zw-more" aria-expanded="false" aria-controls="{" ".join(sub_ids)}">'
                    f"{esc(words)}</button>")
        body.append(f'<tr{_row_attrs(row, {"id": row_id if row.others else None, "data-zw-box": box_id, "data-zw-tier": tier, "data-zw-untiered": row.untiered, "data-zw-group": row.group or None}, classes(mark, "zw-tier-start" if starts else None))}>'
                    f'<td class="zw-rank">{esc(number)}</td>' + cells(row, box_id, more) + "</tr>")
        for other, sub_id in zip(row.others, sub_ids):
            other_box = boxes.box(other, labels) if boxes is not None else f"{sub_id}-box"
            body.append(f'<tr{_row_attrs(other, {"id": sub_id, "data-zw-of": row_id, "data-zw-box": other_box}, classes("zw-sub zw-sub-closed", mark))}>'
                        '<td class="zw-rank"></td>' + cells(other, other_box) + "</tr>")
    # More than two helpers (v2.6: Grading's every measure side by side): the measure column takes no fixed share of the
    # width, only its minimum, so the helpers' columns fit (zw-ui.css .zw-many); where they still do not (a tablet), the
    # table scrolls inside its own box, never the page (.zw-wide, zw-ui.js wides).
    many = len(columns.helpers) > 2
    table = (f'<table{attrs({"class": classes("zw-table", "zw-many" if many else None), "data-zw-tier-by": " ".join(tier_by) or None, "aria-labelledby": label_id})}>'
             f'{head}<tbody>{"".join(body)}</tbody></table>')
    return f'<div class="zw-wide"><div class="zw-wide-box">{table}</div></div>' if many else table


def bar_chart(rows: Sequence[Row], *, marks: Sequence[str | None] = (), label: str = "",
              numbers: Sequence[tuple[str, bool]] | None = None, tier_by: Sequence[str] = (), axis: Axis | None = None,
              subs: bool = False) -> str:
    """The chart view: one bar per row (its chart Bar; a row without one shows its missing words), filtered and cut as
    the table's rows, colour the model's, under each group's heading; with numbers (Bench.chart_rank), each bar's rank
    or tier before its name; with axis, its ticks under the bars; with subs (Bench.one_list), each row's others as bars
    after it (li.zw-sub), shown in the flat view."""
    marks = list(marks) or [None] * len(rows)
    heads = _group_heads(rows, marks)

    def item(row: Row, cls: str | None, rank_text: str | None) -> str:
        chart = row.chart
        if chart is None:
            track = (f'<span class="zw-bar-missing">{esc(row.missing)}</span>' if row.missing
                     else '<span class="zw-bar zw-bar-plain" aria-hidden="true"></span>')
            text = ""
        else:
            track = _track(chart.share, chart.low, chart.high, row.model.colour, chart.ref, chart.ref_label, chart.second)
            text = esc(chart.text) + (f'<span class="zw-val-second">{esc(chart.second.text)}</span>' if chart.second is not None else "")
        tag = f' <span class="zw-tag">{esc(row.model.tag)}</span>' if row.model.tag else ""
        extra: dict[str, str | bool | None] = {"data-zw-series": row.series or row.model.dot_title or None,
                                               "data-zw-group": row.group or None}
        rank = ""
        if rank_text is not None:
            extra["data-zw-tier"] = (" ".join(f"{key}={value}" for key, value in row.tiers.items())
                                     if row.tiers and not row.untiered else None)
            extra["data-zw-untiered"] = row.untiered
            rank = f'<span class="zw-rank">{esc(rank_text)}</span>'
        return (f'<li{_row_attrs(row, extra, cls)}>{rank}<span class="zw-bar-label">{esc(row.model.name)}{tag}'
                + (f'<span class="zw-flag">{esc(row.model.flag)}</span>' if row.model.flag else "")
                + f'</span>{track}<span class="zw-val">{text}</span></li>')

    items = []
    for index, (row, mark) in enumerate(zip(rows, marks)):
        if index in heads:
            items.append(f'<li{attrs({"class": classes("zw-group-head", None if heads[index] else "zw-away"), "data-zw-group-head": row.group})}>'
                         f"{esc(row.group)}</li>")
        starts = numbers is not None and numbers[index][1]
        items.append(item(row, classes(mark, "zw-tier-start" if starts else None), numbers[index][0] if numbers is not None else None))
        for other in row.others if subs else ():
            items.append(item(other, classes("zw-sub", mark), "" if numbers is not None else None))
    ranked = numbers is not None
    axis_html = ""
    if axis is not None:
        ticks = "".join(f'<span class="zw-tick" style="left:{100 * share:.2f}%">{esc(text)}</span>' for share, text in axis.ticks)
        axis_html = (f'<div{attrs({"class": classes("zw-axis-row", "zw-ranked" if ranked else None)})} aria-hidden="true">'
                     f'<span class="zw-axis-name">{esc(axis.label)}</span><span class="zw-axis">{ticks}</span></div>')
    return (f'<ol{attrs({"class": classes("zw-bars", "zw-ranked" if ranked else None), "data-zw-tier-by": " ".join(tier_by) if ranked and tier_by else None, "aria-label": label or None})}>'
            f'{"".join(items)}</ol>{axis_html}')


def legend(rows: Sequence[Row], shown: Iterable[str], labels: Labels = Labels(), *, subs: bool = False) -> str:
    """The chart's legend: one entry per series (maker) in the list, zw-ui.js keeping only those with a bar in view;
    then the two series of rows that have them (Bar.label: solid, then striped) and each reference mark's words
    (Bar.ref_label), always shown."""
    seen: dict[str, str] = {}
    refs: list[str] = []
    pair: tuple[str, str] | None = None
    for row in [item for row in rows for item in (row, *row.others)] if subs else rows:
        name = row.series or row.model.dot_title
        if name and name not in seen:
            seen[name] = row.model.colour
        if row.chart is not None and row.chart.ref is not None and row.chart.ref_label and row.chart.ref_label not in refs:
            refs.append(row.chart.ref_label)
        if pair is None and row.chart is not None and row.chart.second is not None and row.chart.label:
            pair = (row.chart.label, row.chart.second.label)
    visible = set(shown)
    return (f'<ul class="zw-legend" aria-label="{esc(labels.legend)}">'
            + "".join(f'<li{attrs({"class": None if name in visible else "zw-away", "data-zw-series": name})}>'
                      f'<i class="zw-dot" style="--zw-dot:{esc(colour)}"></i>{esc(name)}</li>' for name, colour in seen.items())
            + ("" if pair is None else
               f'<li class="zw-legend-pair"><i class="zw-pair-key" aria-hidden="true"></i>{esc(pair[0])}</li>'
               f'<li class="zw-legend-pair"><i class="zw-pair-key zw-bar-second" aria-hidden="true"></i>{esc(pair[1])}</li>')
            + "".join(f'<li class="zw-legend-ref"><i class="zw-ref-key" aria-hidden="true"></i>{esc(ref)}</li>' for ref in refs)
            + "</ul>")


def result_list(content: str, *, empty: str, count: int, top: int | None, labels: Labels = Labels(),
                scope: Mapping[str, str] | None = None, away: bool = False, title: str = "", after: str = "",
                cut: int | None = None, flat: str | None = None) -> str:
    """A table or chart with its empty line and its Show all button (count: the rows in the default view; cut: how
    many of them the Top N leaves out, where groups cut on their own); scope: data-<param> of this list
    (data-setups="all"); title: its name without JavaScript, where every list shows."""
    button = ""
    if top:
        more = cut > 0 if cut is not None else count > top
        button = (f'<button type="button"{attrs({"class": classes("zw-key zw-showall", None if more else "zw-away")})} '
                  f'data-zw-text-all="{esc(labels.show_all)}" data-zw-text-top="{esc(labels.show_top)}" aria-expanded="false">'
                  f'{esc(labels.show_all.format(n=count))}</button>')
    return (f'<div{attrs({"class": classes("zw-list", "zw-away" if away else None), **{f"data-{k}": v for k, v in (scope or {}).items()}, "data-zw-top": str(top) if top else None, "data-zw-flat": flat})}>'
            + (f'<h3 class="zw-list-title">{esc(title)}</h3>' if title else "") + content
            + f'<p{attrs({"class": classes("zw-empty", "zw-away" if count else None)})}>{esc(empty)}</p>{button}{after}</div>')


def when_holds(when: str, state: Mapping[str, str | None]) -> bool:
    """Whether a data-zw-when condition holds in a state: 'param=v1,v2' and 'param!=v', joined by ';' (zw-ui.js
    whenHolds). 'param=v1,v2' holds while the state names any of the listed values, so with class 'tiny,small'
    'class=small' holds and 'class!=small' does not; no any-value override ('class!=all' holds while a class is chosen)."""
    for condition in (part.strip() for part in when.split(";")):
        if not condition:
            continue
        negated = "!=" in condition
        name, sep, listed = condition.partition("!=" if negated else "=")
        if not sep:
            continue
        chosen = values(state.get(name.strip()))
        inside = any(value.strip() in chosen for value in listed.split(("!=" if negated else "="))[0].split(","))
        if inside == negated:
            return False
    return True


def note_html(note: str | Note, state: Mapping[str, str | None] | None = None) -> str:
    """A note under the results: a paragraph (a str: its HTML in <p class="zw-note">), or a Note: a block or a closed
    details element, or with raw its own markup as it is; shown only in its filter state (data-zw-when; out of the
    default view when state says so)."""
    if isinstance(note, str):
        return f'<p class="zw-note">{note}</p>'
    away = bool(note.when) and state is not None and not when_holds(note.when, state)
    attr = attrs({"class": classes("zw-note", "zw-note-more" if note.summary else None, "zw-note-raw" if note.raw else None,
                                   "zw-away" if away else None), "data-zw-when": note.when or None})
    if note.summary:
        return f'<details{attr}><summary>{esc(note.summary)}</summary><div class="zw-note-body">{note.html}</div></details>'
    if note.raw and not note.when:
        return note.html
    return f"<div{attr}>{note.html}</div>"


def panel(content: str, scope: Mapping[str, str], away: bool = False, *, title: str = "", sub: str = "", keys: str = "",
          title_id: str | None = None, notes: Sequence[str | Note] = (), state: Mapping[str, str | None] | None = None,
          src: str | None = None) -> str:
    """A result panel: shown while every data-<param> of scope holds (data-part, data-measure), under its own head (its
    title and short scope, the Chart / Table keys), its notes under the results. src: the panel's file (Fragments): a
    stub of it, whose content zw-ui.js replaces with the file's on first show."""
    head = ""
    if title or keys:
        head = (f'<div class="zw-panel-head"><h2 class="zw-panel-title"{attrs({"id": title_id})}>{esc(title)}'
                + (f' <span class="zw-panel-sub">{esc(sub)}</span>' if sub else "") + f"</h2>{keys}</div>")
    return (f'<section{attrs({"class": classes("zw-panel", "zw-lazy" if src else None, "zw-away" if away else None), **{f"data-{k}": v for k, v in scope.items()}, "data-zw-src": src, "aria-labelledby": title_id})}>'
            + head + content + "".join(note_html(note, state) for note in notes) + "</section>")


def _lazy_body(src: str, labels: Labels) -> str:
    """A stub's body: 'Loading…' while its file loads, a line with a reload link if it fails, and without JavaScript a
    link to the file, a page of its own."""
    return (f'<div class="zw-lazy-body"><p class="zw-lazy-loading">{esc(labels.loading)}</p>'
            f'<p class="zw-lazy-failed" hidden>{esc(labels.load_failed)} <a href="">{esc(labels.reload)}</a> · '
            f'<a href="{esc(src)}">{esc(labels.open_panel)}</a></p>'
            f'<p class="zw-lazy-link"><a href="{esc(src)}">{esc(labels.open_panel)}</a></p></div>')


# --- The whole block from an adapter (home.py:414-452 leaderboard) ----------------------------------------------------
def _fits(filters: Mapping[str, str], state: Mapping[str, str | None], any_values: Mapping[str, str | None]) -> bool:
    """Whether an element with these data-<param> values (space-separated) shows in a state (zw-ui.js matches()): the
    state is the param's any-value, or names (comma-separated) any of the element's values."""
    return all(state.get(name) is None or value is None or state[name] == any_values.get(name)
               or any(chosen in str(value).split() for chosen in values(state[name])) for name, value in filters.items())


def results(bench: Bench, *, block_id: str = "zw", box_prefix: str | None = None, fragments: Fragments | None = None,
            url_prefix: str = "") -> str:
    """The whole block: the head (title, scope line), the phone's Filters bar, the filter rows, the Measure keys, one
    panel per part and measure (or per group of parts sharing it, Bench.panel_group), each with its views and a list
    per Rows choice (or one line where the measure is not measured), the details boxes, one per setup, and the cost
    calculations, one per distinct text. Written in the default view: what it hides carries zw-away (zw-cut past the
    Top N), which acts only with JavaScript, and the ranks and tiers are the default view's, so nothing changes on
    load; without JavaScript every panel, view, list, row and box shows. With Bench.lazy_panels (opt-in) and fragments
    (a Fragments), only the default view's panel(s) are in the page and every other panel is a page of its own, loaded on
    first show; the site writes the files (fragments.write) beside the page. With Bench.one_list (opt-in), each panel
    has one list, the default Rows choice's with its sub-rows, which the other Rows choice shows flat (zw-ui.js)."""
    labels = bench.labels
    filters = bench.filter_rows()
    by_param = {row.param: row for row in filters}
    measures = bench.measure_keys()
    parts = [key.value for key in by_param["part"].keys] if "part" in by_param else [None]
    setups_values = [key.value for key in by_param["setups"].keys] if "setups" in by_param else [None]
    measure_values = [key.value for key in measures.keys] if measures else [None]
    # A default of several keys ('tiny,small') is supported only on a row with an any-value (Models, Class), as in the
    # address (zw-ui.js); each must be one of the row's keys. Anything else stops the build.
    for row in [*filters, *([measures] if measures else [])]:
        chosen = row.chosen_values
        if len(chosen) > 1 and (row.any is None or any(value not in [key.value for key in row.keys] for value in chosen)):
            raise ValueError(f"zw_ui.results: KeyRow {row.param!r} default {row.chosen!r}: several keys at once only on a row "
                             "with an any-value, each one of its keys")
    default = {row.param: row.chosen for row in filters}
    if measures:
        default[MEASURE] = measures.chosen
    any_values = {row.param: row.any for row in filters}
    top = bench.top
    view_default = bench.default_view
    boxes = Boxes(box_prefix or f"{block_id}-box")
    calcs = Calcs(f"{block_id}-calc")
    inline_boxes: set[str] = set()
    inline_calcs: set[str] = set()
    # Panels loaded on first show only where the adapter opts in (Bench.lazy_panels), into the given Fragments.
    lazy = bool(getattr(bench, "lazy_panels", False))
    one_list = bool(getattr(bench, "one_list", False))  # one list per panel, the other Rows choice shown flat
    if lazy and fragments is None:
        raise ValueError("zw_ui.results: Bench.lazy_panels needs fragments=Fragments(...) to write the panels' pages")
    pages: dict[tuple[str | None, str | None], str] = {}  # each panel's place: its id in the page, or its own page
    # A key of a hide_empty row with no row in the default view (zw-ui.js hides it the same way after every change),
    # unless the view has no rows at all (a panel that is not measured), where every key stays.
    present: dict[str, set[str]] = {row.param: set() for row in filters if row.hide_empty}
    base: dict[str, int] = {param: 0 for param in present}
    panels = []
    for measure in measure_values:
        groups: dict[object, list[str | None]] = {}
        for part in parts:
            groups.setdefault(bench.panel_group(part, measure) or part, []).append(part)
        for group_parts in groups.values():
            part = group_parts[0]
            views = [view for view in bench.views(part, measure) if view in VIEWS] or ["table"]
            shown_panel = default.get("part") in group_parts and measure == default.get(MEASURE)
            view_lists: dict[str, list[str]] = {view: [] for view in views}
            tier_by = bench.tier_by(part, measure)
            pid = f"{block_id}-{part or 'all'}-{measure or 'all'}"
            view_row = KeyRow(VIEW, labels.view, [Key(view, getattr(labels, view)) for view in views],
                              default=view_default if view_default in views else views[0])
            measured = bench.measured(part, measure)
            # One list (Bench.one_list, opt-in): the default Rows choice's rows with their sub-rows, every setup of the
            # other Rows choice placed in it (data-zw-flat-*), which zw-ui.js shows flat for that choice.
            one = one_list and len(setups_values) == 2 and None not in setups_values
            flat_value = next(value for value in setups_values if value != default.get("setups")) if one else None
            for setups in ([default.get("setups")] if one else setups_values) if measured else []:
                rows = bench.rows(part, measure, setups)
                if one:
                    rows = _one_list(rows, bench.rows(part, measure, flat_value), str(flat_value), labels)
                in_list = setups == default.get("setups")
                marks: list[str | None] = []
                shown, cut_count, series = 0, 0, set()
                in_group: dict[str, int] = {}
                for row in rows:
                    if shown_panel and in_list and not row.pinned:
                        for param in present:
                            if _fits(row.filters, {**default, param: any_values.get(param)}, any_values):
                                base[param] += 1
                    if row.pinned:  # a reference row: in view while its filters hold, never counted or cut
                        marks.append(None if _fits(row.filters, default, any_values) else "zw-away")
                        if marks[-1] is None:
                            series.add(row.series or row.model.dot_title)
                        continue
                    if not _fits(row.filters, default, any_values):
                        marks.append("zw-away")
                        if shown_panel and in_list:
                            for param in present:
                                if _fits(row.filters, {**default, param: row.filters.get(param)}, any_values):
                                    present[param].add(str(row.filters.get(param)))
                        continue
                    if shown_panel and in_list:
                        for param in present:
                            present[param].add(str(row.filters.get(param)))
                    shown += 1
                    in_group[row.group] = in_group.get(row.group, 0) + 1
                    cut = bool(top) and in_group[row.group] > top  # each group cut to Top N on its own
                    cut_count += cut
                    marks.append("zw-cut" if cut else None)
                    if not cut:
                        series.add(row.series or row.model.dot_title)
                title = next((key.label for key in by_param["setups"].keys if key.value == setups), "") if setups and not one else ""
                scope = {"setups": setups} if setups is not None and not one else None
                for view in views:
                    if view == "table":
                        content = compact_table(bench.columns(part, measure), rows, (), tier_by=tier_by, labels=labels,
                                                marks=marks, label_id=f"{pid}-title", state=default, boxes=boxes,
                                                row_prefix=f"{pid}-{setups or 'rows'}")
                        after = ""
                    else:
                        ranked = bench.chart_rank(part, measure)
                        content = bar_chart(rows, marks=marks, label=bench.panel_title(part, measure)[0],
                                            numbers=_numbers(rows, tier_by, default, marks) if ranked else None,
                                            tier_by=tier_by, axis=bench.axis(part, measure), subs=one)
                        after = legend(rows, series, labels, subs=one)
                    view_lists[view].append(result_list(content, empty=bench.empty_text(part, measure), count=shown, top=top,
                                                        labels=labels, scope=scope, away=setups is not None and not in_list,
                                                        title=title if len(setups_values) > 1 else "", after=after,
                                                        cut=cut_count, flat=flat_value))
            keys = ""
            if not measured:
                content = f'<p class="zw-not-measured">{esc(bench.empty_text(part, measure))}</p>'
            elif len(views) > 1:
                keys = key_row(view_row, label_id=f"{pid}-view", cls="zw-viewkeys")
                content = "".join(f'<div{attrs({"class": classes("zw-view", None if view == view_row.chosen else "zw-away"), "data-view": view})}>'
                                  + "".join(view_lists[view]) + "</div>" for view in views)
            else:
                content = '<div class="zw-view">' + "".join(view_lists[views[0]]) + "</div>"
            scope = {**({"part": " ".join(str(p) for p in group_parts)} if part is not None else {}),
                     **({MEASURE: measure} if measure is not None else {})}
            title, sub = bench.panel_title(part, measure)
            panel_calcs: set[str] = set()
            panel_boxes = set(boxes.used)
            boxes.used = set()
            full = calcs.share(panel(content, scope, away=not shown_panel, title=title, sub=sub, keys=keys,
                                     title_id=f"{pid}-title", notes=bench.notes(part, measure), state=default), panel_calcs)
            if not lazy or shown_panel:
                panels.append(full)
                inline_boxes |= panel_boxes
                inline_calcs |= panel_calcs
                pages.update({(p, measure): f"#{pid}-title" for p in group_parts})
                continue
            # Outside the default view (lazy_panels): a stub in the page, the panel in a page of its own with the bench's
            # title, the part's scope line, a link back to the main view in the same state, and the boxes and
            # calculations its rows refer to.
            box_calcs: set[str] = set()
            box_html = calcs.share(boxes.section(labels, panel_boxes), box_calcs)
            query = "&".join(f"{name}={value}" for name, value in (("part", part), (MEASURE, measure))
                             if value is not None and value != default.get(name))
            page_head = (f'<header class="zw-pagehead"><h1 class="zw-title">{esc(bench.title())}</h1>'
                         + (f'<p class="zw-scope">{esc(bench.scope(part))}</p>' if bench.scope(part) else "")
                         + f'<p class="zw-back"><a href="{esc(fragments.page + (f"?{query}" if query else ""))}">'
                         f"{esc(labels.back)}</a></p></header>")
            src = fragments.add(pid, " · ".join(text for text in (title, sub, bench.title()) if text), full,
                                box_html + calcs.section(labels, panel_calcs | box_calcs), page_head)
            pages.update({(p, measure): src for p in group_parts})
            panels.append(calcs.share(panel(_lazy_body(src, labels), scope, away=True, title=title, sub=sub, keys=keys,
                                            title_id=f"{pid}-title", src=src)))
    hidden_keys = {param: [key.value for key in by_param[param].keys if key.value != by_param[param].any
                           and key.value not in by_param[param].chosen_values and key.value not in found]
                   for param, found in present.items() if base[param]}
    scope_lines = "".join(f'<span{attrs({"class": classes("zw-scope-part", None if part == default.get("part") else "zw-away"), "data-part": part})}>'
                          f"{esc(bench.scope(part))}</span>" for part in parts if bench.scope(part)) if parts != [None] else esc(bench.scope(None))
    head = (f'<header class="zw-pagehead"><h1 class="zw-title" id="{esc(block_id)}-title">{esc(bench.title())}</h1>'
            + (f'<p class="zw-scope">{scope_lines}</p>' if scope_lines else "") + "</header>")
    filters_id = f"{block_id}-filters"
    anchors = bench.anchors()
    main_calcs: set[str] = set()
    box_html = calcs.share(boxes.section(labels, inline_boxes if lazy else None), main_calcs)
    # Without JavaScript (lazy_panels), the Measure keys as links: each measure's panel of the default part, its own page.
    nojs = ""
    if lazy and measures:
        nojs = (f'<nav class="zw-nojs-measures" aria-label="{esc(measures.label)}"><span class="zw-row-label">{esc(measures.label)}</span>'
                + "".join(f'<a class="zw-key" href="{esc(pages.get((default.get("part"), key.value), ""))}"'
                          f'{attrs({"aria-current": "page" if key.value == measures.chosen else None})}>{esc(key.label)}</a>'
                          for key in measures.keys if (default.get("part"), key.value) in pages) + "</nav>")
    return (f'<section class="zw-block" id="{esc(block_id)}" aria-labelledby="{esc(block_id)}-title"'
            f'{attrs({"data-zw-anchors": json.dumps(anchors, separators=(",", ":")) if anchors else None, "data-zw-top": str(top) if top and lazy else None, "data-zw-prefix": url_prefix or None})}>'
            + head + (filter_bar(filters, filters_id, labels)
                      + filter_rows(filters, filters_id, hidden_keys, label_prefix=f"{block_id}-label") if filters else "")
            + (key_row(measures, label_id=f"{block_id}-label-{measures.param}") if measures else "") + nojs
            + '<div class="zw-results">' + "".join(panels) + "</div>"
            + box_html + calcs.section(labels, inline_calcs | main_calcs if lazy else None) + "</section>")
