"""Where models disagree with the answer key: the questions most setups get wrong, with the pick most of them chose
instead, and a link to the "Answer key correction" issue template."""

from __future__ import annotations

from collections import Counter

from v2build.questions import picks_data, question_link
from v2build.site import ISSUE_URL, Site, esc, rel

PATH = "disagreements/"


def build(site: Site) -> dict[str, str]:
    data = picks_data(site)
    runs = data["runs"]
    chat = [item for item in runs if not item["decision"]]
    rows = []
    for position, (question_id, unit, page, number, key) in enumerate(data["questions"]):
        picks = [item["picks"][position] for item in runs]
        wrong = sum(pick != key for pick in picks)
        if 2 * wrong <= len(runs):
            continue
        others = Counter(pick for pick in picks if pick not in (key, "-"))
        common, common_count = others.most_common(1)[0] if others else ("—", 0)
        chat_right = sum(item["picks"][position] == key for item in chat)
        rows.append((wrong, common_count, question_id, unit, key, common, chat_right))
    rows.sort(key=lambda row: (-row[0], -row[1], row[2]))
    body_rows = "".join(
        "<tr>"
        f'<td class="model">{question_link(PATH, question_id)}</td>'
        f'<td data-label="Part">{site.part(unit).capitalize()}</td>'
        f'<td data-label="Topic"><a href="{rel(PATH, f"topics/{unit}/")}">{esc(site.unit(unit)["english"])}</a></td>'
        f'<td class="num" data-label="Answer key">{esc(key)}</td>'
        f'<td class="num" data-label="Setups wrong">{wrong} of {len(runs)}</td>'
        f'<td class="num" data-label="Most common other pick">{esc(common)}{f" ({common_count})" if common_count else ""}</td>'
        f'<td class="num" data-label="Chat models right">{chat_right} of {len(chat)}</td>'
        "</tr>"
        for wrong, common_count, question_id, unit, key, common, chat_right in rows
    )
    body = f"""    <section class="card">
      <h1>Where models disagree with the answer key</h1>
      <p>These {len(rows):,} questions were answered wrongly by more than half of the {len(runs)} setups. Most are simply hard. Where many setups agree on another answer, the key may be wrong.</p>
      <p>Think a key is wrong? <a href="{ISSUE_URL}answer-key-correction.md">Report an answer key correction</a>. The <a href="{rel(PATH, "data/")}#key-changelog">key changelog</a> lists every change and how a fix works.</p>
      <div class="table-wrap"><table class="board list"><thead><tr><th scope="col">ID</th><th scope="col">Part</th><th scope="col">Topic</th><th scope="col" class="num">Answer key</th><th scope="col" class="num">Setups wrong</th><th scope="col" class="num">Most common other pick</th><th scope="col" class="num">Chat models right</th></tr></thead>
      <tbody>{body_rows}</tbody></table></div>
    </section>"""
    return {PATH: site.page(PATH, "Where models disagree with the answer key",
                            "The questions most setups get wrong, with the answer most of them chose instead.", body)}
