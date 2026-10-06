#!/usr/bin/env bash
# The measurement run itself (#1605, CR-11 B7 test 11): ONE script for the two
# places it runs — inside the local helper container (scripts/measure-local.sh
# calls it) and in the CI job `e2e` (one step calls it). What differs by place —
# where the empty database comes from, how `faketime` got installed — stays with
# the caller; everything the run IS stands here, once.
#
# It expects:
#   DATABASE_URL   an EMPTY database of its own (never the e2e's: those tests
#                  consume their seed, and this run only reads)
#   faketime       on the PATH
#   the e2e environment (backend/tests_e2e/e2e.env) already in the environment
#
# It migrates and seeds that database under the frozen moment, serves it under
# the same moment on its own port, and then compares every pilot screen with its
# baseline — or, with --write, writes the baselines.
#
#   scripts/measure-run.sh                      # compare
#   scripts/measure-run.sh -k betalingen        # any pytest argument
#   scripts/measure-run.sh --write [screen …]   # measure and WRITE
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
PORT="${MEASURE_PORT:-8001}"

: "${DATABASE_URL:?measure-run.sh: DATABASE_URL must name the measurement database}"
case "$DATABASE_URL" in
  */raakmeet|*/raakmeet_*) ;;
  *)
    echo "measure-run.sh: REFUSED — the database in DATABASE_URL does not read as a measurement database (raakmeet…)." >&2
    exit 2
    ;;
esac
command -v faketime >/dev/null || { echo "measure-run.sh: faketime is not installed" >&2; exit 2; }

# The frozen moment: ONE place, read by the seed, the server and the tests.
NOW="$(sed -n 's/^MEASURE_NOW = "\(.*\)"$/\1/p' tests_e2e/measures.py)"
[ -n "$NOW" ] || { echo "measure-run.sh: MEASURE_NOW not found in tests_e2e/measures.py" >&2; exit 2; }

echo "→ measurement database under ${NOW}"
if ! MIGRATION="$(alembic upgrade head 2>&1)"; then
  echo "measure-run.sh: alembic upgrade head failed:" >&2
  printf '%s\n' "$MIGRATION" | tail -20 >&2
  exit 1
fi
python seed_postal_codes.py >/dev/null
E2E_SEED=1 faketime "$NOW" python seed_e2e.py | tail -1
# What the pilot screens need on top of the e2e seed (an album, a card with
# three dates and a poster): only in THIS database, the e2e's keep theirs.
E2E_SEED=1 faketime "$NOW" python -m tests_e2e.measure_seed | tail -1

# The measurement server: its own port, the frozen clock. A server of an earlier
# run is stopped through its pid file.
PIDFILE=/tmp/measure-uvicorn.pid
if [ -f "$PIDFILE" ]; then kill "$(cat "$PIDFILE")" 2>/dev/null || true; rm -f "$PIDFILE"; fi
JOBS_ENABLED=false nohup faketime "$NOW" uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
  >/tmp/measure-uvicorn.log 2>&1 &
echo $! >"$PIDFILE"
up=0
for _ in $(seq 1 60); do
  if python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:${PORT}/')" 2>/dev/null; then
    up=1
    break
  fi
  sleep 1
done
if [ "$up" != 1 ]; then
  echo "measure-run.sh: the measurement server did not come up:" >&2
  tail -30 /tmp/measure-uvicorn.log >&2
  exit 1
fi

export MEASURE_BASE_URL="http://127.0.0.1:${PORT}" MEASURE_REQUIRED=1
# The largest difference per screen and width with the baseline, printed after
# the comparison: in CI this is the local-against-runner difference.
export MEASURE_REPORT=/tmp/measure-report.txt
rm -f "$MEASURE_REPORT"
status=0
if [ "${1:-}" = "--write" ]; then
  shift
  python -m tests_e2e.measures --write "$@" || status=$?
else
  python -m pytest -o cache_dir=/tmp/pytest_cache tests_e2e/test_measure_baselines.py "$@" || status=$?
  if [ -f "$MEASURE_REPORT" ]; then
    echo "── largest difference with the baseline, per screen and width ──"
    cat "$MEASURE_REPORT"
  fi
fi
kill "$(cat "$PIDFILE")" 2>/dev/null || true
rm -f "$PIDFILE"
exit "$status"
