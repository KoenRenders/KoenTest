#!/usr/bin/env bash
# Formats and lint-fixes the working copy with the ruff of the helper container (#1971).
#
# Why this script exists: the helper container of scripts/test-local.sh runs as `app`
# and cannot write into the bind-mounted working copy, so `ruff format` and
# `ruff check --fix` do not work in place there. This script lets ruff print its
# changes as a diff (`--diff`) and applies each diff on the HOST with `patch`, so the
# files stay owned by the calling user. Nothing is installed on the host, the image and
# its user are not touched, and nothing is written inside the container.
#
# Usage:
#   scripts/ruff-fix.sh                          # all of backend/
#   scripts/ruff-fix.sh app/domains/cms tests/test_x.py   # paths relative to backend/
#
# It uses the helper container of THIS working copy, `raaktest-<folder name>`, made by
# scripts/test-local.sh, and never makes one: it stops with one sentence when it is not
# running. Each diff is first tried with `patch --dry-run`, so a hunk that does not
# apply leaves nothing half done. At the end both checks run again, without `--diff`.
#
# Exit code: 0 when the tree is clean, 1 when ruff still finds something it cannot fix
# (it is printed), 2 when the script refuses.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
slug="$(basename "$ROOT" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | sed 's/_\+/_/g; s/^_//; s/_$//')"
NAAM="raaktest-${slug}"

if [ "$(docker inspect -f '{{.State.Running}}' "$NAAM" 2>/dev/null || true)" != "true" ]; then
  echo "ruff-fix.sh: REFUSED — the helper container $NAAM is not running; start it with scripts/test-local.sh first." >&2
  exit 2
fi

if ! command -v patch >/dev/null; then
  echo "ruff-fix.sh: REFUSED — `patch` is not installed on this machine (apt install patch)." >&2
  exit 2
fi

PATHS=("$@")
[ "${#PATHS[@]}" -gt 0 ] || PATHS=(.)

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

ruff() {
  docker exec -w /app/backend "$NAAM" python -m ruff "$@"
}

# apply_diff LABEL FILE — the diff on the host, from backend/, after a dry run.
apply_diff() {
  local label="$1" file="$2"
  [ -s "$file" ] || return 0
  if ! (cd "$ROOT/backend" && patch -p0 --dry-run -s <"$file" >/dev/null); then
    echo "ruff-fix.sh: REFUSED — a hunk of the $label diff does not apply; nothing of it was written." >&2
    exit 2
  fi
  (cd "$ROOT/backend" && patch -p0 -s <"$file")
  echo "→ $label: applied ($(grep -c '^+++ ' "$file") file(s))"
}

# `--diff` exits 1 when there is something to change; that is not a failure here.
# The fixes go first: removing an unused import leaves a blank line that the formatter
# then has to take away.
ruff check --no-cache --fix --diff "${PATHS[@]}" >"$WORK/check.diff" 2>/dev/null || true
apply_diff "ruff check --fix" "$WORK/check.diff"

ruff format --no-cache --diff "${PATHS[@]}" >"$WORK/format.diff" 2>/dev/null || true
apply_diff "ruff format" "$WORK/format.diff"

if ruff format --check --no-cache "${PATHS[@]}" >"$WORK/after.txt" 2>&1 \
  && ruff check --no-cache "${PATHS[@]}" >>"$WORK/after.txt" 2>&1; then
  echo "ruff-fix.sh: the tree is clean (ruff format --check and ruff check both pass)."
else
  cat "$WORK/after.txt" >&2
  echo "ruff-fix.sh: ruff still finds something it cannot fix itself (above)." >&2
  exit 1
fi
