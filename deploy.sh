#!/usr/bin/env bash
# Deploys one environment. Replaces deploy-hdev.sh / deploy-uat.sh / deploy-prod.sh;
# after #576 those were thin wrappers, removed with #577 once v2.0.0 ran on UAT and
# PROD. They carried weight during the cutover: the deploy script of v1.14.0 does an
# `exec "$0"` after the checkout (#162), so the old file name had to exist in the
# NEW tag.
#
#   ./deploy.sh hdev                      # follows master (integration line, no tag)
#   ./deploy.sh uat  v2.0.0               # an exact release tag
#   ./deploy.sh prod v2.0.0 --remove-orphans
#
# Why one script: deploy-uat.sh and deploy-prod.sh were identical line for line
# except for the string uat/prod. Two copies of the deploy path to production is a
# drift risk — a fix that lands in one and not in the other goes unnoticed. The
# differences between the environments are now explicit flags in the config block
# below, instead of silent absences.
#
# UAT/PROD deliberately run a pinned tag: we do NOT assume master equals the latest
# release. HDEV is the integration line and follows master.
set -euxo pipefail

cd "$(dirname "$0")"

ENV="${1:?Name the environment: hdev | uat | prod (e.g. ./deploy.sh uat v2.0.0)}"
shift

# ── Config block per environment ─────────────────────────────────────────────
# SOURCE   master = follow the integration line; tag = exact release tag required
# BACKUP   pre-migration dump of the database before the rebuild (#395)
# ROLLBACK one automatic fallback when the smoke test fails (#395)
# CADDY    own = the stack's own Caddy (HDEV); shared = the shared proxy, deployed
#          separately through deploy-caddy.sh
# KETEN_GATE / LOG_GATE  post-check (#604): 1 = gate (a failure rolls back on the
#          environments that have ROLLBACK=1), 0 = reporting only. See "Post-check".
# SMOKE_TENANT   the association the smoke test checks, by its path prefix (#1530):
#          the bare host may be the platform, which has activities and payment off.
# SMOKE_PLATFORM 1 = also check that the bare host is the platform (health 200, a
#          module that is off 404); only where the bare host is known to be it.
case "$ENV" in
  hdev)
    COMPOSE="docker-compose.hdev.yml"; ENVFILE=".env.hdev"
    SOURCE="master"; BACKUP=0; ROLLBACK=0; CADDY="own"
    KETEN_GATE=0; LOG_GATE=0
    SMOKE_BASE_DEFAULT="http://localhost:8081"
    SMOKE_TENANT="raakmillegem"; SMOKE_PLATFORM=1
    ;;
  uat)
    COMPOSE="docker-compose.uat.yml"; ENVFILE=".env.uat"
    SOURCE="tag"; BACKUP=1; ROLLBACK=1; CADDY="shared"
    KETEN_GATE=1; LOG_GATE=0
    SMOKE_BASE_DEFAULT=""
    SMOKE_TENANT="raakmillegem"; SMOKE_PLATFORM=0
    ;;
  prod)
    COMPOSE="docker-compose.prod.yml"; ENVFILE=".env.prod"
    SOURCE="tag"; BACKUP=1; ROLLBACK=1; CADDY="shared"
    KETEN_GATE=1; LOG_GATE=0
    SMOKE_BASE_DEFAULT=""
    SMOKE_TENANT="raakmillegem"; SMOKE_PLATFORM=0
    ;;
  *)
    echo "ERROR: unknown environment '$ENV' — choose hdev, uat or prod." >&2
    exit 1
    ;;
esac

dc() { docker compose -f "$COMPOSE" --env-file "$ENVFILE" "$@"; }

# ── Determine the ref ────────────────────────────────────────────────────────
REF=""
if [ "$SOURCE" = "tag" ]; then
  REF="${1:?Name the release tag to deploy, e.g.: ./deploy.sh $ENV v2.0.0}"
  shift
fi
# Whatever is left goes on to `docker compose up` (e.g. --remove-orphans).
UP_EXTRA=("$@")

