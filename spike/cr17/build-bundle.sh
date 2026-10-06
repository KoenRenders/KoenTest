#!/bin/sh
# CR-17 spike (#1626) — the one-off TipTap bundle build.
#
# Runs entirely outside the repository: the build directory (with
# package.json and node_modules) is never committed, not even on this
# throwaway branch. Node exists only inside the container, once, for this
# step; the repository's own build stays Python + Tailwind-standalone.
#
# Measured on 6 October 2026, with a cold container each step:
#   npm install (7 pinned packages + esbuild):  4 s
#   esbuild --bundle --minify --format=iife:     451 ms (376 ms first run)
# Result: dist/tiptap-3.31.4.min.js, 441 283 bytes (139 010 gzip)
#         -> backend/app/static/vendor/tiptap-3.31.4.min.js
# TipTap v3 ships no CSS; tiptap-3.31.4.css is ours (the kit's chrome).
# Learned while building: StarterKit v3 already includes link, and `Table`
# alone is not usable — the schema needs TableKit (table + row + header + cell).
#
# Rebuild (phase 1 rebuilds it the same way; nothing is copied):
#   BUILD=/tmp/tiptap-build
#   mkdir -p $BUILD && cd $BUILD
#   cat > package.json <<'JSON'
#   {
#     "name": "tiptap-bundle-build", "version": "0.0.0", "private": true,
#     "type": "module",
#     "dependencies": {
#       "@tiptap/core": "3.31.4", "@tiptap/pm": "3.31.4",
#       "@tiptap/starter-kit": "3.31.4",
#       "@tiptap/extension-table": "3.31.4",
#       "@tiptap/extension-image": "3.31.4",
#       "@tiptap/extension-link": "3.31.4",
#       "@tiptap/extension-placeholder": "3.31.4"
#     },
#     "devDependencies": { "esbuild": "0.25.0" }
#   }
#   JSON
#   cat > entry.js <<'JS'
#   import { Editor, Node, mergeAttributes } from '@tiptap/core'
#   import { StarterKit } from '@tiptap/starter-kit'
#   import { TableKit } from '@tiptap/extension-table'
#   import { Image } from '@tiptap/extension-image'
#   import { Link } from '@tiptap/extension-link'
#   import { Placeholder } from '@tiptap/extension-placeholder'
#   export { Editor, Node, mergeAttributes, StarterKit, TableKit, Image, Link, Placeholder }
#   JS
#   docker run --rm -v $PWD:/build -w /build node:22-alpine \
#     npm install --no-audit --no-fund --loglevel=error
#   docker run --rm -v $PWD:/build -w /build node:22-alpine \
#     ./node_modules/.bin/esbuild entry.js --bundle --minify --format=iife \
#       --global-name=RaakTiptap --outfile=dist/tiptap-3.31.4.min.js \
#       --legal-comments=none --log-level=error
#   sha256sum dist/tiptap-3.31.4.min.js   # -> scripts/vendor-manifest.txt
