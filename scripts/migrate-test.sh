#!/usr/bin/env bash
# Migration rehearsal (#2196): run a release tag's migrations on a throwaway copy
# of an environment's dump, before the deploy does it for real.
#
#   ./scripts/migrate-test.sh <env> <tag> [dump.sql.gz]  (run from the env's checkout)
#
# Why: the PROD deploy of v2.17.0 failed in migration 212 on data no other
# environment held. `restore-test.sh` proves a dump restores; it does not run the
# NEXT release's migrations on it. This does, and only that:
#
# - the dump (the newest of $BACKUP_DIR, default ./backups, or the one named) is
#   restored into the throwaway database `migrate_test` of the environment's own db
#   container — `ON_ERROR_STOP`, and a trap drops it on every exit;
# - the tag's backend image is built from a copy of the tag (`git archive`), never
#   from the checkout of the environment, which is not touched;
# - one container of that image runs `alembic upgrade head` on the environment's
#   network against the throwaway database: no app start, no seeding, no jobs, no
#   mail (the container is given no mail or payment settings at all);
# - the report holds revisions, the `Running upgrade` lines, the first error and
#   counts — never rows. Nothing leaves the server.
#
# Exit code: 0 only when the head was reached.
set -uo pipefail
ENV="${1:?Usage: ./scripts/migrate-test.sh hdev|uat|prod <tag> [dump.sql.gz]}"
TAG="${2:?Usage: ./scripts/migrate-test.sh hdev|uat|prod <tag> [dump.sql.gz]}"
COMPOSE=(docker compose -f "docker-compose.${ENV}.yml" --env-file ".env.${ENV}")
BACKUP_DIR="${BACKUP_DIR:-./backups}"
DUMP="${3:-$(ls -1t "$BACKUP_DIR"/*.sql.gz 2>/dev/null | head -1)}"
[ -n "$DUMP" ] || { echo "No dump found in $BACKUP_DIR"; exit 1; }

THROWAWAY_DB="migrate_test"
WORK="$(mktemp -d)"
IMAGE="raak-migrate-test:${ENV}-$$"
rc=1

admin_sql() {
  "${COMPOSE[@]}" exec -T db sh -c "psql -v ON_ERROR_STOP=1 -q -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"$1\""
}

cleanup() {
  admin_sql "DROP DATABASE IF EXISTS ${THROWAWAY_DB};" >/dev/null 2>&1 || true
  docker rmi -f "$IMAGE" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

# Counts of the same tables restore-test.sh names, and the revision, in one table.
counts() {
  "${COMPOSE[@]}" exec -T db sh -c "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d ${THROWAWAY_DB} -c \"
    SELECT 'alembic_version' t, string_agg(version_num, ', ') AS n FROM public.alembic_version
    UNION ALL SELECT 'mdm.members', count(*)::text FROM mdm.members
    UNION ALL SELECT 'mdm.persons', count(*)::text FROM mdm.persons
    UNION ALL SELECT 'activities.registrations', count(*)::text FROM activities.registrations
    UNION ALL SELECT 'payment.payment_records', count(*)::text FROM payment.payment_records;\""
}

echo "== Migration rehearsal: ${ENV} dump ${DUMP} -> ${TAG} =="

# 1. The tag's code. A tag the checkout does not know yet is fetched (refs only,
#    the same as a deploy does); the working tree and the branch stay as they are.
if ! git rev-parse -q --verify "refs/tags/${TAG}^{commit}" >/dev/null; then
  git fetch -q --tags origin || { echo "Cannot fetch tags"; exit 1; }
fi
git rev-parse -q --verify "refs/tags/${TAG}^{commit}" >/dev/null || { echo "Unknown tag: ${TAG}"; exit 1; }
git archive "refs/tags/${TAG}" backend | tar -x -C "$WORK" || { echo "Cannot unpack ${TAG}"; exit 1; }

# 2. The throwaway database from the dump.
admin_sql "DROP DATABASE IF EXISTS ${THROWAWAY_DB};" || exit 1
admin_sql "CREATE DATABASE ${THROWAWAY_DB};" || exit 1
gunzip -c "$DUMP" | "${COMPOSE[@]}" exec -T db sh -c \
  "psql -q -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d ${THROWAWAY_DB}" >/dev/null || { echo "The dump does not restore"; exit 1; }
echo "== Before =="
counts || exit 1

# 3. The image, and the one-off container on the environment's network. The
#    connection string goes in a file that only this user reads, never on a command
#    line or into the report.
docker build -q -t "$IMAGE" "$WORK/backend" >/dev/null || { echo "The image of ${TAG} does not build"; exit 1; }
NETWORK="$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' \
  "$("${COMPOSE[@]}" ps -q db)" | awk '{print $1}')"
[ -n "$NETWORK" ] || { echo "Cannot find the network of the db container"; exit 1; }
ENVFILE="$WORK/migrate.env"
( umask 077
  "${COMPOSE[@]}" exec -T db sh -c \
    "echo DATABASE_URL=postgresql://\$POSTGRES_USER:\$POSTGRES_PASSWORD@db:5432/${THROWAWAY_DB}" > "$ENVFILE" )
# The settings refuse a weak key outside development, also for a migration. A fresh
# random one: this container signs nothing and the key is gone with it.
echo "SECRET_KEY=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')" >> "$ENVFILE"

LOG="$WORK/alembic.log"
docker run --rm --network "$NETWORK" --env-file "$ENVFILE" -w /app "$IMAGE" alembic upgrade head >"$LOG" 2>&1
rc=$?

echo "== Alembic =="
grep 'Running upgrade' "$LOG" || echo "(no upgrade lines)"
if [ "$rc" -ne 0 ]; then
  echo "== First error =="
  # The end of the traceback, where the exception stands; the connection string
  # is masked in case an error line quotes it.
  sed -n '/Traceback/,$p' "$LOG" | sed "s#postgresql://[^ @]*@#postgresql://***@#g" | tail -30
  echo "== Migration rehearsal FAILED; the throwaway database is dropped. =="
  exit "$rc"
fi

echo "== After =="
counts || exit 1
HEAD_REACHED="$(docker run --rm --network "$NETWORK" --env-file "$ENVFILE" -w /app "$IMAGE" alembic heads 2>/dev/null | awk '{print $1}')"
echo "head=${HEAD_REACHED}"
echo "== Migration rehearsal succeeded; the throwaway database is dropped. =="
exit 0
