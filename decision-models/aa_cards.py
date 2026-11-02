#!/usr/bin/env python3
"""The four reply charts of aa-decision-index/: our answers, card by card, to Artificial Analysis's thread on SubQ Snap
1.1 (22 October 2026), from the same data as that page: results.json, vision.json and page_config.json's
aa_decision_index (Artificial Analysis's models, by run id).

  1. Accuracy on the Text tab             (Artificial Analysis: its Decision Index)
  2. Non-hallucination rate, "Bilmiyorum" (Artificial Analysis: AA-Omniscience-Decision's non-hallucination rate)
  3. Cost per 1M questions                (Artificial Analysis: cost per 1M tasks)
  4. Score by part                        (Artificial Analysis: score by benchmark)

The numbers are written as the page writes them: percentages to one decimal, and the cost per 1,000 questions as the site
rounds it, times 1,000. Each card is an SVG that headless Chrome (CHROME, else google-chrome, as build_page.py draws the
link preview) turns into aa-decision-index/card-<n>-<topic>-<hash>.png at 2048 × 912; aa-decision-index/cards.json names
the files with the results version they were drawn from, and the page shows them only at that version (the build stops
otherwise). build_site.py draws them with the link preview; without Chrome, `build_site.py --no-images` keeps them.
Text is measured with Pillow in the cards' first font, Noto Sans (found by fontconfig; CARD_FONT overrides).

Usage: python3 aa_cards.py"""

from __future__ import annotations

import hashlib
import html
import json
import os
import subprocess
import tempfile
from functools import cache
from math import log10
from pathlib import Path
from typing import Any

from PIL import ImageFont

import build_page as bp

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "aa-decision-index"
MANIFEST = OUT / "cards.json"
URL = "zekiworks.github.io/analysis/decision-models/aa-decision-index"
# Our label where it differs from Artificial Analysis's name for the model.
LABELS = {"Elephant 9B": "Elephant-1 (9B)", "d1": "d1 (free tier)"}
# Each card: its topic (in its file name) and the card of Artificial Analysis's thread it answers.
CARDS = (("accuracy", "Artificial Analysis Decision Index"), ("non-hallucination", "AA-Omniscience-Decision: Non-Hallucination Rate"),
         ("cost", "Artificial Analysis Decision Index: Cost per 1M Tasks"), ("score-by-part", "Artificial Analysis Decision Index: Score by Benchmark"))
# The site's light theme (v3.css). Card 4's series: the site's reading blue and grammar orange, then two colours that are
# not the site's red (kept but wrong) or green (kept and right).
PANEL, TEXT, TEXT_2, EDGE, MARK_EDGE = "#f7f6f2", "#23221f", "#4b4944", "#cbc7bf", "#7c7871"
SERIES = (("Reading", "#2563eb"), ("Grammar", "#ea580c"), ("Page images, picture alone", "#0d9488"), ("Non-hallucination rate", "#7c3aed"))
W, H, ZOOM = 1024, 456, 2
LEFT, RIGHT, BASE = 64, W - 28, 272
GPU = "†"
esc = html.escape


