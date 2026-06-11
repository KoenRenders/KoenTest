#!/usr/bin/env bash
# Dagelijkse logische back-up van de PostgreSQL-database via pg_dump.
#
# Schrijft een gecomprimeerde SQL-dump naar /backups (host-gemount). Lokaal
# worden enkel de laatste KEEP_DAYS dagen bewaard — de lange historie en de
# off-site kopie verlopen via Restic, dat deze map mee back-upt.
set -euo pipefail

: "${DB_USER:?DB_USER ontbreekt}"
: "${DB_NAME:?DB_NAME ontbreekt}"
: "${PGPASSWORD:?PGPASSWORD ontbreekt}"
BACKUP_PREFIX="${BACKUP_PREFIX:-db}"
KEEP_DAYS="${KEEP_DAYS:-7}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
DB_HOST="${DB_HOST:-db}"
# Vast tijdstip (uur, 00-23) waarop de dagelijkse dump draait. Standaard 02:00,
# zodat alle activiteit van de vorige dag erin zit vóór de nachtelijke Restic-run.
BACKUP_HOUR="${BACKUP_HOUR:-02}"

echo "[db-backup] gestart — dagelijkse pg_dump van '${DB_NAME}' om ${BACKUP_HOUR}:00, lokaal ${KEEP_DAYS} dagen bewaren"

while true; do
  # Wacht tot het volgende geplande tijdstip.
  now=$(date +%s)
  next=$(date -d "today ${BACKUP_HOUR}:00" +%s)
  [ "$next" -le "$now" ] && next=$(date -d "tomorrow ${BACKUP_HOUR}:00" +%s)
  sleep $(( next - now ))

  ts=$(date +%Y%m%d-%H%M%S)
  out="${BACKUP_DIR}/${BACKUP_PREFIX}-${ts}.sql.gz"
  echo "[db-backup] $(date -Iseconds) — dump naar ${out}"
  if pg_dump -h "${DB_HOST}" -U "${DB_USER}" "${DB_NAME}" | gzip > "${out}.tmp"; then
    mv "${out}.tmp" "${out}"
    echo "[db-backup] klaar: ${out}"
  else
    echo "[db-backup] FOUT: pg_dump mislukt" >&2
    rm -f "${out}.tmp"
  fi
  # Oude lokale back-ups opruimen (Restic bewaart de lange historie off-site).
  find "${BACKUP_DIR}" -name "${BACKUP_PREFIX}-*.sql.gz" -mtime "+${KEEP_DAYS}" -delete || true
done
