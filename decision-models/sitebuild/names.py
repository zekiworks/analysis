"""Model names as every page shows them (the project lead's naming rule, Ümit #4445; the three sites' scheme, #4449):
a setup shows its model's official name, the maker's name for the model and nothing else (official), and beside it a
small tag for how we ran it (tags), in the order setting · route · snapshot:

- setting: a chat model's confidence method where it has one ("vote share") and its reasoning setting ("high",
  "reasoning off", REASONING_WORDS);
- route: "chat" for a chat model's call (a setup with a reasoning setting); for a decision model, only where two of its
  setups differ by it, the route page_config.json display_names.routes names for the run ("API", "DGX Spark",
  "Decisions API": named, never inferred), then "with web" for a setup with web search;
- snapshot: the release or version of a checkpoint that sets a setup apart (the shared table's snapshot, else
  page_config.json display_names.snapshots by model ID:
  "1017", "first release", "v1.2");

then "1 per request" where a model has setups that differ only in their request size. A decision model with a single
setup has no tag. results.json keeps every run's setup name, run id and model id unchanged (they are identities); the
official name and the tag are derived here for display only. The official name comes from the three sites' shared table,
model_names.json at the site's root (logic #4487, copied byte for byte; MODEL_NAMES), by the setup's model_key, the
join key; each entry carries its source status ("maker", "inferred", "openrouter-only", "unverified": not every name
is maker-proven), its snapshot and its base model. Where the table lacks a model, page_config.json
display_names.pending gives the name the site shows until the table carries it, else the setup name stands. The build
stops where a shown name carries a bracket or a comma (a route or openness note), or where two setups would show the
same name and the same tag."""

from __future__ import annotations

import functools
import html
import json
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

# The three sites' shared names table, by model identity (logic #4487): name, source_status, snapshot, base_model.
MODEL_NAMES = Path(__file__).resolve().parent.parent / "model_names.json"
# A reasoning setting in a tag: a level as the provider names it ("high"), the other settings in words.
REASONING_WORDS = {"on": "reasoning on", "off": "reasoning off", "none": "no reasoning", "default": "default reasoning"}
# The tag's separator, and the one between a name and its tag in plain text (a tooltip, a chart label, a list).
SEPARATOR = " · "
# What a setup name may say about how it ran rather than which model it is: openness and route in parentheses. A release
# after a comma stays: "DeepSeek-V4.1-Flash, first release" is not the 1017 update nor a hosted "DeepSeek V4.1 Flash".
SETTING = re.compile(r"\s*\((?:open(?: weights)?|api[^)]*|local gpu)\)", re.I)


def model_key(name: str) -> str:
    """The three sites' join key (#4243): a setup name without its setting or route (SETTING dropped), lower case,
    spaces as hyphens, dots kept: "GLiDE 27B (open)" reads glide-27b, "Perplexity Decider 27B v1.2 (API, with web)"
    perplexity-decider-27b-v1.2, "GLiNER2.5 Multi (base)" gliner2.5-multi-base."""
    return "-".join(re.sub(r"[(),]", " ", SETTING.sub("", name)).lower().split())


@functools.cache
def shared() -> dict[str, dict[str, Any]]:
    """The shared table's entries by model_key, and by source_model_key where a row gives one (a Reading model_key that
    the table and the other sites write differently, logic #4514)."""
    entries = json.loads(MODEL_NAMES.read_text(encoding="utf-8"))["models"].values()
    return {**{entry["model_key"]: entry for entry in entries},
            **{entry["source_model_key"]: entry for entry in entries if entry.get("source_model_key")}}


@functools.cache
def key_aliases() -> dict[str, str]:
    """Reading's model_key to the shared one where the table's row gives a source_model_key (Zeki #4507, logic #4514):
    used only to look a name up here and to join rows on All benches. Reading writes its own model_key unchanged
    everywhere else."""
    entries = json.loads(MODEL_NAMES.read_text(encoding="utf-8"))["models"].values()
    return {entry["source_model_key"]: entry["model_key"] for entry in entries if entry.get("source_model_key")}


def entry(name: str) -> dict[str, Any] | None:
    """A setup name's entry in the shared table (by its model_key, or the row's source_model_key), or None where the
    table lacks the model."""
    return shared().get(model_key(name))