@cache
def data() -> dict[str, Any]:
    """The results, the page images and page_config.json, with the lookups the cards use."""
    results = json.loads((ROOT / "results.json").read_text())
    vision = json.loads((ROOT / "vision.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "page_config.json").read_text())
    by_id = {run["run"]: run for run in results["runs"]}
    models = config["aa_decision_index"]["models"]
    return {
        "results": results, "config": config, "scale": config["rank_scale"]["stops"],
        "decision": [run for run in results["runs"]
                     if run["provider"] in config["decision_model_providers"] and run["model"] not in config["not_decision_models"]],
        "ours": [by_id[item["run"]] for item in models if item["run"] is not None],
        "aa_name": {item["run"]: item["name"] for item in models if item["run"] is not None},
        "absent": [item["name"] for item in models if item["run"] is None],
        "held": {model["original_run"]: model for model in results["dont_know"]["models"]},
        "pages": {(model["provider"], model["model"]): model for model in vision["models"]},
        "prices": {(price["provider"], price["model"]): price for price in results["prices"]},
        "maker": config["first_cost_marks"]["maker"]["mark"],
    }


@cache
def font() -> str:
    found = os.environ.get("CARD_FONT") or subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans:style=Regular"],
                                                          capture_output=True, text=True, check=True).stdout
    if not found or not Path(found).is_file():
        raise SystemExit("aa_cards.py: no Noto Sans font file (install it, or set CARD_FONT to a font file)")
    return found


def text_width(text: str, size: float) -> float:
    return ImageFont.truetype(font(), size).getlength(text)


def wrap(text: str, width: float = W - 56, size: float = 11.5) -> list[str]:
    """A note's words in lines no wider than width at size px."""
    lines, line = [], ""
    for word in text.split(" "):
        longer = f"{line} {word}" if line else word
        if line and text_width(longer, size) > width:
            lines.append(line)
            line = word
        else:
            line = longer
    return lines + [line] if line else lines


def joined(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def accuracy(run: dict[str, Any]) -> float:
    groups = run["groups"]
    return (groups["reading"]["correct"] + groups["grammar"]["correct"]) / (groups["reading"]["questions"] + groups["grammar"]["questions"])


def part(run: dict[str, Any], name: str) -> float:
    return run["groups"][name]["correct"] / run["groups"][name]["questions"]


def cost_per_1000(run: dict[str, Any]) -> float | None:
    return None if run["api_equivalent_usd"] is None else 1000 * run["api_equivalent_usd"] / run["answered_questions"]


def page_entry(run: dict[str, Any]) -> dict[str, Any] | None:
    return data()["pages"].get((run["provider"], run["model"]))


def picture_alone(run: dict[str, Any]) -> float | None:
    condition = (page_entry(run) or {}).get("conditions", {}).get("B")
    return None if condition is None else condition["accuracy"]


def name(run: dict[str, Any], mark: str = "") -> str:
    aa = data()["aa_name"][run["run"]]
    return LABELS.get(aa, aa) + (f" {mark}" if mark else "")


def gpu(run: dict[str, Any]) -> str:
    return GPU if run["billing"] == "local" else ""


def rank_color(value: float, worst: float, best: float, log: bool = False) -> str:
    """The site's rankColor: the ranking scale between the worst and best ends, linear in RGB."""
    scale = data()["scale"]
    at = log10 if log else (lambda item: item)
    span = at(best) - at(worst)
    share = 1 if not span else min(1, max(0, (at(value) - at(worst)) / span))
    place = share * (len(scale) - 1)
    index = min(len(scale) - 2, int(place))
    low, high = ([int(color[i:i + 2], 16) for i in (1, 3, 5)] for color in scale[index:index + 2])
    return "#" + "".join(f"{round(a + (b - a) * (place - index)):02x}" for a, b in zip(low, high))


def absent_note() -> str:
    absent = data()["absent"]
    return f"{joined(absent)} {'is' if len(absent) == 1 else 'are'} not in our benchmark." if absent else ""


def frame(title: str, subtitle: list[str], body: str, notes: list[str], legend: str = "") -> str:
    """A card: title, subtitle and our name at the top, the chart, then its notes and the source page's address."""
    parts = [f'<rect width="{W}" height="{H}" fill="{PANEL}"/>', f'<text x="28" y="46" class="title">{esc(title)}</text>']
    parts += [f'<text x="28" y="{72 + 18 * i}" class="sub">{esc(line)}</text>' for i, line in enumerate(subtitle)]
    parts += [f'<text x="{W - 28}" y="44" class="brand" text-anchor="end">Hilde · Decision models</text>', legend, body]
    lines = [line for note in notes for line in wrap(note)] + [f"Source: {URL}"]
    parts += [f'<text x="28" y="{H - 14 - 16 * (len(lines) - 1 - i)}" class="{"url" if i == len(lines) - 1 else "note"}">{esc(line)}</text>'
              for i, line in enumerate(lines)]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W * ZOOM}" height="{H * ZOOM}" viewBox="0 0 {W} {H}">'
            f'<style>{STYLE}</style>{"".join(parts)}</svg>')


