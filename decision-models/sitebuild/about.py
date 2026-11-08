"""The About tab (about/): what the test is and how it was built (short, with the Method page for the full study), how
the scores work in detail, the leaderboard rules (sitebuild/leaderboard.py), the three result cards and the summary that
stood on the home page before (build_site.py checks both on this page: card_checks, summary_checks), and the links to
Method and Data. build_site.py builds it, after the home page, from the parts it computes (page)."""

from __future__ import annotations

from sitebuild import leaderboard
from sitebuild.site import Site, esc, rel

PATH = "about/"
TITLE = "About"
# The summary of the decision models' results, as it stood under Info on the home page: fixed copy, each line checked
# against results.json by build_site.py (copy_checks, summary_checks). Its links open a tab of the full ranking (All
# setups) on the Leaderboard.
SUMMARY = """<div class="summary">
        <p class="summary-lead">Among decision models, none led on every measure:</p>
        <ul class="summary-list">
          <li><a href="../?tab=accuracy#board">Accuracy</a>: REAX 1.3 and Liquid d1-ultra, tied and clearly ahead at 77.9% and 77.1%; then Decider v1.2 (API, with web), GLiDE v1.2, GLiDE, vLLM-SR d3 and d3-ultra (tied), Drex Max v1 and 1.1, Mammoth-1, and Deciders v1.1 and v1.2 (local GPU), at 66.9% to 68.7%.</li>
          <li><a href="../?tab=confidence#board">Calibration gap, as shipped</a>: Liquid d1.1 had the smallest gap among decision models.</li>
          <li><a href="../?tab=confidence#board">Better than a flat guess, after refit</a>: Perplexity Decider 27B v1.2 (API) at 32.1%, then Open-Jev 27B v1.1 (31.9%), then SubQ Snap 1.1 and Perplexity Decider 27B v1.1 (31.5% each). We did not test whether the gaps between them are real.</li>
          <li><a href="../?tab=routing#board">Estimated saving</a>: d1-ultra, the biggest in 10 of the 16 LLM setups; REAX 1.3 in the other 6.</li>
          <li><a href="../#reading-grammar">Reading vs grammar</a>: decision models got up to 92.4% of the reading questions right, but at most 71.8% of the grammar questions.</li>
        </ul>
      </div>"""


def page(site: Site, intro: str, how_scores: str, notes: str, cards: str, stats: str) -> str:
    """The About page from the home page's parts: the intro (plain text), the How the scores work bullets, the notes
    behind the full ranking, the result cards and the counters (HTML, links relative to the home page, moved here)."""
    up = rel(PATH, "")
    moved = lambda text: text.replace('href="models/', f'href="{up}models/').replace('href="method/', f'href="{up}method/')  # noqa: E731
    body = f"""    <section class="card prose" id="test">
      <h1>About the Reading bench</h1>
      <p>{esc(intro)}</p>
      <p>The questions come from a published book; their text stays unpublished, as the publisher owns it. Every setup's answer to every question is in <a href="{up}answers.json" download>answers.json</a>. The <a href="{rel(PATH, "method/")}">Method</a> page has the full study: the questions, the answer key, the runs and the tests.</p>
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
    <section class="card results-lead" id="results" aria-label="Main results">
      {moved(cards)}
    </section>
    <section class="card prose" id="summary">
      <h2>Summary</h2>
      {SUMMARY}
    </section>
    <section class="card prose" id="more">
      <h2>More</h2>
      <p><a href="{rel(PATH, "method/")}">Method</a>: how the questions, the answer key, the runs and the tests were made. <a href="{rel(PATH, "data/")}">Data</a>: every file behind the site.</p>
    </section>"""
    return site.page(PATH, TITLE, "What the Reading bench is, how its scores and its leaderboard work, and its main results.",
                     body)
