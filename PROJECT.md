# Project

## Purpose and structure

This repository contains a static HTML report titled **Jev → GPT: packet-level reanalysis and held-out cascade**. The current report distributes the article and figure only, without an embedded reproduction archive or download controls.

- `jev-swe-bench.html`: report entrypoint, with inline CSS and report content.
- `images/image-01.png`: image asset.
- `LICENSE`: repository license.

## Operation and constraints

Open `jev-swe-bench.html` directly in a browser. Its CSS is inline, and the figure loads from the relative path `images/image-01.png`. No build step or application server is needed for this viewing flow. No package manifest, build configuration, or test runner is present in the repository.

Names of data files, request templates, source files and analysis code in the article describe the original experiment's artifacts, not files supplied by this report-only repository. The artifact-availability section states this limitation; instructions requiring the removed archive are not included.

The report explicitly corrects the provenance of its labels: they were written by an AI assistant, not human annotators. Preserve that distinction when describing the results.

Do not commit private SSH keys, credentials, or other secrets when publishing the repository.

Removing an embedded archive from the current HTML does not remove copies from Git history or prior downloads.

## Verification

The local-file viewing flow has been exercised in Chromium. The report renders without download controls, embedded ZIP links, checksum metadata or archive-dependent reproduction commands. All five numerical tables retain their original contents, the 2080 × 1440 figure loads, and the label-provenance correction and dataset attribution link remain visible.