def grid(top: float, steps: int = 4) -> str:
    return "".join(f'<line class="grid" x1="{LEFT}" x2="{RIGHT}" y1="{BASE - (BASE - top) * i / steps:.1f}" y2="{BASE - (BASE - top) * i / steps:.1f}"/>'
                   for i in range(1, steps + 1)) + f'<line class="axis" x1="{LEFT}" x2="{RIGHT}" y1="{BASE}" y2="{BASE}"/>'


def label(x: float, text: str) -> str:
    return f'<text class="label" text-anchor="end" transform="translate({x:.1f} {BASE + 14}) rotate(-45)">{esc(text)}</text>'


def bars(rows: list[tuple[str, float, str]], top: float, high: float, text: Any) -> str:
    """One bar per row (label, value, colour), on a linear axis from 0 to high, its value above it."""
    slot = (RIGHT - LEFT) / len(rows)
    width = slot * 0.6
    parts = [grid(top)]
    for i, (text_label, value, color) in enumerate(rows):
        x = LEFT + slot * i + (slot - width) / 2
        y = BASE - (BASE - top) * value / high
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{BASE - y:.1f}" rx="2" fill="{color}" stroke="{MARK_EDGE}" stroke-width=".75"/>')
        parts.append(f'<text class="value" x="{x + width / 2:.1f}" y="{y - 7:.1f}" text-anchor="middle">{esc(text(value))}</text>')
        parts.append(label(x + width / 2 + 4, text_label))
    return "".join(parts)


def card_accuracy() -> str:
    d = data()
    decision = [accuracy(run) for run in d["decision"]]
    worst, best = min(decision), max(decision)
    rows = sorted(((name(run, gpu(run)), round(100 * accuracy(run), 1), rank_color(accuracy(run), worst, best)) for run in d["ours"]),
                  key=lambda row: -row[1])
    total = d["results"]["questions"]
    glide = [run for run in d["ours"] if run["provider"] == "fastino"]
    hosted = [f"{name(run)}: Fastino's hosted model as it answered on {bp.long_date(run['started'][:10])}." for run in glide]
    return frame("Turkish Question Bank: Accuracy",
                 [f"Share of {total:,} questions answered correctly, on a reading comprehension and grammar test in native",
                  "Turkish (not translated); five options, one question per request · Higher is better"],
                 bars(rows, 112, 100, lambda value: f"{value:.1f}"),
                 [" ".join([f"{GPU} Run on our GPU from the released weights.", *hosted, absent_note()])])


def card_non_hallucination() -> str:
    d = data()
    ran = sorted((run for run in d["ours"] if run["run"] in d["held"]), key=lambda run: -d["held"][run["run"]]["non_hallucination"])
    values = [d["held"][run["run"]]["non_hallucination"] for run in ran]
    rows = [(name(run, gpu(run)), round(100 * value, 1), rank_color(value, min(values), max(values))) for run, value in zip(ran, values)]
    not_run = [d["aa_name"][run["run"]] for run in d["ours"] if run["run"] not in d["held"]]
    several = [name(run) for run in ran if len(d["held"][run["run"]]["runs"]) > 1]
    option = d["results"]["dont_know"]["option"]
    return frame("Turkish Question Bank: Non-Hallucination Rate",
                 [f"Share of “{option}” (“I don't know”) among the answers that were not right, with it offered as a",
                  "sixth option · Higher is better"],
                 bars(rows, 112, 100, lambda value: f"{value:.1f}"),
                 [f"The {len(ran)} of AA's models we ran with the option. Not run with it: {', '.join(not_run)}. {absent_note()} "
                  f"{GPU} Run on our GPU from the released weights."
                  + (f" {joined(several)}: the first of their five runs, as on our site." if several else "")])


