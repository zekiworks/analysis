"""Data: the downloads, the results changelog (rendered from results-changelog.md), the answer key changelog (rendered
from key-changelog.md), how to cite (build_page.py's CITATION.cff text) and the licences."""

from __future__ import annotations

import hashlib
import re

import build_page as bp
from sitebuild.questions import PICKS
from sitebuild.site import ROOT, Site, esc, more_link, rel
from sitebuild.vision import joined

PATH = "data/"
CODE_URL = "https://github.com/zekiworks/analysis/tree/main/decision-models"
BLOB_URL = "https://github.com/zekiworks/analysis/blob/main/decision-models/"


def inline(text: str) -> str:
    """Markdown's inline marks in key-changelog.md: code, bold and links (a repo file links to GitHub)."""
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(f"<code>{esc(part[1:-1])}</code>")
            continue
        part = esc(part, quote=False)
        part = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", part)
        part = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                      lambda m: f'<a href="{m.group(2) if "://" in m.group(2) else BLOB_URL + m.group(2)}">{m.group(1)}</a>', part)
        out.append(part)
    return "".join(out)


def markdown(text: str) -> str:
    """The subset of Markdown key-changelog.md uses: headings, paragraphs, lists and tables. Its title is dropped; the
    page gives its own."""
    blocks = re.split(r"\n\s*\n", text.strip())
    out = []
    for block in blocks:
        lines = block.splitlines()
        if lines[0].startswith("# "):
            continue
        if lines[0].startswith("## "):
            out.append(f"<h3>{inline(lines[0][3:])}</h3>")
            lines = lines[1:]
            if not lines:
                continue
        if all(line.startswith("|") for line in lines):
            rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
            head, body = rows[0], [row for row in rows[2:]]
            out.append(
                '<div class="table-wrap"><table class="board list"><thead><tr>'
                + "".join(f'<th scope="col">{inline(cell)}</th>' for cell in head)
                + "</tr></thead><tbody>"
                + "".join("<tr>" + "".join(f'<td data-label="{esc(head[i])}">{inline(cell)}</td>' for i, cell in enumerate(row)) + "</tr>"
                          for row in body)
                + "</tbody></table></div>"
            )
            if not body:
                out.append('<p class="note">No rows yet.</p>')
        elif all(line.startswith("- ") for line in lines):
            out.append("<ul>" + "".join(f"<li>{inline(line[2:])}</li>" for line in lines) + "</ul>")
        else:
            out.append(f"<p>{inline(' '.join(line.strip() for line in lines))}</p>")
    return "\n".join(out)


def size(path) -> str:
    megabytes = path.stat().st_size / 1e6
    return f"{megabytes:.1f} MB" if megabytes >= 1 else f"{path.stat().st_size / 1e3:.0f} kB"


# What each section that answers.json keeps in a file of its own holds, for that file's line (answers.json `files`).
SECTION_WORDS = {"repeat_runs": "the repeat runs of each repeated setup (the Stability tab's), each with its repeat set",
                 "repeat_check_runs": "the Experiments page's repeat checks' Text and English repeat runs, each with its "
                                      "first run",
                 "english_runs": "the English reading runs on the kept questions",
                 "english_dont_know_runs": "the English \u201cI don't know\u201d runs",
                 "english_dont_know_turkish_runs": "their Turkish counterparts on the kept questions"}


