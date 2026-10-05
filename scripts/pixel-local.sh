#!/usr/bin/env bash
# The pixel run, locally (#1605, CR-11 B7 test 11): renders the pilot screens
# against a FROZEN clock and compares them with the baselines in
# backend/tests_e2e/baselines/, or writes those baselines.
#
# Why a run of its own, and not a few tests among the e2e's:
#
#   * the e2e seed counts from today (an activity in thirty days, this year's
#     membership, a booking made thirty days ago) and the screens show those
#     dates — a baseline recorded today would be red tomorrow with no line of
#     code changed. So this run has its OWN database, seeded under a fixed date,
#     and its OWN server process under that same date (`faketime`); the e2e's
#     keep running in real time on theirs;
#   * the e2e's consume their seed (they confirm the open payment, cancel the
#     membership). A screen rendered after them is another screen. This database
#     is seeded and then only read.
#
# Usage:
#   scripts/pixel-local.sh                    # compare every screen with its baseline
#   scripts/pixel-local.sh -k betalingen      # any pytest argument
#   scripts/pixel-local.sh --write            # render and WRITE the baselines
#   scripts/pixel-local.sh --write public-home betalingen   # only these
#
# Environment:
#   PIXEL_DB_NAME   overrides the derived database name (must start with raakpixel)
#   PIXEL_OUT       where a red comparison leaves actual and diff (default /tmp/pixel-out
#                   in the helper container; this script copies it next to the repo's
#                   parent directory is NOT done — read it with `docker cp`)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/docker-compose.dev.yml")

slug="$(basename "$ROOT" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | sed 's/_\+/_/g; s/^_//; s/_$//')"
DB_NAAM="${PIXEL_DB_NAME:-raakpixel_${slug}}"

# This script DROPS its target database, like e2e-local.sh: a name that does not
# read as a pixel database is left alone.
case "$DB_NAAM" in
  raakpixel|raakpixel_*) ;;
  *)
    echo "pixel-local.sh: REFUSED — '$DB_NAAM' does not read as a pixel database." >&2
    exit 2
    ;;
esac

# The helper container of the e2e's: the same image, the same pinned browser.
NAAM="raake2e-${slug}"
POORT=8001
ENV_FILE="$ROOT/backend/tests_e2e/e2e.env"
# The frozen moment: ONE place, read by the seed, the server and the tests.
NU="$(sed -n 's/^PIXEL_NOW = "\(.*\)"$/\1/p' "$ROOT/backend/tests_e2e/pixels.py")"
[ -n "$NU" ] || { echo "pixel-local.sh: PIXEL_NOW not found in tests_e2e/pixels.py" >&2; exit 2; }

if ! docker inspect -f '{{.State.Running}}' "$NAAM" 2>/dev/null | grep -q true; then
  echo "pixel-local.sh: the helper container $NAAM is not running — run scripts/e2e-local.sh once first (it builds it)." >&2
  exit 2
fi
"${COMPOSE[@]}" up -d --no-recreate db >/dev/null
DB_USER="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_USER)"
DB_PASS="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_PASSWORD)"
URL="postgresql+psycopg2://${DB_USER}:${DB_PASS}@db:5432/${DB_NAAM}"

# `faketime` from Debian's own archive, once per helper container.
docker exec "$NAAM" sh -c 'command -v faketime >/dev/null || (apt-get update -q >/dev/null && apt-get install -y -q faketime >/dev/null)'

echo "→ rebuilding ${DB_NAAM} under ${NU}"
"${COMPOSE[@]}" exec -T db sh -c \
  "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c 'DROP DATABASE IF EXISTS ${DB_NAAM} WITH (FORCE)' \
   && psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c 'CREATE DATABASE ${DB_NAAM}'" >/dev/null
if ! MIGRATIE="$(docker exec --env-file "$ENV_FILE" -e DATABASE_URL="$URL" "$NAAM" alembic upgrade head 2>&1)"; then
  echo "pixel-local.sh: alembic upgrade head failed on ${DB_NAAM}:" >&2
  printf '%s\n' "$MIGRATIE" | tail -20 >&2
  exit 1
fi
docker exec --env-file "$ENV_FILE" -e DATABASE_URL="$URL" "$NAAM" python seed_postal_codes.py >/dev/null
docker exec --env-file "$ENV_FILE" -e DATABASE_URL="$URL" -e E2E_SEED=1 "$NAAM" \
  faketime "$NU" python seed_e2e.py | tail -1

# The pixel server: its own port, the frozen clock. A server of an earlier run is
# stopped through its pid file (the image has no pkill).
docker exec "$NAAM" sh -c 'if [ -f /tmp/pixel-uvicorn.pid ]; then kill "$(cat /tmp/pixel-uvicorn.pid)" 2>/dev/null || true; rm -f /tmp/pixel-uvicorn.pid; fi'
docker exec -d --env-file "$ENV_FILE" -e DATABASE_URL="$URL" "$NAAM" \
  sh -c "faketime '$NU' uvicorn app.main:app --host 0.0.0.0 --port ${POORT} > /tmp/pixel-uvicorn.log 2>&1 & echo \$! > /tmp/pixel-uvicorn.pid; wait"
for _ in $(seq 1 30); do
  if docker exec "$NAAM" python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:${POORT}/')" 2>/dev/null; then
    break
  fi
  sleep 1
done

RUN=(docker exec --env-file "$ENV_FILE" -e DATABASE_URL="$URL"
     -e PIXEL_BASE_URL="http://127.0.0.1:${POORT}" -e PIXEL_OUT="${PIXEL_OUT:-/tmp/pixel-out}" "$NAAM")
if [ "${1:-}" = "--write" ]; then
  shift
  exec "${RUN[@]}" python -m tests_e2e.pixels --write "$@"
fi
exec "${RUN[@]}" python -m pytest -o cache_dir=/tmp/pytest_cache tests_e2e/test_pixel_baselines.py "$@"
