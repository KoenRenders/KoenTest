#!/usr/bin/env bash
# Restore-oefening (#395): bewijs dat een backup ook echt terug te zetten is.
#
# Neemt de NIEUWSTE dump uit $BACKUP_DIR (default ./backups), zet die in een
# wegwerp-database in de draaiende db-container en telt een paar kerntabellen.
# Draai dit minstens één keer per release (architectuurdoc §19.1) — en vóór
# v2.0 fungeert dit als de upgrade-generale op een PROD-restore (epic #393).
#
#   ./scripts/restore-test.sh hdev|uat|prod [pad/naar/dump.sql.gz]
#
# #1232: the exercise could not have succeeded since the schema split. The
# counts named `members`, `persons`, … without a schema, and those tables now
# live in `mdm`, `activities` and `payment`, so the count failed under
# `set -e` and the throwaway database stayed behind. And the restore ran
# without `ON_ERROR_STOP`, so a dump that broke halfway gave errors but no exit
# code — a half restore could have been reported as a success. Now:
#
# - the restore stops at the first error (`-v ON_ERROR_STOP=1`), the same flag
#   the rollback stop message of deploy.sh prescribes (#1203);
# - the counts are schema-qualified and are the same tables that stop message
#   asks to check before a redeploy, plus the alembic revision of the dump;
# - a trap drops the throwaway database on every exit, failed or not.
set -euo pipefail
ENV="${1:?Gebruik: ./scripts/restore-test.sh hdev|uat|prod [dump.sql.gz]}"
COMPOSE=(docker compose -f "docker-compose.${ENV}.yml" --env-file ".env.${ENV}")
BACKUP_DIR="${BACKUP_DIR:-./backups}"
DUMP="${2:-$(ls -1t "$BACKUP_DIR"/*.sql.gz 2>/dev/null | head -1)}"
[ -n "$DUMP" ] || { echo "Geen dump gevonden in $BACKUP_DIR"; exit 1; }
echo "== Restore-oefening met: $DUMP =="

RESTORE_DB="restore_test"

# Runs one SQL statement as the superuser, on the real database of the
# container — the one that can create and drop the throwaway one.
admin_sql() {
  "${COMPOSE[@]}" exec -T db sh -c "psql -v ON_ERROR_STOP=1 -q -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"$1\""
}

cleanup() {
  admin_sql "DROP DATABASE IF EXISTS ${RESTORE_DB};" >/dev/null 2>&1 || true
}
trap cleanup EXIT

admin_sql "DROP DATABASE IF EXISTS ${RESTORE_DB};"
admin_sql "CREATE DATABASE ${RESTORE_DB};"
gunzip -c "$DUMP" | "${COMPOSE[@]}" exec -T db sh -c \
  "psql -q -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d ${RESTORE_DB}"

echo "== Sanity-tellingen =="
"${COMPOSE[@]}" exec -T db sh -c "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d ${RESTORE_DB} -c \"
  SELECT 'alembic_version' t, string_agg(version_num, ', ') AS n FROM public.alembic_version
  UNION ALL SELECT 'mdm.members', count(*)::text FROM mdm.members
  UNION ALL SELECT 'mdm.persons', count(*)::text FROM mdm.persons
  UNION ALL SELECT 'activities.registrations', count(*)::text FROM activities.registrations
  UNION ALL SELECT 'payment.payment_records', count(*)::text FROM payment.payment_records;\""

echo "== Restore-oefening geslaagd; wegwerp-DB wordt opgeruimd. =="