def build(site: Site) -> dict[str, str]:
    results = site.results
    parts = site.answers.get("files", {})
    unknown = sorted({section for sections in parts.values() for section in sections} - SECTION_WORDS.keys())
    if unknown:
        raise SystemExit(f"data.py: name what {', '.join(unknown)} holds in SECTION_WORDS")
    elsewhere = joined([f"{'; '.join(SECTION_WORDS[section] for section in sections)}, are in {name}"
                        for name, sections in parts.items()]) if parts else ""
    files = (
        (ROOT / "results.json", rel(PATH, "results.json"),
         "Every published number: each setup's accuracy, confidence, latency and cost, and the routing replays and live tests."),
        (ROOT / "answers.json", rel(PATH, "answers.json"),
         "Every answer of every run, with its score and option probabilities, and the prompts. No question text."
         + (f" {elsewhere[:1].upper()}{elsewhere[1:]}, which it lists under files; reproduce.py reads them together."
            if parts else "")),
        *((ROOT / name, rel(PATH, name),
           f"The part of answers.json kept in a file of its own, under GitHub's file size limit: "
           f"{'; '.join(SECTION_WORDS[section] for section in sections)} ({', '.join(sections)}), with answers.json's "
           "schema version and dataset, so it reads on its own.") for name, sections in parts.items()),
        (PICKS, rel(PATH, "data/picks.json"),
         "Built from answers.json for these pages: each leaderboard setup's pick and score on each scored question, and "
         "each English setup's English pick and score on each kept reading question."),
        (ROOT / "vision.json", rel(PATH, "vision.json"),
         "The Page images test: the questions that depend on the printed page, asked as text, as page images and through "
         "OCR; every number and each answer's pick and option probabilities. No question text, page image or OCR text."),
        (ROOT / "vision-repeats.json", rel(PATH, "vision-repeats.json"),
         "The Page images test's repeat passes, kept outside its table: each pass's run records and answers, compared with "
         "the table's first pass."),
        (ROOT / "english-reading.json", rel(PATH, "english-reading.json"),
         "The record of the English reading and English and Turkish pages: the translator, its two prompts, each reading question's flags and the "
         "SHA-256 of its English text. No question text."),
        (ROOT / "web-grounding.json", rel(PATH, "web-grounding.json"),
         "The Web grounding page's inputs beside answers.json: each run's input tokens by group, what the grounded "
         "searches returned (sites and source checks, as counts and question IDs) and PWS-Decisions' aggregates. No question "
         "text, page address or snippet."),
        (ROOT / "pws-decisions.json", rel(PATH, "pws-decisions.json"),
         "The PWS-Decisions page's totals: each decision model's three runs on Parallel's benchmark of dated web facts, "
         "with request times, cost and confidence. No question or answer."),
    )
    downloads = "".join(
        f'<tr><td class="model"><a href="{href}" download>{esc(path.name)}</a></td><td data-label="Contents">{esc(text)}</td>'
        f'<td class="num" data-label="Size">{size(path)}</td></tr>'
        for path, href, text in files
    )
    citation = bp.citation(site.snapshot, site.values)
    key = results["answer_key"]
    picks_hash = hashlib.sha256(PICKS.read_bytes()).hexdigest()[:12]
    site.note(PATH, "Data", "<p>Everything the pages show comes from these files. They hold aggregate numbers and every "
              "answer, but not the questions: the publisher owns them.</p>")
    body = f"""    <section class="card">
      <h1>Data</h1>
      <div class="table-wrap"><table class="board list"><thead><tr><th scope="col">File</th><th scope="col">Contents</th><th scope="col" class="num">Size</th></tr></thead><tbody>{downloads}</tbody></table></div>
      <p class="note">Everything the pages show comes from these files.</p>
      {more_link(PATH)}
      <p class="note">Results version {esc(results["results_version"])} (what changed: the <a href="#results-changelog">results changelog</a>); picks.json {picks_hash}. The code that ran the benchmark and rebuilds these files is in the <a href="{CODE_URL}">repository</a>; its runner README explains how someone who owns the book rebuilds the question bank.</p>
    </section>
    <section class="card" id="results-changelog">
      <h2>Results changelog</h2>
      {site.in_prose(markdown((ROOT / "results-changelog.md").read_text()))}
    </section>
    <section class="card" id="key-changelog">
      <h2>Answer key changelog</h2>
      <p>Every setup is scored on answer key version {key["version"]}. Question bank SHA-256 <code>{esc(results["dataset"]["graded_sha256"])}</code>; key fingerprint <code>{esc(key["fingerprint"])}</code>.</p>
      {site.in_prose(markdown((ROOT / "key-changelog.md").read_text()))}
      <p>To report a wrong key, use the <a href="https://github.com/zekiworks/analysis/issues/new?template=answer-key-correction.md">answer key correction</a> form.</p>
    </section>
    <section class="card" id="citation">
      <h2>How to cite</h2>
      <p>Cite the results version, the answer key version and the commit of the repository you used.</p>
      <pre class="citation"><code>{esc(citation)}</code></pre>
    </section>
    <section class="card" id="licences">
      <h2>Licences</h2>
      <ul>
        <li>Code, results and answers: <a href="https://github.com/zekiworks/analysis/blob/main/LICENSE">MIT licence</a>.</li>
        <li>The questions: owned by the book's publisher and not published. Question IDs, pages and printed numbers locate each one in the book.</li>
      </ul>
    </section>"""
    return {PATH: site.page(PATH, "Data", "Downloads, the results and answer key changelogs, how to cite and the licences.",
                            body)}
