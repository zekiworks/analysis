"""The About tab (about/): what the test is and how it was built (short, with the Method page for the full study), how
the scores work in detail (moved from the home page), the leaderboard rules (sitebuild/leaderboard.py), the notes on each
page (the longer explanations moved from the top of the pages and from above their charts, Site.note), the summary that
stood on the home page before (build_site.py checks it on this page: summary_checks), and the links to Method and Data.
The three result cards (highest accuracy, most answers kept, lowest cost) are gone: the project lead wants no leader
summaries ahead of the results (via Zeki #4663). build_site.py builds the page, after the home page and the other pages,
from the parts it computes (page)."""

from __future__ import annotations

from sitebuild import all_benches, leaderboard
from sitebuild.site import NOTES_ANCHOR, Site, esc, note_anchor, rel

PATH = "about/"
TITLE = "About"
# The order of the pages in Notes on each page; a page not named here follows them in the order it was built.
NOTES_ORDER = ("", "english/", "turkish-vs-english/", "dont-know/", "web-grounding/", "pws-decisions/", "vision/",
               "questions/", "experiments/", "data/")
# The summary of the decision models' results, as it stood under Info on the home page: fixed copy, each line checked
# against results.json by build_site.py (copy_checks, summary_checks). Its links open a tab of the full ranking (All
# setups) on the Leaderboard.
SUMMARY = """<div class="summary">
        <p class="summary-lead">No decision model led on every measure:</p>
        <ul class="summary-list">
          <li><a href="../?tab=accuracy#board">Accuracy</a>: KnowLine-31B-Gen1.5 clearly ahead at 81.8%; REAX 1.3, Gemini Decision 1 and Liquid's d1-ultra, tied at 77.9%, 77.5% and 77.1%; GLiDE 27B at 71.1%; then Decider v1.2 with web search, GLiDE v1.2, hosted GLiDE, d3 and d3-ultra, Drex Max and Drex Max v1.1, Mammoth-1, Decider v1.1 and Decider v1.2 on our DGX Spark, at 66.9% to 68.7%.</li>
          <li><a href="../?tab=confidence#board">Calibration gap, as shipped</a>: d1.1 had the smallest among decision models.</li>
          <li><a href="../?tab=confidence#board">Better than a flat guess, after refit</a>: hosted Perplexity Decider 27B v1.2 at 32.1%, then Open-Jev-27B-v1.1 (31.9%), then SubQ Snap 1.1 and Perplexity Decider 27B v1.1 (31.5% each); the gaps are untested.</li>
          <li><a href="../?tab=routing#board">Estimated saving</a>: d1-ultra, the biggest in 7 of 16 LLM setups; Gemini Decision 1 in 5; REAX 1.3 in 2; GLiDE 27B in 2.</li>
          <li><a href="../#reading-grammar">Reading vs grammar</a>: decision models got up to 92.8% of reading questions right, but at most 77.1% of grammar.</li>
        </ul>
      </div>"""


def page_notes(site: Site) -> str:
    """Notes on each page (#page-notes): for each page with moved text (Site.note), a sub-heading linking the page with
    its anchor (note_anchor), then its text, each part under its own sub-heading and anchor."""
    order = sorted(site.notes, key=lambda path: NOTES_ORDER.index(path) if path in NOTES_ORDER else len(NOTES_ORDER))
    blocks = []
    for path in order:
        title, parts = site.notes[path]
        text = "".join(f'<h4 id="{note_anchor(path, part)}">{heading}</h4>{body}' if part else body
                       for part, heading, body in parts)
        blocks.append(f'<h3 id="{note_anchor(path)}"><a href="{rel(PATH, path)}">{esc(title)}</a></h3>{text}')
    return (f'<section class="card prose page-notes" id="{NOTES_ANCHOR}">\n      <h2>Notes on each page</h2>\n      '
            + "\n      ".join(blocks) + "\n    </section>")


def page(site: Site, intro: str, how_scores: str, notes: str, stats: str) -> str:
    """The About page from the home page's parts: the intro (plain text), the How the scores work bullets, the notes
    behind the full ranking and the counters (HTML, links relative to the home page, moved here)."""
    up = rel(PATH, "")
    moved = lambda text: text.replace('href="models/', f'href="{up}models/').replace('href="method/', f'href="{up}method/')  # noqa: E731
    body = f"""    <section class="card prose" id="test">
      <h1>About the Reading bench</h1>
      <p>{esc(intro)}</p>
      <p>The questions come from a published book; their text stays unpublished, as the publisher owns it. Every setup's answer to every question is in <a href="{up}answers.json" download>answers.json</a> and the files it lists beside it (the <a href="{up}data/">Data</a> page names each). The <a href="{rel(PATH, "method/")}">Method</a> page has the full study: the questions, the answer key, the runs and the tests.</p>
      <ul class="readouts">{stats}</ul>
      <p class="version">{site.version()}</p>
    </section>
    {moved(how_scores)}
    <section class="card prose" id="notes">
      <h2>Notes behind the scores</h2>
      <div class="tab-notes">{notes}</div>
    </section>
    <section class="card prose" id="leaderboard">
      <h2>The leaderboard rules</h2>
      {leaderboard.about_text(site, PATH)}
    </section>
    {page_notes(site)}
    <section class="card prose" id="summary">
      <h2>Summary</h2>
      {SUMMARY}
    </section>
    <section class="card prose" id="more">
      <h2>More</h2>
      <p><a href="{rel(PATH, "method/")}">Method</a>: how the questions, the answer key, the runs and the tests were made. <a href="{rel(PATH, "data/")}">Data</a>: every file behind the site. <a href="{all_benches.suite_path(site)}">{all_benches.TITLE}</a> (draft): every Zeki Works bench for the decision models on one page.</p>
    </section>"""
    return site.page(PATH, TITLE, "What the Reading bench is, how its scores and its leaderboard work, and its main results.",
                     body)
