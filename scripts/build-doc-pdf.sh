#!/usr/bin/env bash
# Build a printable PDF from a document under docs/.
#
#   scripts/build-doc-pdf.sh docs/intermediate-architecture-upgrade-v1.md
#
# Writes docs/<naam>.pdf next to the source, and the diagrams under
# docs/build/figuren/<naam>/.
#
# The tooling is installed once into .cache/ (git-ignored), never system-wide:
#   - weasyprint + markdown in a venv — lays the document out on A4;
#   - mermaid-cli via npm (Node >= 18) — renders ```mermaid fences to SVG.
#
# **Node is only needed when a diagram changed.** The SVGs are cached by content
# hash, so a rebuild of unchanged diagrams never starts mermaid-cli — and a
# document without diagrams never needs Node at all. That is why the npm install
# below is deferred until the document turns out to contain a mermaid fence.
#
# Chromium: mermaid-cli drives puppeteer. Set CHROME_PATH to an existing
# Chromium/Chrome binary to skip puppeteer's own download — a Playwright browser
# works, and this repo already installs one for the e2e tests.
set -euo pipefail
cd "$(dirname "$0")/.."

DOC="${1:-}"
if [ -z "$DOC" ] || [ ! -f "$DOC" ]; then
  echo "gebruik: scripts/build-doc-pdf.sh <docs/bestand.md>" >&2
  exit 2
fi

CACHE=.cache/docpdf
mkdir -p "$CACHE"

if [ ! -d "$CACHE/venv" ]; then
  echo "==> venv met weasyprint + markdown in $CACHE"
  python3 -m venv "$CACHE/venv"
  "$CACHE/venv/bin/pip" install -q "weasyprint>=62" "markdown>=3.5"
fi

# Only pay for Node when the document actually draws something.
if grep -q '^```mermaid' "$DOC"; then
  if [ ! -x "$CACHE/node_modules/.bin/mmdc" ]; then
    command -v npm >/dev/null || {
      echo "FOUT: $DOC bevat mermaid-diagrammen en npm ontbreekt." >&2
      echo "      Installeer Node >= 18, of haal de diagrammen uit het document." >&2
      exit 1
    }
    echo "==> mermaid-cli installeren in $CACHE"
    ( cd "$CACHE"
      [ -f package.json ] || npm init -y >/dev/null
      PUPPETEER_SKIP_DOWNLOAD="${CHROME_PATH:+1}" \
        npm install --no-audit --no-fund @mermaid-js/mermaid-cli@11 >/dev/null )
  fi
  export MMDC="$PWD/$CACHE/node_modules/.bin/mmdc"
  if [ -n "${CHROME_PATH:-}" ]; then
    printf '{"executablePath":"%s","args":["--no-sandbox","--disable-gpu"]}\n' "$CHROME_PATH" \
      > "$CACHE/puppeteer.json"
    export PUPPETEER_CONFIG="$PWD/$CACHE/puppeteer.json"
  fi
fi

exec "$CACHE/venv/bin/python" docs/build/build_doc_pdf.py "$DOC"
