# Project

## Purpose and structure

This repository contains a static HTML report titled **Jev → GPT: packet-level reanalysis and held-out cascade**. The report links to a separate reproduction ZIP; it does not embed binary payloads in the HTML.

- `jev-swe-bench.html`: report entrypoint, with inline CSS and report content.
- `jev-q50-reanalysis.zip`: original reproduction archive, preserved byte for byte; 3,118,932 bytes and 482 files, including a SHA-256 inventory.
- `images/image-01.png`: image asset.
- `LICENSE`: repository license.

## Operation and constraints

Open `jev-swe-bench.html` directly in a browser, or run `python3 -u -m http.server 0 --bind 127.0.0.1` from the repository root and open the printed server address followed by `/jev-swe-bench.html`. Its CSS is inline, and the figure loads from the relative path `images/image-01.png`. No build step or application server is required; Python is only needed for the optional HTTP preview.

The download button and reproduction-section link both request the sibling `jev-q50-reanalysis.zip` as a separate file. Publish the HTML, ZIP and `images/` directory together, preserving their relative paths. The displayed archive size, file count and SHA-256 must remain synchronized with the ZIP.

The archive contains the original packets, backend prompt mappings, referenced sources, frozen controls and labels, paired trial data, analysis/construction code, tests, pinned dependencies and upstream license notices. Unpack it before following the report's reproduction commands, which use `reanalysis/paired-trials.csv` rather than replaying provider calls. Installing dependencies can require network access. There is no build configuration or test runner for the static report itself.

The report explicitly corrects the provenance of its labels: they were written by an AI assistant, not human annotators. Preserve that distinction when describing the results.

Do not commit private SSH keys, credentials, or other secrets when publishing the repository.

Removing an embedded archive from the current HTML does not remove copies from Git history or prior downloads.

## Verification

The report has been exercised in Chromium over local HTTP. Clicking its download button saves a ZIP that matches the verified archive byte for byte; all 481 entries in its checksum manifest have been verified. The HTML has no embedded data/blob links, all five numerical tables retain their original contents, the figure loads, and the label-provenance correction and dataset attribution remain intact. This publication verification does not rerun the bundled analysis or provider inference.