# Rollback target (#395): remember what runs NOW, before the checkout. Set once;
# survives the re-exec and a possible rollback exec through export.
if [ "$ROLLBACK" = 1 ]; then
  export DEPLOY_PREV_REF="${DEPLOY_PREV_REF:-$(git describe --tags --always 2>/dev/null || echo '')}"
fi

# ── Fetch the source ─────────────────────────────────────────────────────────
if [ "$SOURCE" = "master" ]; then
  # --tags so that `git describe` shows a meaningful release tag in the version log (#151).
  git fetch --tags --force origin master
  git reset --hard origin/master
else
  # A detached HEAD is intended here: you run an exact commit, not a moving branch.
  git fetch --tags --prune origin
  git checkout --detach "$REF"
fi

# Robustness (#162): after the checkout the previous script version may still be
# running. Re-exec the version now checked out once, so the rest (version export,
# build, smoke) comes from the right script content. The guard prevents an endless loop.
if [ -z "${DEPLOY_REEXEC:-}" ]; then
  export DEPLOY_REEXEC=1
  exec "$0" "$ENV" ${REF:+"$REF"} ${UP_EXTRA[@]+"${UP_EXTRA[@]}"}
fi

# From here on, capture all output (build + smoke) in the diagnostics file AND show
# it on screen (#291). This is also the RESET of the log file: every deploy starts
# with a clean file; logging.sh appends to it afterwards.
LOG_OUT="${LOG_OUT:-/tmp/${ENV}-diagnostics.log}"
exec > >(tee "$LOG_OUT") 2>&1

# The six post-deploy measurements, one definition shared with logging.sh (#1253).
# shellcheck source=scripts/deploy-summary.sh
. ./scripts/deploy-summary.sh

# Version + commit for the startup log (#151); passed as build args to the backend image.
export APP_VERSION="$(git describe --tags --always 2>/dev/null || echo unknown)"
export GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
SUMMARY_COMMIT="$APP_VERSION"