def card_cost() -> str:
    d = data()
    decision = [value for value in map(cost_per_1000, d["decision"]) if value is not None]
    worst, best = max(decision), min(decision)
    # In the order of the exact estimates, as the source page lists them; the labels show them as the site rounds them.
    priced = sorted((run for run in d["ours"] if cost_per_1000(run) is not None), key=lambda run: (cost_per_1000(run), run["name"].casefold()))
    rows = [(name(run, d["maker"] if run["cost_basis"] == "maker" else ""), round(cost_per_1000(run), 3) * 1000,
             rank_color(cost_per_1000(run), worst, best, log=True)) for run in priced]
    high = max(value for _, value, _ in rows) * 1.15
    makers = joined(sorted({d["prices"][(run["provider"], run["model"])]["basis"].split("'s list price")[0]
                            for run in priced if run["cost_basis"] == "maker"}))
    notes = [f"{d['maker']} Run on our GPU, priced at its maker's list price for the same model ({makers})."]
    for run in priced:
        price = d["prices"].get((run["provider"], run["model"]))
        if run["billing"] == "free":
            notes.append(f"{name(run).split(' (')[0]}: its free tier, priced at {price['basis']}.")
        if price and price.get("change"):
            notes.append(f"{name(run)}: at the price recorded on {bp.long_date(price['date'])}. Provider update: {price['change']}.")
    return frame("Turkish Question Bank: Cost per 1M Questions",
                 ["Estimated from list prices and recorded token use, in USD per 1 million questions (our site gives",
                  "the same estimates per 1,000 questions) · Lower is better"],
                 bars(rows, 112, high, lambda value: f"${value:,.0f}"),
                 [" ".join([*notes, absent_note()])])


def card_parts() -> str:
    d = data()
    ours = sorted(d["ours"], key=lambda run: -accuracy(run))
    top = 144
    slot = (RIGHT - LEFT) / len(ours)
    width = slot * 0.8 / len(SERIES)
    parts = [grid(top)]
    for i, run in enumerate(ours):
        held = d["held"].get(run["run"])
        values = [part(run, "reading"), part(run, "grammar"), picture_alone(run), held["non_hallucination"] if held else None]
        start = LEFT + slot * i + slot * 0.1
        for j, ((_, color), value) in enumerate(zip(SERIES, values)):
            x = start + width * j
            if value is None:
                parts.append(f'<text class="missing" x="{x + width / 2:.1f}" y="{BASE - 4}" text-anchor="middle">–</text>')
                continue
            y = BASE - (BASE - top) * value
            parts.append(f'<rect x="{x + 0.5:.1f}" y="{y:.1f}" width="{width - 1:.1f}" height="{BASE - y:.1f}" rx="1.5" fill="{color}"/>')
            parts.append(f'<text class="small-value" transform="translate({x + width / 2 + 3.5:.1f} {y - 4:.1f}) rotate(-90)">{100 * value:.1f}</text>')
        parts.append(label(start + slot * 0.4 + 4, name(run, gpu(run))))
    legend, x = [], 28
    for text, color in SERIES:
        legend.append(f'<circle cx="{x + 6}" cy="113" r="6" fill="{color}"/><text x="{x + 18}" y="118" class="legend">{esc(text)}</text>')
        x += 18 + text_width(text, 13) + 28
    paged = sum(picture_alone(run) is not None for run in ours)
    held = sum(run["run"] in d["held"] for run in ours)
    text_only = [name(run) for run in ours if (page_entry(run) or {}).get("kind") == "text"]
    groups = d["results"]["runs"][0]["groups"]
    pictures = next(iter(d["pages"].values()))["conditions"]["A"]["questions"]
    return frame("Turkish Question Bank: Score by Part",
                 [f"Accuracy on the reading ({groups['reading']['questions']:,}) and grammar ({groups['grammar']['questions']:,}) questions and on page images from the picture alone",
                  f"({pictures:,}), and the non-hallucination rate with “{d['results']['dont_know']['option']}” · Higher is better"],
                 "".join(parts),
                 [f"– Not measured: page images for {len(ours) - paged} of the {len(ours)}"
                  + (f" ({joined(text_only)} {'takes' if len(text_only) == 1 else 'take'} no image input)" if text_only else "")
                  + f", the non-hallucination rate for {len(ours) - held}. {GPU} Run on our GPU from the released weights. {absent_note()}"],
                 legend="".join(legend))


