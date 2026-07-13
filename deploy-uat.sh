#!/usr/bin/env bash
# Deployt een EXACTE release-tag naar UAT (geen bewegende branch).
# Gebruik: ./deploy-uat.sh v1.2.1
#
# UAT/PROD draaien bewust op een vastgepinde tag — we gaan er NIET van uit dat
# master gelijk is aan de laatste release. master kan al verder staan.
set -euxo pipefail

REF="${1:?Geef de te deployen release-tag op, bv: ./deploy-uat.sh v1.2.1}"

# Rollback-doel (#395): onthoud wat er NU draait, vóór de checkout. Eén keer
# gezet; overleeft de re-exec en de eventuele rollback-exec via export.
export DEPLOY_PREV_REF="${DEPLOY_PREV_REF:-$(git describe --tags --always 2>/dev/null || echo '')}"

# Haal de tags op en check de exacte commit uit (detached HEAD is hier gewenst).
git fetch --tags --prune origin
git checkout --detach "$REF"

# Robuustheid (#162): na de checkout draait mogelijk nog de vorige scriptversie.
# Re-exec één keer de nu-uitgecheckte versie zodat de rest (versie-export, build,
# smoke) uit de juiste scriptinhoud komt. De guard voorkomt een oneindige lus.
if [ -z "${DEPLOY_REEXEC:-}" ]; then
  export DEPLOY_REEXEC=1
  exec "$0" "$@"
fi

# Vang vanaf hier alle output (build + smoke) op in het diagnostiek-bestand én
# toon ze op je scherm (#291). Dit is meteen de RESET van de logfile: elke deploy
# begint met een schoon bestand; logging-uat.sh voegt er daarna aan toe (append).
LOG_OUT="${LOG_OUT:-/tmp/uat-diagnostics.log}"
exec > >(tee "$LOG_OUT") 2>&1

# Versie + commit voor de startup-log (#151); als build-args naar de backend-image.
export APP_VERSION="$(git describe --tags --always 2>/dev/null || echo onbekend)"
export GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo onbekend)"

# Pre-migratie-backup (#395): dump de databank vóór de rebuild (alembic draait
# bij containerstart). Credentials komen uit de db-container zelf. Expand/
# contract-regel (architectuurdoc §19.5): binnen een release enkel additieve
# migraties — anders is de rollback hieronder schijnveiligheid en is deze
# backup het enige pad terug.
BACKUP_DIR="${BACKUP_DIR:-./backups}"; mkdir -p "$BACKUP_DIR"
if [ -n "$(docker compose -f docker-compose.uat.yml --env-file .env.uat ps -q db 2>/dev/null)" ]; then
  TS=$(date +%Y%m%d-%H%M%S)
  docker compose -f docker-compose.uat.yml --env-file .env.uat exec -T db \
    sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$BACKUP_DIR/pre-deploy-uat-$TS.sql.gz"
  echo "Pre-migratie-backup: $BACKUP_DIR/pre-deploy-uat-$TS.sql.gz"
else
  echo "db-container niet actief — pre-migratie-backup overgeslagen (eerste deploy?)"
fi

docker compose -f docker-compose.uat.yml --env-file .env.uat up --build -d

# Post-deploy rooktest (alleen-lezen; maakt geen data aan). Doel-URL = de
# publieke origin uit .env.uat (Caddy proxiet /api/* naar de backend).
SMOKE_BASE="${SMOKE_BASE:-$(sed -nE "s/^FRONTEND_URL=[\"']?([^\"']*)[\"']?.*/\1/p" .env.uat | head -1)}"
if [ -n "$SMOKE_BASE" ]; then
  # Smoke is een GATE (#395): faalt hij, dan rollen we één keer automatisch
  # terug naar wat er vóór deze deploy draaide (loop-guard via DEPLOY_ROLLBACK).
  if ! BASE="$SMOKE_BASE" ./tests/run-all.sh; then
    echo "!! SMOKE FAALDE op $REF."
    CUR="$(git describe --tags --always 2>/dev/null || echo '')"
    if [ -z "${DEPLOY_ROLLBACK:-}" ] && [ -n "$DEPLOY_PREV_REF" ] && [ "$DEPLOY_PREV_REF" != "$CUR" ]; then
      echo ">>> Automatische rollback naar $DEPLOY_PREV_REF (eenmalig)."
      DEPLOY_ROLLBACK=1 DEPLOY_REEXEC= exec "$0" "$DEPLOY_PREV_REF"
    fi
    echo "!! Geen (verdere) automatische rollback mogelijk — handmatig ingrijpen (runbook: architectuurdoc §19.5; backup in $BACKUP_DIR)."
    exit 1
  fi
  echo "Smoke OK op $REF."
else
  echo "FRONTEND_URL onbekend in .env.uat — rooktest overgeslagen"
fi