def official(name: str, config: dict[str, Any]) -> str:
    """A setup name's official model name: the shared table's name for its model_key, else page_config.json
    display_names.pending's, else the setup name. The build stops where the result carries a bracket or a comma."""
    found = (entry(name) or {}).get("name") or config["display_names"]["pending"].get(name) or name
    if re.search(r"[(),]", found):
        raise SystemExit(f"names: {name!r} reads {found!r}, still with a note; the shared model_names.json lacks it: "
                         "give its name in page_config.json display_names.pending")
    return found


def snapshot(run: dict[str, Any], config: dict[str, Any]) -> str | None:
    """The snapshot or version that sets a setup apart: the shared table's, else display_names.snapshots' by model ID."""
    return (entry(run["name"]) or {}).get("snapshot") or config["display_names"]["snapshots"].get(run["model"])


def base_model(run: dict[str, Any]) -> str | None:
    """The model a setup's model is built on (the shared table's base_model), for its details box only."""
    return (entry(run["name"]) or {}).get("base_model")


def reasoning_word(value: str) -> str:
    return REASONING_WORDS.get(value, value)


def machine(run: dict[str, Any]) -> str:
    """The machine of a setup on our hardware, from its hardware record: "1 × DGX Spark, GB10 (128 GB …)" reads
    "DGX Spark" (PWS-Decisions' setups, which display_names.routes does not cover)."""
    match = re.match(r"\s*\d+\s*×\s*([^,;(]+)", run.get("hardware") or "")
    if not match:
        raise SystemExit(f"names: run {run['run']} ({run['name']}) ran on our hardware but its hardware record "
                         f"{run.get('hardware')!r} names no machine")
    return match.group(1).strip()


def tags(setups: Iterable[dict[str, Any]], decision: Callable[[dict[str, Any]], bool],
         config: dict[str, Any]) -> dict[int, str]:
    """Each setup's tag, by run id (see the module's rule), over every setup the site shows (the Text tab's runs and
    the English-only setups): a decision model's route only where its official name has more than one setup; "N per
    request" for the setups whose request size alone tells them apart from another setup of the model (the smaller
    size). The build stops where two setups would show the same official name and the same tag, or where a route names
    a run the site does not show."""
    setups = list(setups)
    names = config["display_names"]
    routes = names["routes"]
    stale = set(routes) - {"about"} - {str(run["run"]) for run in setups}
    if stale:
        raise SystemExit(f"names: display_names.routes names runs the site does not show: {sorted(stale)}")
    by_name: dict[str, list[dict[str, Any]]] = {}
    for run in setups:
        by_name.setdefault(official(run["name"], config), []).append(run)
    found: dict[int, str] = {}
    for name, same in by_name.items():
        for run in same:
            parts: list[str] = []
            if decision(run):
                if len(same) > 1:
                    parts.append(routes.get(str(run["run"]), ""))
                    if run.get("perplexity_mode"):
                        parts.append("with web")
            else:
                if run.get("variant"):
                    parts.append(run["variant"])
                if run.get("reasoning"):
                    parts += [reasoning_word(run["reasoning"]), "chat"]
                if run.get("perplexity_mode"):
                    parts.append("with web")
            if snapshot(run, config):
                parts.append(snapshot(run, config))
            found[run["run"]] = SEPARATOR.join(filter(None, parts))
        groups: dict[str, list[dict[str, Any]]] = {}
        for run in same:
            groups.setdefault(found[run["run"]], []).append(run)
        for tag, group in groups.items():
            largest = max(run["questions_per_request"] for run in group)
            for run in group:
                if len(group) > 1 and run["questions_per_request"] != largest:
                    size = run["questions_per_request"]
                    found[run["run"]] = SEPARATOR.join(filter(None, (tag, f"{size} per request")))
        shown: dict[str, int] = {}
        for run in same:
            other = shown.setdefault(found[run["run"]], run["run"])
            if other != run["run"]:
                raise SystemExit(f"names: runs {other} and {run['run']} would both show as {name!r} with the tag "
                                 f"{found[run['run']]!r}; name their routes in page_config.json display_names.routes")
    return found


def plain(name: str, tag: str) -> str:
    """A name and its tag as plain text, for a tooltip, a chart label or a list: "GPT-6 Astra · low · chat"."""
    return f"{name}{SEPARATOR}{tag}" if tag else name


def tag_html(tag: str) -> str:
    """The small tag beside a name (v3.css .name-tag), a space before it so copied text never runs the two together;
    nothing without a tag."""
    return f' <span class="name-tag">{html.escape(tag)}</span>' if tag else ""


def name_html(name: str, tag: str) -> str:
    """A name and its tag as HTML: the name, then the small tag (tag_html)."""
    return html.escape(name) + tag_html(tag)
