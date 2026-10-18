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
#   scripts/build-tiptap-bundle.sh --offline  # the containers get NO network:
#                                             # the build can only use what a
#                                             # build before it left in the
#                                             # build directory, or fail
#
# `--offline` is for a rebuild whose checksum changes ON PURPOSE (a changed
# export list), where the checksum cannot prove that the packages are the
# pinned ones. The two-step way (Koen, 13 October 2026, "a nu"): first a build
# without it and without any change — it must print OK, which proves that
# the registry still gives the packages of the pinned checksum — and then the
# changed build with `--offline` from that same build directory, which can
# fetch nothing. A normal rebuild does not use it.
#
# Measured on 7 October 2026: npm install 4 s, esbuild 451 ms; two builds
# from cold containers gave the same sha256.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/backend/app/static/vendor"
MANIFEST="$ROOT/scripts/vendor-manifest.txt"
BUILD="${TIPTAP_BUILD_DIR:-/tmp/tiptap-bundle-build}"
IMAGE="node@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402"

UPDATE=0
NET_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --update) UPDATE=1 ;;
    --offline) NET_ARGS=(--network none) ;;
    *) echo "unknown argument: $arg (known: --update, --offline)" >&2; exit 64 ;;
  esac
done

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
import { Editor, Extension, Mark, Node, mergeAttributes } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import { StarterKit } from '@tiptap/starter-kit'
import { TableKit } from '@tiptap/extension-table'
import { Image } from '@tiptap/extension-image'
import { Link } from '@tiptap/extension-link'
import { Placeholder } from '@tiptap/extension-placeholder'
export {
  Editor, Extension, Mark, Node, mergeAttributes, StarterKit, TableKit, Image, Link, Placeholder,
  Plugin, PluginKey, Decoration, DecorationSet,
}
JS
# The five names added on 13 October 2026 — Extension, Plugin, PluginKey,
# Decoration, DecorationSet — are classes of packages the bundle already
# held and used (the StarterKit is built from them): no package was added
# and no version changed. The document editor's own script needs them for
# one rule of its own (a whole block that is selected keeps its selection).

# The `overrides` above are the 17 packages that install by range — the
# second look (#1699): a checksum that only DETECTS a drift is a race, a
# pin makes the drift impossible. The containers run as the calling user
# (with a writable HOME), so the build directory stays hers.
USER_ARGS=(-u "$(id -u):$(id -g)" -e HOME=/tmp)
docker run --rm -v "$PWD:/build" -w /build "${NET_ARGS[@]}" "${USER_ARGS[@]}" "$IMAGE" \
  npm install --no-audit --no-fund --loglevel=error
docker run --rm -v "$PWD:/build" -w /build "${NET_ARGS[@]}" "${USER_ARGS[@]}" "$IMAGE" \
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

if [ "$UPDATE" = 1 ]; then
  cp dist/tiptap-3.31.4.min.js "$VENDOR/tiptap-3.31.4.min.js"
  # The file's own head is written here too: until 13 October 2026 it was
  # typed into the file by hand, and the first `--update` after that dropped it.
  cat > "$VENDOR/tiptap-3.31.4.LICENSES" <<'HEAD'
# The licences of everything in tiptap-3.31.4.min.js (CR-17, #1671).
#
# MIT asks that the copyright and permission notice travel with the
# copies; the bundle is built with --legal-comments=none, so they travel
# HERE — every package the bundle was built from, with its licence
# text (review B2, #1699). Regenerated by scripts/build-tiptap-bundle.sh.

HEAD
  docker run --rm -v "$PWD:/build" -w /build "${NET_ARGS[@]}" "${USER_ARGS[@]}" "$IMAGE" sh -c '
    npm ls --all --parseable 2>/dev/null | tail -n +2 | while read p; do
      pkg=$(node -p "require(\"$p/package.json\").name")
      ver=$(node -p "require(\"$p/package.json\").version")
      lic=$(ls "$p" | grep -iE "^licen[cs]e" | head -1)
      echo "===== $pkg@$ver ====="
      if [ -n "$lic" ]; then cat "$p/$lic"; else
        echo "(no licence file in the package; the package.json says: $(node -p "require(\"$p/package.json\").license||\"?\""))"
      fi
      echo
    done' >> "$VENDOR/tiptap-3.31.4.LICENSES"
  echo "Wrote the bundle and tiptap-3.31.4.LICENSES into $VENDOR."
fi
