#!/usr/bin/env bash
# Restic-back-up van de PROD-server naar de Hetzner Storage Box.
#
# Back-upt de dagelijkse database-dumps en de .env.prod (secrets, niet in git)
# naar een aparte Restic-repo. Bedoeld om door een systemd-timer dagelijks
# gedraaid te worden, kort na de nachtelijke pg_dump.
set -Eeuo pipefail

################################
# CONFIG
################################

RESTIC_REPOSITORY="sftp:hetzner-storagebox:restic-raakmillegem"
RESTIC_PASSWORD_FILE="/root/.config/restic/raakmillegem-password"

LOG_DIR="/var/log/raakmillegem"
TIMESTAMP="$(date '+%Y-%m-%d_%H-%M-%S')"
LOG_FILE="${LOG_DIR}/restic_backup_${TIMESTAMP}.log"

# Heel /opt back-uppen: code-checkouts, .env-files en de pg_dump-SQL-dumps.
# Samen met de SQL-dump (consistente momentopname van de database) geeft dit
# een volledige, consistente restore. De live PostgreSQL-datafiles zitten in
# een Docker-volume buiten /opt en worden bewust niet rauw mee gekopieerd.
BACKUP_PATHS=(
  "/opt"
)

KEEP_DAILY=7
KEEP_WEEKLY=4
KEEP_MONTHLY=6

################################
# FUNCTIES
################################

log() {
  echo "[$(date '+%F %T')] $*" | tee -a "$LOG_FILE"
}

fail() {
  log "FOUT: $*"
  exit 1
}

cleanup_on_error() {
  local exit_code=$?
  if [[ $exit_code -ne 0 ]]; then
    log "Script gestopt met foutcode ${exit_code}"
  fi
}
trap cleanup_on_error EXIT

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Commando niet gevonden: $1"
}

################################
# PRECHECKS
################################

log "==== PRECHECKS ===="

mkdir -p "$LOG_DIR"

require_cmd restic
require_cmd tee

[[ -f "$RESTIC_PASSWORD_FILE" ]] || fail "Restic password file ontbreekt: $RESTIC_PASSWORD_FILE"

for path in "${BACKUP_PATHS[@]}"; do
  [[ -e "$path" ]] || fail "Pad bestaat niet: $path"
done

export RESTIC_REPOSITORY
export RESTIC_PASSWORD_FILE

################################
# INIT (indien nodig)
################################

log "==== START BACKUP ===="
log "Repository: $RESTIC_REPOSITORY"

if ! restic snapshots >/dev/null 2>&1; then
  log "Initialiseer restic repo..."
  restic init | tee -a "$LOG_FILE"
fi

################################
# BACKUP
################################

log "Start restic backup"

restic backup "${BACKUP_PATHS[@]}" \
  --verbose \
  2>&1 | tee -a "$LOG_FILE"

log "Backup klaar"

################################
# RETENTION
################################

log "Opschonen oude backups"

restic forget --prune \
  --keep-daily "$KEEP_DAILY" \
  --keep-weekly "$KEEP_WEEKLY" \
  --keep-monthly "$KEEP_MONTHLY" \
  2>&1 | tee -a "$LOG_FILE"

################################
# STATUS
################################

log "Snapshots overzicht:"
restic snapshots 2>&1 | tee -a "$LOG_FILE"

# Oude logs opruimen (>30 dagen).
find "$LOG_DIR" -name 'restic_backup_*.log' -mtime +30 -delete || true

log "==== BACKUP KLAAR ===="
