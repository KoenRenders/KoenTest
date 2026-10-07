#!/usr/bin/env bash
# The TipTap bundle of the document editor (CR-17, #1671) — built ENTIRELY
# outside the repository, from this script, so a rebuild is a decision.
#
# Why a script in the repo: the recipe first stood on the spike's throwaway
# branch only, and 17 of the packages install by range — the first patch
# release of any of them would change the checksum without anyone changing a
# version (review B3, #1699). So the recipe lives here, the Node image is
# pinned by digest, and the 17 install-by-range packages stand in an
# `overrides` block — a pin, not a detector. The script still verifies the
# checksum against scripts/vendor-manifest.txt and refuses a rebuild that
# differs: belt and braces, and a drifted dependency is a decision to make
# with the diff in front of you. Still no package.json, no node_modules, no
# Node in the repository, at run time or in CI (the spike's decision, C8).
#
# Usage:
#   scripts/build-tiptap-bundle.sh            # build into /tmp, verify the checksum
#   scripts/build-tiptap-bundle.sh --update   # also write the bundle, the
#                                             # licences file and the resolved
#                                             # versions into the repository
#
# Measured on 7 October 2026: npm install 4 s, esbuild 451 ms; two builds
# from cold containers gave the same sha256.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/backend/app/static/vendor"
MANIFEST="$ROOT/scripts/vendor-manifest.txt"
BUILD="${TIPTAP_BUILD_DIR:-/tmp/tiptap-bundle-build}"
IMAGE="node@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402"

mkdir -p "$BUILD"
cd "$BUILD"
cat > package.json <<'JSON'
{
  "name": "tiptap-bundle-build", "version": "0.0.0", "private": true,
  "type": "module",
  "dependencies": {
    "@tiptap/core": "3.31.4", "@tiptap/pm": "3.31.4",
    "@tiptap/starter-kit": "3.31.4",
    "@tiptap/extension-table": "3.31.4",
    "@tiptap/extension-image": "3.31.4",
    "@tiptap/extension-link": "3.31.4",
    "@tiptap/extension-placeholder": "3.31.4"
  },
  "devDependencies": { "esbuild": "0.25.0" },
  "overrides": {
    "linkifyjs": "4.3.3",
    "orderedmap": "2.1.1",
    "prosemirror-changeset": "2.4.4",
    "prosemirror-commands": "1.7.2",
    "prosemirror-dropcursor": "1.8.4",
    "prosemirror-gapcursor": "1.4.1",
    "prosemirror-history": "1.5.1",
    "prosemirror-inputrules": "1.5.1",
    "prosemirror-keymap": "1.2.3",
    "prosemirror-model": "1.25.12",
    "prosemirror-schema-list": "1.5.1",
    "prosemirror-state": "1.4.4",
    "prosemirror-tables": "1.8.5",
    "prosemirror-transform": "1.12.2",
    "prosemirror-view": "1.42.6",
    "rope-sequence": "1.3.4",
    "w3c-keyname": "2.2.8"
  }
}
JSON
cat > entry.js <<'JS'
import { Editor, Node, mergeAttributes } from '@tiptap/core'
import { StarterKit } from '@tiptap/starter-kit'
import { TableKit } from '@tiptap/extension-table'
import { Image } from '@tiptap/extension-image'
import { Link } from '@tiptap/extension-link'
import { Placeholder } from '@tiptap/extension-placeholder'
export { Editor, Node, mergeAttributes, StarterKit, TableKit, Image, Link, Placeholder }
JS

# The `overrides` above are the 17 packages that install by range — the
# second look (#1699): a checksum that only DETECTS a drift is a race, a
# pin makes the drift impossible. The containers run as the calling user
# (with a writable HOME), so the build directory stays hers.
USER_ARGS=(-u "$(id -u):$(id -g)" -e HOME=/tmp)
docker run --rm -v "$PWD:/build" -w /build "${USER_ARGS[@]}" "$IMAGE" \
  npm install --no-audit --no-fund --loglevel=error
docker run --rm -v "$PWD:/build" -w /build "${USER_ARGS[@]}" "$IMAGE" \
  ./node_modules/.bin/esbuild entry.js --bundle --minify --format=iife \
  --global-name=RaakTiptap --outfile=dist/tiptap-3.31.4.min.js \
  --legal-comments=none --log-level=error

NEW="$(sha256sum dist/tiptap-3.31.4.min.js | cut -d' ' -f1)"
OLD="$(grep -E '^[0-9a-f]{64}' "$MANIFEST" | head -1 | cut -d' ' -f1)"
if [ "$NEW" != "$OLD" ]; then
  echo "REFUSED: the rebuild gives $NEW, the manifest pins $OLD." >&2
  echo "A dependency drifted. Update scripts/vendor-manifest.txt (and the" >&2
  echo "bundle, with --update) as a decision — this script does not do it silently." >&2
  exit 2
fi
echo "OK: the rebuild matches the pinned checksum ($NEW)."

if [ "${1:-}" = "--update" ]; then
  cp dist/tiptap-3.31.4.min.js "$VENDOR/tiptap-3.31.4.min.js"
  docker run --rm -v "$PWD:/build" -w /build "${USER_ARGS[@]}" "$IMAGE" sh -c '
    npm ls --all --parseable 2>/dev/null | tail -n +2 | while read p; do
      pkg=$(node -p "require(\"$p/package.json\").name")
      ver=$(node -p "require(\"$p/package.json\").version")
      lic=$(ls "$p" | grep -iE "^licen[cs]e" | head -1)
      echo "===== $pkg@$ver ====="
      if [ -n "$lic" ]; then cat "$p/$lic"; else
        echo "(no licence file in the package; the package.json says: $(node -p "require(\"$p/package.json\").license||\"?\""))"
      fi
      echo
    done' > "$VENDOR/tiptap-3.31.4.LICENSES"
  echo "Wrote the bundle and tiptap-3.31.4.LICENSES into $VENDOR."
fi
