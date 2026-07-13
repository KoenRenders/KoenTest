#!/usr/bin/env bash
# Restore-oefening (#395): bewijs dat een backup ook echt terug te zetten is.
#
# Neemt de NIEUWSTE dump uit $BACKUP_DIR (default ./backups), zet die in een
# wegwerp-database in de draaiende db-container en telt een paar kerntabellen.
# Draai dit minstens één keer per release (architectuurdoc §19.1) — en vóór
# v2.0 fungeert dit als de upgrade-generale op een PROD-restore (epic #393).
#
#   ./scripts/restore-test.sh hdev|uat|prod [pad/naar/dump.sql.gz]
set -euo pipefail
ENV="${1:?Gebruik: ./scripts/restore-test.sh hdev|uat|prod [dump.sql.gz]}"
COMPOSE=(docker compose -f "docker-compose.${ENV}.yml" --env-file ".env.${ENV}")
BACKUP_DIR="${BACKUP_DIR:-./backups}"
DUMP="${2:-$(ls -1t "$BACKUP_DIR"/*.sql.gz 2>/dev/null | head -1)}"
[ -n "$DUMP" ] || { echo "Geen dump gevonden in $BACKUP_DIR"; exit 1; }
echo "== Restore-oefening met: $DUMP =="

RESTORE_DB="restore_test"
"${COMPOSE[@]}" exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c 'DROP DATABASE IF EXISTS ${RESTORE_DB};' -c 'CREATE DATABASE ${RESTORE_DB};'"
gunzip -c "$DUMP" | "${COMPOSE[@]}" exec -T db sh -c "psql -q -U \"\$POSTGRES_USER\" -d ${RESTORE_DB}"

echo "== Sanity-tellingen =="
"${COMPOSE[@]}" exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d ${RESTORE_DB} -c \"
  SELECT 'members' t, count(*) FROM members
  UNION ALL SELECT 'persons', count(*) FROM persons
  UNION ALL SELECT 'registrations', count(*) FROM registrations
  UNION ALL SELECT 'payment_records', count(*) FROM payment_records;\""

"${COMPOSE[@]}" exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c 'DROP DATABASE ${RESTORE_DB};'"
echo "== Restore-oefening geslaagd; wegwerp-DB opgeruimd. =="