# ── Pre-migration backup ─────────────────────────────────────────────────────
# Alembic runs at container start, so the dump must happen before the rebuild.
# Credentials come from the db container itself.
#
# For a release that adds a migration, this dump is the ONLY way back (#1203).
# Additive migrations keep the schema compatible with the previous image, but
# not alembic's version check: the previous image runs `alembic upgrade head` at
# startup, does not know the revision the database now carries, and refuses to
# start. So the rollback below is skipped for such a release, and its stop
# message names this file.
BACKUP_FILE=""
if [ "$BACKUP" = 1 ]; then
  BACKUP_DIR="${BACKUP_DIR:-./backups}"; mkdir -p "$BACKUP_DIR"
  if [ -n "$(dc ps -q db 2>/dev/null)" ]; then
    TS=$(date +%Y%m%d-%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/pre-deploy-$ENV-$TS.sql.gz"
    dc exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
      | gzip > "$BACKUP_FILE"
    echo "Pre-migration backup: $BACKUP_FILE"
  else
    echo "db container not running — pre-migration backup skipped (first deploy?)"
  fi
fi

# ── Build and start ──────────────────────────────────────────────────────────
dc up --build -d ${UP_EXTRA[@]+"${UP_EXTRA[@]}"}

# HDEV has its own Caddy in the stack. Restart it so that changes to Caddyfile.hdev
# (bind mount) are reliably active: `caddy reload` (admin API) turned out not to
# always pick up the config — stale routing and lost compression were the result.
# Force-recreate loads the config fresh from disk (#169). UAT/PROD share one Caddy;
# that one goes separately through deploy-caddy.sh.
if [ "$CADDY" = "own" ]; then
  dc up -d --force-recreate caddy
fi

# ── Post-check: migration chain and clean start (#604) ───────────────────────
# After every deploy three things ought to hold: exactly one alembic head, a
# `current` equal to it, and a startup without errors. `raakctl diagnose` collects
# them neatly — but you run that separately, after the deploy, and that report has
# no exit code that stops anything. Forget it, and nobody notices.
#
# The smoke test does not see these two failures: it checks that public pages return
# 200 and that the admin is shielded. A split migration chain and a backend that
# only breaks after that first successful request pass it unnoticed.
#
#   | check           | hdev           | uat / prod     |
#   |-----------------|----------------|----------------|
#   | migration chain | reporting only | GATE           |
#   | clean start     | reporting only | reporting only |
#
# The chain check is deterministic — two heads are two heads — so it may be a gate
# right away. The log check not yet: a false rollback on PROD over one ERROR line
# costs more than missing the message, and we do not know yet how quiet those logs
# really are. So it runs loudly for a release first. Set LOG_GATE=1 in the config
# block once that is known.
#
# Both run through `dc exec -T backend`, so with this environment's env file — the
# same pattern as logging.sh — and both read the measurements of deploy-summary.sh,
# so the check and the summary block can never disagree. They run inside the same
# DEPLOY_ROLLBACK guard as the smoke test, so a deploy never rolls back twice.

# The measurements the checks and the summary block read. Taken once per run.
measure() {
  summary_measure_chain
  summary_measure_startup 500
}

migratieketen_ok() {
  local count
  if [ "$SUMMARY_ALEMBIC_HEADS" = "$NOT_MEASURED" ]; then
    echo "!! Migration chain: alembic heads could not be read from the backend."
    return 1
  fi
  count="$(printf '%s' "$SUMMARY_ALEMBIC_HEADS" | tr ',' '\n' | grep -c . || true)"
  if [ "$count" -ne 1 ]; then
    echo "!! Migration chain: $count heads instead of 1 — the chain is split: [$SUMMARY_ALEMBIC_HEADS]"
    return 1
  fi
  if [ "$SUMMARY_ALEMBIC_CURRENT" != "$SUMMARY_ALEMBIC_HEADS" ]; then
    echo "!! Migration chain: alembic current is [$SUMMARY_ALEMBIC_CURRENT], not [$SUMMARY_ALEMBIC_HEADS] — a migration was not applied."
    return 1
  fi
  echo "Migration chain OK: one head ($SUMMARY_ALEMBIC_HEADS), current equal."
}

schone_start_ok() {
  # TIGHTLY scoped to the startup window (see summary_startup_window).
  case "$SUMMARY_CLEAN_START" in
    ok)
      echo "Clean start OK: no ERROR/Traceback/Exception between container start and 'Uvicorn running'." ;;
    not_reached)
      echo "!! Clean start: the backend never reached 'Uvicorn running'; startup hung."
      return 1 ;;
    errors)
      echo "!! Clean start: errors during startup:"
      printf '%s\n' "$SUMMARY_STARTUP_ERRORS"
      return 1 ;;
    *)
      echo "!! Clean start: no startup window in the last 500 backend lines — did the backend start?"
      return 1 ;;
  esac
}

applicatielog_regel() {
  # INFORMATIONAL, never a gate (#766). The check this issue asks for: does the log
  # still hold something from before the deploy after it? You read it here — if the
  # oldest line is older than this deploy, the log survived the container. An empty
  # or missing folder is no reason to roll anything back; it is something you should
  # see here instead of having to go looking for it.
  local uit
  uit="$(dc exec -T backend sh -c \
    'f=/var/log/raak/app.log; [ -f "$f" ] || exit 3; echo "$(wc -l < "$f") lines, oldest: $(head -1 "$f" | cut -c1-19)"' \
    2>/dev/null || true)"
  if [ -z "$uit" ]; then
    echo "Application log: /var/log/raak/app.log not present yet — normal on the first deploy after #766."
  else
    echo "Application log (survives the deploy): $uit"
  fi
}

nacontrole() {
  local mislukt=0
  echo "== Post-check (#604): migration chain and clean start =="
  if ! migratieketen_ok; then
    if [ "$KETEN_GATE" = 1 ]; then mislukt=1; else echo "   (reporting only on $ENV — this rolls nothing back)"; fi
  fi
  if ! schone_start_ok; then
    if [ "$LOG_GATE" = 1 ]; then mislukt=1; else echo "   (reporting only on $ENV — this rolls nothing back)"; fi
  fi
  applicatielog_regel
  return $mislukt
}

