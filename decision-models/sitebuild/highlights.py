"""The Highlights tab (highlights/): a page shell only, a heading and one sentence on what will go there. Single
questions with two or three models' answers come later, their text from the project lead; no question text here."""

from __future__ import annotations

from sitebuild.site import Site

PATH = "highlights/"
TITLE = "Highlights"


def build(site: Site) -> dict[str, str]:
    body = """    <section class="card">
      <h1>Highlights</h1>
      <p>Six to eight single questions will go here, each with two or three models' answers side by side; their text is still to come.</p>
    </section>"""
    return {PATH: site.page(PATH, TITLE, "Single questions with two or three models' answers side by side: still to come.", body)}
