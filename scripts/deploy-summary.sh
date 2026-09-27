#!/usr/bin/env bash
# The six post-deploy measurements, defined once (#1253). Sourced by deploy.sh
# and logging.sh — never run on its own.
#
# Why this file exists: after every deploy six things are reported (CLAUDE.md,
# "Verifying a deploy via the backend logs"). They used to be fished out of the
# prose of deploy.sh with search terms on its messages. That is a second copy of
# what the script says, and a single reworded sentence would have turned "no
# migrations ran" into "I did not look" without anyone noticing. So the scripts
# print a block with fixed keys, and whoever passes the numbers on reads the block.
#
#   === DEPLOY SUMMARY v1 ===
#   environment=uat
#   commit=v2.7.0
#   alembic_heads=2026_09_27_101500
#   alembic_current=2026_09_27_101500
#   migrations_applied=2026_09_26_091200,2026_09_27_101500
#   clean_start=ok
#   smoke=12 passed, 0 failed, 0 skipped
#   === END DEPLOY SUMMARY ===
#
# The key names are the contract (backend/tests/test_deploy_summary.py). A value
# is NOT_MEASURED when the measurement could not be taken; an empty value is a
# measurement. That difference matters most for migrations_applied: empty means
# "the startup ran no migration", NOT_MEASURED means "no startup was found to
# look at". Change the shape → bump v1 to v2, so readers know.
#
# The caller defines `dc` (docker compose with the environment's compose and
# env file) and `ENV` before calling these functions.

SUMMARY_KEYS=(environment commit alembic_heads alembic_current migrations_applied clean_start smoke)
NOT_MEASURED="NOT_MEASURED"

SUMMARY_COMMIT="$NOT_MEASURED"
SUMMARY_ALEMBIC_HEADS="$NOT_MEASURED"
SUMMARY_ALEMBIC_CURRENT="$NOT_MEASURED"
SUMMARY_MIGRATIONS_APPLIED="$NOT_MEASURED"
SUMMARY_CLEAN_START="$NOT_MEASURED"
SUMMARY_SMOKE="$NOT_MEASURED"
# Raw material for the callers' own reports; not part of the block.
SUMMARY_RAW_HEADS=""
SUMMARY_RAW_CURRENT=""
SUMMARY_STARTUP_ERRORS=""

# Revision ids from `alembic heads` / `alembic current` output, one per line.
summary_revisions() { sed -nE 's/^([0-9a-z_]+)([[:space:]].*)?$/\1/p'; }

summary_join() { paste -sd, -; }

summary_measure_commit() {
  SUMMARY_COMMIT="$(git describe --tags --always 2>/dev/null || echo "$NOT_MEASURED")"
}

# alembic heads and current, from the running backend. A command that fails is
# NOT_MEASURED; a command that answers nothing is an empty measurement.
summary_measure_chain() {
  if SUMMARY_RAW_HEADS="$(dc exec -T backend alembic heads 2>&1)"; then
    SUMMARY_ALEMBIC_HEADS="$(printf '%s\n' "$SUMMARY_RAW_HEADS" | summary_revisions | summary_join)"
  else
    SUMMARY_ALEMBIC_HEADS="$NOT_MEASURED"
  fi
  if SUMMARY_RAW_CURRENT="$(dc exec -T backend alembic current 2>&1)"; then
    SUMMARY_ALEMBIC_CURRENT="$(printf '%s\n' "$SUMMARY_RAW_CURRENT" | summary_revisions | summary_join)"
  else
    SUMMARY_ALEMBIC_CURRENT="$NOT_MEASURED"
  fi
}

# The last startup window of the backend: from "==> Running database migrations..."
# (the first line startup.sh prints) up to "Uvicorn running". Traffic after the
# start deliberately does not count — a Mollie webhook that 404s or a visitor's bad
# request in the seconds after a deploy must not become a rollback. After a restart
# awk keeps the LAST window: every start marker begins again.
#   $1 = how many backend log lines to read (a number, or "all")
summary_startup_window() {
  dc logs backend --tail="$1" 2>&1 | awk '
      /==> Running database migrations/ { buf = ""; busy = 1 }
      busy { buf = buf $0 "\n" }
      busy && /Uvicorn running on/ { busy = 0 }
      END { printf "%s", buf }'
}

# migrations_applied and clean_start from the startup window.
#   clean_start: ok | errors | not_reached | NOT_MEASURED (no startup window found)
#   $1 = how many backend log lines to read
summary_measure_startup() {
  local window
  window="$(summary_startup_window "$1")"
  SUMMARY_STARTUP_ERRORS=""
  if [ -z "$window" ]; then
    SUMMARY_MIGRATIONS_APPLIED="$NOT_MEASURED"
    SUMMARY_CLEAN_START="$NOT_MEASURED"
    return 0
  fi
  SUMMARY_MIGRATIONS_APPLIED="$(printf '%s' "$window" \
    | sed -nE 's/.*Running upgrade .* -> ([0-9a-z_]+).*/\1/p' | summary_join)"
  if ! printf '%s' "$window" | grep -q 'Uvicorn running on'; then
    SUMMARY_CLEAN_START="not_reached"
    return 0
  fi
  SUMMARY_STARTUP_ERRORS="$(printf '%s' "$window" | grep -iE 'error|traceback|exception' || true)"
  if [ -n "$SUMMARY_STARTUP_ERRORS" ]; then
    SUMMARY_CLEAN_START="errors"
  else
    SUMMARY_CLEAN_START="ok"
  fi
}

# The smoke result, from the file tests/run-all.sh writes when SMOKE_RESULT_FILE is
# set ("passed=N failed=M skipped=K"). No file or no numbers: NOT_MEASURED.
#   $1 = that file
summary_measure_smoke() {
  local line passed failed skipped
  line="$(cat "$1" 2>/dev/null || true)"
  passed="$(printf '%s' "$line" | sed -nE 's/.*passed=([0-9]+).*/\1/p')"
  failed="$(printf '%s' "$line" | sed -nE 's/.*failed=([0-9]+).*/\1/p')"
  skipped="$(printf '%s' "$line" | sed -nE 's/.*skipped=([0-9]+).*/\1/p')"
  if [ -n "$passed" ] && [ -n "$failed" ] && [ -n "$skipped" ]; then
    SUMMARY_SMOKE="$passed passed, $failed failed, $skipped skipped"
  else
    SUMMARY_SMOKE="$NOT_MEASURED"
  fi
}

# The block, one line per key of SUMMARY_KEYS: the key list is the only place the
# keys are named, so a key added there is printed without a second edit.
#
# xtrace is switched off while printing: deploy.sh runs with `set -x`, and its trace
# lines would otherwise land between the keys — the block must read on its own.
summary_print() {
  local key var xtrace=""
  case "$-" in *x*) xtrace=1; set +x ;; esac
  SUMMARY_ENVIRONMENT="${ENV}"
  echo "=== DEPLOY SUMMARY v1 ==="
  for key in "${SUMMARY_KEYS[@]}"; do
    var="SUMMARY_${key^^}"
    echo "${key}=${!var-$NOT_MEASURED}"
  done
  echo "=== END DEPLOY SUMMARY ==="
  if [ -n "$xtrace" ]; then set -x; fi
}
