"""Compare: two setups side by side, with the exact McNemar test on the questions they answered differently. The page is
drawn by compare.js from the site's results.json and from data/picks.json (written by v3build.questions)."""

from __future__ import annotations

from v3build.site import Site, esc, rel

PATH = "compare/"


def build(site: Site) -> dict[str, str]:
    ranked = site.ranked()
    options = "".join(f'<option value="{run["run"]}">{esc(site.full_name(run))}</option>' for run in ranked)
    first = next(run for run in ranked if site.decision(run))
    second = ranked[0]
    body = f"""    <section class="card" id="compare" data-default-a="{first["run"]}" data-default-b="{second["run"]}">
      <h1>Compare two setups</h1>
      <div class="compare-pickers">
        <label class="control">First <select data-pick="a">{options}</select></label>
        <label class="control">Second <select data-pick="b">{options}</select></label>
      </div>
      <p class="note" data-compare-status>This page needs JavaScript. The <a href="{rel(PATH, "")}">leaderboard</a> lists every setup.</p>
      <div data-compare hidden></div>
    </section>"""
    return {PATH: site.page(PATH, "Compare two setups", "Two setups side by side, with the exact McNemar test on the questions they answered differently.",
                            body, scripts=("compare.js",))}