# ── Post-deploy smoke test ───────────────────────────────────────────────────
# STRICTLY READ-ONLY, creates no data (safe on PROD). Target URL = the public origin
# from the env file (Caddy proxies /api/* to the backend); for HDEV that is the
# local port.
SMOKE_BASE="${SMOKE_BASE:-$SMOKE_BASE_DEFAULT}"
if [ -z "$SMOKE_BASE" ]; then
  SMOKE_BASE="$(sed -nE "s/^FRONTEND_URL=[\"']?([^\"']*)[\"']?.*/\1/p" "$ENVFILE" | head -1)"
fi

if [ -z "$SMOKE_BASE" ]; then
  echo "FRONTEND_URL unknown in $ENVFILE — smoke test skipped"
  measure
  summary_print
  exit 0
fi

# #1530: the smoke test names the tenant it checks. A path prefix wins over the host
# in the tenant resolution, on every path including /api, so `<site>/<code>` is that
# association whatever the bare host resolves to. Since #1523 the bare HDEV host is
# the platform, where /api/v1/activities is absent by design. The checks themselves
# are unchanged.
SMOKE_SITE="${SMOKE_BASE%/}"
SMOKE_BASE="${SMOKE_SITE}/${SMOKE_TENANT}"
PLATFORM_BASE=""
[ "$SMOKE_PLATFORM" = "1" ] && PLATFORM_BASE="$SMOKE_SITE"
echo "Smoke target: ${SMOKE_BASE}${PLATFORM_BASE:+ (platform: ${PLATFORM_BASE})}"

# Wait until the site answers before the smoke test starts (#800). This loop used to
# sit INSIDE the `own` branch and polled `$SMOKE_BASE_DEFAULT` — which is empty on UAT
# and PROD, so there it never ran. The protection sat on the environment that needs it
# least, and was missing on the two where a rollback has real consequences: the
# compression check got a 502 (Caddy does not compress an error page), the smoke test
# failed, and the script rolled back a healthy deploy.
#
# Measured on 9 September 2026 while bringing UAT level with v2.0.1: `1 OK ·
# 1 gefaald` on the compression, automatic rollback, the same failure on the
# rolled-back version, and a minute later three times a clean `content-encoding:
# zstd`. The stack was healthy; only the test was too early.
#
# `curl -fsS` already fails on a 502, so this waits for a real 200 and not for
# "something answers". Thirty attempts: if the backend still does not answer after
# that, it is a real failure and the smoke test ought to fail.
for _ in $(seq 1 30); do
  curl -fsS -o /dev/null "${SMOKE_BASE}/" && break
  sleep 1
done

SMOKE_RESULT_FILE="$(mktemp)"
FAAL=""
if ! SMOKE_RESULT_FILE="$SMOKE_RESULT_FILE" BASE="$SMOKE_BASE" PLATFORM_BASE="$PLATFORM_BASE" \
    ./tests/run-all.sh; then
  FAAL="SMOKE"
  # Not judged — the smoke test already failed — but measured, so the summary block
  # below is complete on the failure path too.
  measure
else
  measure
  if ! nacontrole; then
    FAAL="POST-CHECK"
  fi
fi
summary_measure_smoke "$SMOKE_RESULT_FILE"
rm -f "$SMOKE_RESULT_FILE"
summary_print

if [ -z "$FAAL" ]; then
  echo "Smoke + post-check OK on ${REF:-master}."
  exit 0
fi

echo "!! $FAAL FAILED on ${REF:-master}."
if [ "$ROLLBACK" != 1 ]; then
  exit 1
fi

# ── Can the previous release still start? (#1203) ────────────────────────────
# The alembic head of a ref, read from git: the revisions no other migration names
# as its `down_revision`. No database needed, so this also answers when the
# backend is down — which is exactly when the question comes up.
alembic_head_at() {
  local ref="$1" revisions downs
  revisions="$(git grep -h -E '^revision *=' "$ref" -- 'backend/alembic/versions/*.py' 2>/dev/null \
    | sed -nE "s/^revision *= *['\"]([^'\"]+)['\"].*/\1/p" | sort -u || true)"
  downs="$(git grep -h -E '^down_revision *=' "$ref" -- 'backend/alembic/versions/*.py' 2>/dev/null \
    | sed -nE "s/^down_revision *= *['\"]([^'\"]+)['\"].*/\1/p" | sort -u || true)"
  comm -23 <(printf '%s\n' "$revisions") <(printf '%s\n' "$downs") | grep . || true
}

