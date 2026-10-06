#!/usr/bin/env bash
# The measurement run, locally (#1605, CR-11 B7 test 11): renders the pilot
# screens against a FROZEN clock and compares the positions, sizes and counts
# of their elements with the numbers in backend/tests_e2e/baselines/, or writes
# those numbers. The run itself is scripts/measure-run.sh, which CI calls too;
# this script only gives it what is local: an empty database of its own in the
# dev stack, and the helper container of the e2e's to run in.
#
# Why a run of its own, and not a few tests among the e2e's:
#
#   * the e2e seed counts from today (an activity in thirty days, this year's
#     membership, a booking made thirty days ago) and the screens show those
#     dates and counts — a baseline recorded today would be red tomorrow with no
#     line of code changed. So this run has its OWN database, seeded under a
#     fixed date, and its OWN server process under that same date (`faketime`);
#     the e2e's keep running in real time on theirs;
#   * the e2e's consume their seed (they confirm the open payment, cancel the
#     membership). A screen measured after them is another screen. This database
#     is seeded and then only read.
#
# Usage:
#   scripts/measure-local.sh                    # compare every screen with its baseline
#   scripts/measure-local.sh -k betalingen      # any pytest argument
#   scripts/measure-local.sh --write            # measure and WRITE the baselines
#   scripts/measure-local.sh --write public-home betalingen   # only these
#
# Environment:
#   MEASURE_DB_NAME   overrides the derived database name (must start with raakmeet)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/docker-compose.dev.yml")

slug="$(basename "$ROOT" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | sed 's/_\+/_/g; s/^_//; s/_$//')"
DB_NAAM="${MEASURE_DB_NAME:-raakmeet_${slug}}"

# This script DROPS its target database, like e2e-local.sh: a name that does not
# read as a measurement database is left alone.
case "$DB_NAAM" in
  raakmeet|raakmeet_*) ;;
  *)
    echo "measure-local.sh: REFUSED — '$DB_NAAM' does not read as a measurement database." >&2
    exit 2
    ;;
esac

# The helper container of the e2e's: the same image, the same pinned browser.
NAAM="raake2e-${slug}"
ENV_FILE="$ROOT/backend/tests_e2e/e2e.env"

if ! docker inspect -f '{{.State.Running}}' "$NAAM" 2>/dev/null | grep -q true; then
  echo "measure-local.sh: the helper container $NAAM is not running — run scripts/e2e-local.sh once first (it builds it)." >&2
  exit 2
fi
"${COMPOSE[@]}" up -d --no-recreate db >/dev/null
DB_USER="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_USER)"
DB_PASS="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_PASSWORD)"
URL="postgresql+psycopg2://${DB_USER}:${DB_PASS}@db:5432/${DB_NAAM}"

# `faketime` from Debian's own archive, once per helper container.
docker exec "$NAAM" sh -c 'command -v faketime >/dev/null || (apt-get update -q >/dev/null && apt-get install -y -q faketime >/dev/null)'

"${COMPOSE[@]}" exec -T db sh -c \
  "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c 'DROP DATABASE IF EXISTS ${DB_NAAM} WITH (FORCE)' \
   && psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c 'CREATE DATABASE ${DB_NAAM}'" >/dev/null 2>&1

status=0
docker exec --env-file "$ENV_FILE" -e DATABASE_URL="$URL" "$NAAM" /app/scripts/measure-run.sh "$@" || status=$?
if [ "${1:-}" = "--write" ]; then
  # The container writes as root; the baselines belong to whoever commits them.
  docker exec "$NAAM" chown -R "$(id -u):$(id -g)" /app/backend/tests_e2e/baselines
fi
exit "$status"