STYLE = f"""
text {{ font-family: "Noto Sans", "Liberation Sans", Arial, sans-serif; fill: {TEXT}; }}
.title {{ font-size: 26px; font-weight: 650; }}
.sub {{ font-size: 14px; fill: {TEXT_2}; }}
.brand {{ font-size: 15px; font-weight: 650; }}
.url, .note, .missing {{ font-size: 11.5px; fill: {TEXT_2}; }}
.value {{ font-size: 13px; font-weight: 650; }}
.small-value {{ font-size: 10.5px; fill: {TEXT_2}; }}
.label {{ font-size: 12.5px; }}
.legend {{ font-size: 13px; }}
.grid {{ stroke: {EDGE}; stroke-dasharray: 2 4; }}
.axis {{ stroke: {MARK_EDGE}; }}
"""


def cards() -> list[tuple[str, str, str, str]]:
    """Each card: its topic, its title, the card of Artificial Analysis's it answers, and its SVG."""
    svgs = [card_accuracy(), card_non_hallucination(), card_cost(), card_parts()]
    titles = [svg.split('class="title">', 1)[1].split("<", 1)[0] for svg in svgs]
    return [(topic, html.unescape(title), answers, svg) for (topic, answers), title, svg in zip(CARDS, titles, svgs)]


def draw() -> None:
    """Draw the cards with headless Chrome into OUT, replacing the earlier ones, and write MANIFEST."""
    chrome = os.environ.get("CHROME", "google-chrome")
    drawn = cards()
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    with tempfile.TemporaryDirectory() as work:
        for number, (topic, title, answers, svg) in enumerate(drawn, 1):
            source, shot = Path(work) / f"{topic}.html", Path(work) / f"{topic}.png"
            source.write_text(f'<!doctype html><meta charset="utf-8"><body style="margin:0;background:{PANEL}">{svg}</body>', encoding="utf-8")
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={work}/profile",
                            "--force-device-scale-factor=1", "--hide-scrollbars", f"--window-size={W * ZOOM},{H * ZOOM}", f"--screenshot={shot}",
                            source.as_uri()], check=True, capture_output=True)
            if bp.png_size(shot) != (W * ZOOM, H * ZOOM):
                raise SystemExit(f"aa_cards.py: {topic} is {bp.png_size(shot)}, not {W * ZOOM}x{H * ZOOM}")
            image = shot.read_bytes()
            entries.append({"file": f"card-{number}-{topic}-{hashlib.sha256(image).hexdigest()[:8]}.png", "title": title, "answers": answers,
                            "image": image})
    for old in OUT.glob("card-*.png"):
        old.unlink()
    for entry in entries:
        path = OUT / entry["file"]
        path.write_bytes(entry.pop("image"))
        os.chmod(path, 0o644)
        print(f"Wrote {path.relative_to(ROOT)} ({W * ZOOM}x{H * ZOOM})")
    MANIFEST.write_text(json.dumps({"results_version": data()["results"]["results_version"], "width": W * ZOOM, "height": H * ZOOM,
                                    "cards": entries}, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    draw()
