"""Compare: two setups side by side, with the exact McNemar test on the questions they answered differently. The page is
drawn by compare.js from the site's results.json and from data/picks.json (written by sitebuild.questions), at the
versioned addresses the page gives it (Site asset), and from compare-settings: each run's cost basis and price in the
model page's words (Site.cost_basis_text), and the upper-bound mark with its note."""

from __future__ import annotations

import json

import build_page as bp
from sitebuild.site import Site, asset, esc, rel

PATH = "compare/"


def settings(site: Site) -> str:
    """Each run's cost basis and list price, by run id, and the upper-bound mark, for compare.js; as v3-settings."""
    prices = {bp.price_key(item): item for item in site.results["prices"]}
    costs = {}
    for run in site.runs:
        price = prices.get(bp.price_key(run))
        costs[run["run"]] = {"basis": site.cost_basis_text(run),
                             "price": {key: price[key] for key in ("text", "source", "date")} if price else None}
    upper = site.config["first_cost_marks"]["upper"]
    data = {"costs": costs, "upper": {"mark": upper["mark"], "note": upper["note"]}}
    return f'<script type="application/json" id="compare-settings">{json.dumps(data, ensure_ascii=False, separators=(",", ":"))}</script>'


def build(site: Site) -> dict[str, str]:
    ranked = site.ranked()
    options = "".join(f'<option value="{run["run"]}">{esc(site.full_name(run))}</option>' for run in ranked)
    first = next(run for run in ranked if site.decision(run))
    second = ranked[0]
    body = f"""    {settings(site)}
    <section class="card" id="compare" data-default-a="{first["run"]}" data-default-b="{second["run"]}" data-results="{rel(PATH, asset("results.json"))}" data-picks="{rel(PATH, asset("data/picks.json"))}">
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
