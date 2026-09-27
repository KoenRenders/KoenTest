#!/usr/bin/env bash
# Diagnostics after a deploy — bundles into ONE file what you would otherwise run
# separately, so you see at a glance whether something is wrong. Runs ON the server,
# in the repo checkout. Deliberately holds no secrets/IPs (this repo is public).
#
#   ./logging.sh hdev | uat | prod
#
# Output:  /tmp/<env>-diagnostics.log   (override with LOG_OUT=…, lines with LOG_TAIL=…)
# To fetch it to your laptop: `raak fetch <env>`.
#
# Replaces logging-hdev.sh / logging-uat.sh / logging-prod.sh, which were identical
# line for line except for three variables and where the caddy logs come from.
set -euo pipefail

cd "$(dirname "$0")"

ENV="${1:?Name the environment: hdev | uat | prod (e.g. ./logging.sh uat)}"

# CADDY  own    = the stack's own Caddy (HDEV)
#        shared = the shared proxy (separate compose project, name: caddy). It
#                 serves UAT and PROD, so its logs hold traffic of both.
case "$ENV" in
  hdev) COMPOSE="docker-compose.hdev.yml"; ENVFILE=".env.hdev"; CADDY="own" ;;
  uat)  COMPOSE="docker-compose.uat.yml";  ENVFILE=".env.uat";  CADDY="shared" ;;
  prod) COMPOSE="docker-compose.prod.yml"; ENVFILE=".env.prod"; CADDY="shared" ;;
  *)    echo "ERROR: unknown environment '$ENV' — choose hdev, uat or prod." >&2; exit 1 ;;
esac

OUT="${LOG_OUT:-/tmp/${ENV}-diagnostics.log}"
TAIL="${LOG_TAIL:-100}"

dc() { docker compose -f "$COMPOSE" --env-file "$ENVFILE" "$@"; }
caddy_logs() {
  if [ "$CADDY" = "own" ]; then
    dc logs caddy --tail="${TAIL}" 2>&1 || echo "(caddy logs failed)"
  else
    docker compose -f docker-compose.caddy.yml logs caddy --tail="${TAIL}" 2>&1 \
      || echo "(caddy logs failed — is the shared Caddy running?)"
  fi
}

# The six post-deploy measurements, one definition shared with deploy.sh (#1253).
# shellcheck source=scripts/deploy-summary.sh
. ./scripts/deploy-summary.sh

# Output shows on your screen AND goes to the file (tee). We APPEND (-a): the deploy
# (deploy.sh) resets the log file at its start; this adds the post-deploy
# diagnostics, so one file holds the whole deploy + diagnostics (#291).
{
  echo "=== Raak Millegem — ${ENV} diagnostics ==="
  echo "Date:    $(date -Is)"
  echo "Commit:  $(git rev-parse --short HEAD 2>/dev/null || echo unknown) ($(git describe --tags --always 2>/dev/null || echo unknown))"
  echo

  echo "--- container status (everything 'running'/'healthy'? no 'restarting'/'exited'?) ---"
  dc ps 2>&1 || echo "(docker compose ps failed)"
  echo

  summary_measure_chain
  echo "--- alembic heads (there must be EXACTLY ONE) ---"
  printf '%s\n' "$SUMMARY_RAW_HEADS"
  [ "$SUMMARY_ALEMBIC_HEADS" != "$NOT_MEASURED" ] || echo "(alembic heads failed)"
  echo

  echo "--- alembic current (must equal the head above) ---"
  printf '%s\n' "$SUMMARY_RAW_CURRENT"
  [ "$SUMMARY_ALEMBIC_CURRENT" != "$NOT_MEASURED" ] || echo "(alembic current failed)"
  echo

  echo "--- disk space (a full disk causes odd deploy failures) ---"
  df -h / 2>&1 || echo "(df failed)"
  echo

  echo "--- quick error filter: ERROR/Traceback/Exception in the last ${TAIL} backend lines ---"
  if dc logs backend --tail="${TAIL}" 2>&1 | grep -iE 'error|traceback|exception' ; then
    : # matches shown above
  else
    echo "(no ERROR/Traceback/Exception in the last ${TAIL} lines)"
  fi
  echo

  echo "--- application log on disk (#766: survives a deploy, last ${TAIL}) ---"
  dc exec -T backend sh -c \
    'f=/var/log/raak/app.log; [ -f "$f" ] || { echo "(no $f yet)"; exit 0; }; echo "($(wc -l < "$f") lines, oldest: $(head -1 "$f" | cut -c1-19))"; tail -n '"${TAIL}"' "$f"' \
    2>&1 || echo "(application log not readable)"
  echo

  echo "--- backend logs (last ${TAIL}) ---"
  dc logs backend --tail="${TAIL}" 2>&1 || echo "(backend logs failed)"
  echo

  if [ "$CADDY" = "shared" ]; then
    echo "--- caddy logs (SHARED Caddy — UAT and PROD, last ${TAIL}) ---"
  else
    echo "--- caddy logs (own Caddy, last ${TAIL}) ---"
  fi
  caddy_logs
  echo

  # The same block deploy.sh prints, from the same definition. The whole container
  # log is read for the startup window: days after a deploy it is no longer in the
  # last ${TAIL} lines. No smoke test runs here, so smoke is NOT_MEASURED.
  summary_measure_commit
  summary_measure_startup all
  summary_print
} 2>&1 | tee -a "$OUT"

echo
echo "Diagnostics appended to: $OUT"
