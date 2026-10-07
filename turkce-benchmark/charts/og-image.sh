#!/bin/sh
# Writes the page's sharing card: <docs-dir>/og-image.svg from <docs-dir>/results.json with the
# charts binary, then <docs-dir>/og-image.png (1200 × 630) rasterized with headless Chrome.
#
#   charts/og-image.sh docs
#
# Set CHROME to use another Chrome or Chromium binary.
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: charts/og-image.sh <docs-dir>" >&2
    exit 2
fi
umask 022
docs=$(cd "$1" && pwd)
charts=$(cd "$(dirname "$0")" && pwd)
chrome=${CHROME:-google-chrome}

cargo run --quiet --release --manifest-path "$charts/Cargo.toml" -- og-image "$docs/results.json" "$docs/og-image.svg"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp "$docs/og-image.svg" "$work/og-image.svg"
cat > "$work/card.html" <<'EOF'
<!doctype html>
<html><head><meta charset="utf-8">
<style>html, body { margin: 0; padding: 0; overflow: hidden; background: #fff; } img { display: block; width: 1200px; height: 630px; }</style>
</head><body><img src="og-image.svg" alt=""></body></html>
EOF
"$chrome" --headless=new --disable-gpu --no-first-run --no-default-browser-check --user-data-dir="$work/profile" \
    --force-device-scale-factor=1 --hide-scrollbars --window-size=1200,630 \
    --screenshot="$work/og-image.png" "file://$work/card.html" 2>/dev/null
cp "$work/og-image.png" "$docs/og-image.png"

# A PNG stores its width and height as big-endian 32-bit numbers at bytes 16 to 23.
size=$(od -An -tu1 -j16 -N8 "$docs/og-image.png" | awk '{ print $1*16777216 + $2*65536 + $3*256 + $4 "x" $5*16777216 + $6*65536 + $7*256 + $8 }')
if [ "$size" != "1200x630" ]; then
    echo "error: $docs/og-image.png is $size, not 1200x630" >&2
    exit 1
fi
echo "Wrote $docs/og-image.png ($size)"
