#!/usr/bin/env bash
# Rebuild docs/architecture.pdf (and the SVG diagrams under docs/architecture/) from
# docs/architecture.md. Tooling is installed once into .cache/ (git-ignored):
#   - mermaid-cli via npm (needs Node ≥ 18) — renders the Mermaid fences to SVG;
#   - weasyprint + markdown via pip — lays the document out on A4.
# Chromium: mermaid-cli uses puppeteer; set CHROME_PATH to an existing Chromium/Chrome
# binary to skip puppeteer's own download (e.g. a Playwright browser).
set -euo pipefail
cd "$(dirname "$0")/.."

CACHE=.cache/archdoc
mkdir -p "$CACHE"

if [ ! -x "$CACHE/node_modules/.bin/mmdc" ]; then
  echo "==> installing mermaid-cli into $CACHE"
  ( cd "$CACHE" && [ -f package.json ] || npm init -y >/dev/null
    cd "$CACHE" && PUPPETEER_SKIP_DOWNLOAD="${CHROME_PATH:+1}" npm install --no-audit --no-fund @mermaid-js/mermaid-cli@11 >/dev/null )
fi

if [ ! -d "$CACHE/venv" ]; then
  echo "==> creating venv with weasyprint + markdown"
  python3 -m venv "$CACHE/venv"
  "$CACHE/venv/bin/pip" install -q "weasyprint>=62" "markdown>=3.5"
fi

export MMDC="$PWD/$CACHE/node_modules/.bin/mmdc"
if [ -n "${CHROME_PATH:-}" ]; then
  printf '{"executablePath":"%s","args":["--no-sandbox","--disable-gpu"]}\n' "$CHROME_PATH" > "$CACHE/puppeteer.json"
  export PUPPETEER_CONFIG="$PWD/$CACHE/puppeteer.json"
fi

"$CACHE/venv/bin/python" docs/build/build_architecture_pdf.py