# True when the previous ref carries the same alembic head as this one, i.e. this
# release adds no migration and the previous image can start on this database.
# Anything else — a new head, or a chain that cannot be read — means no automatic
# rollback: guessing wrong here takes the environment down instead of leaving the
# failed release running.
rollback_can_start() {
  local prev_head new_head db_revision
  prev_head="$(alembic_head_at "$DEPLOY_PREV_REF")"
  new_head="$(alembic_head_at HEAD)"
  if [ -n "$prev_head" ] && [ "$prev_head" = "$new_head" ]; then
    echo "No migration in this release (alembic head $new_head on both refs) — the rollback can start."
    return 0
  fi
  db_revision="$(dc exec -T db sh -c \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version"' \
    2>/dev/null | tr -d '[:space:]' || true)"
  echo "!! No automatic rollback (#1203)."
  if [ -z "$prev_head" ] || [ -z "$new_head" ]; then
    echo "   The alembic chain could not be read from git for $DEPLOY_PREV_REF or HEAD,"
    echo "   so it is unknown whether this release adds a migration."
  else
    echo "   This release adds a migration: $DEPLOY_PREV_REF ends at $(echo $prev_head),"
    echo "   ${REF:-HEAD} at $(echo $new_head)."
    echo "   The previous image runs 'alembic upgrade head' at startup and does not know"
    echo "   the new revision, so it would not start. The failed release stays up."
  fi
  echo "   Database revision now: ${db_revision:-unknown (the db container did not answer)}"
  if [ -n "$BACKUP_FILE" ]; then
    echo "   Dump taken just before this deploy: $BACKUP_FILE"
    echo "   To go back, restore that dump and redeploy the previous release:"
    echo "     docker compose -f $COMPOSE --env-file $ENVFILE stop backend"
    echo "     docker compose -f $COMPOSE --env-file $ENVFILE exec -T db sh -c 'dropdb --force -U \"\$POSTGRES_USER\" \"\$POSTGRES_DB\" && createdb -U \"\$POSTGRES_USER\" \"\$POSTGRES_DB\"'"
    echo "     gunzip -c $BACKUP_FILE | docker compose -f $COMPOSE --env-file $ENVFILE exec -T db sh -c 'psql -q -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\"'"
    echo "   Stop here if psql reported an error. Before redeploying, check a few row"
    echo "   counts (e.g. mdm.persons, activities.registrations) against what you expect:"
    echo "   at startup the previous release seeds every table it finds empty, so after"
    echo "   the redeploy a half-restored database can no longer be told from a seeded one."
    echo "     DEPLOY_ROLLBACK=1 ./deploy.sh $ENV $DEPLOY_PREV_REF"
  else
    echo "   This deploy took no dump (the db container was not running); see ${BACKUP_DIR:-./backups}."
  fi
  return 1
}

# Smoke and post-check together are the GATE (#395, #604): if either fails, we roll
# back once, automatically, to what ran before this deploy (loop guard through
# DEPLOY_ROLLBACK) — unless this release adds a migration (#1203), see
# `rollback_can_start`.
CUR="$(git describe --tags --always 2>/dev/null || echo '')"
if [ -z "${DEPLOY_ROLLBACK:-}" ] && [ -n "$DEPLOY_PREV_REF" ] && [ "$DEPLOY_PREV_REF" != "$CUR" ]; then
  if ! rollback_can_start; then
    exit 1
  fi
  echo ">>> Automatic rollback to $DEPLOY_PREV_REF (once)."
  DEPLOY_ROLLBACK=1 DEPLOY_REEXEC= exec "$0" "$ENV" "$DEPLOY_PREV_REF"
fi
echo "!! No (further) automatic rollback possible — intervene by hand (runbook: architecture document §19.5; backup in ${BACKUP_DIR:-./backups})."
exit 1
