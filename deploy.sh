#!/usr/bin/env bash
# Deployt één omgeving. Vervangt deploy-hdev.sh / deploy-uat.sh / deploy-prod.sh,
# die nu dunne wrappers om dit script zijn.
#
#   ./deploy.sh hdev                      # volgt master (integratielijn, geen tag)
#   ./deploy.sh uat  v2.0.0               # exacte release-tag
#   ./deploy.sh prod v2.0.0 --remove-orphans
#
# Waarom één script: deploy-uat.sh en deploy-prod.sh waren regel voor regel
# identiek op de string uat/prod na. Twee kopieën van het deploy-pad naar
# productie is een driftrisico — een fix die in de ene landt en niet in de andere
# valt niemand op. De verschillen tussen de omgevingen staan nu als expliciete
# vlaggen in het configblok hieronder, in plaats van als stilzwijgende afwezigheid.
#
# UAT/PROD draaien bewust op een vastgepinde tag: we gaan er NIET van uit dat
# master gelijk is aan de laatste release. HDEV is de integratielijn en volgt master.
set -euxo pipefail

cd "$(dirname "$0")"

ENV="${1:?Geef de omgeving op: hdev | uat | prod (bv. ./deploy.sh uat v2.0.0)}"
shift

# ── Configblok per omgeving ──────────────────────────────────────────────────
# SOURCE   master = volg de integratielijn; tag = exacte release-tag verplicht
# BACKUP   pre-migratie-dump van de databank vóór de rebuild (#395)
# ROLLBACK eenmalige automatische terugval als de rooktest faalt (#395)
# CADDY    own = eigen Caddy in de stack (HDEV); shared = de gedeelde proxy,
#          die apart gaat via deploy-caddy.sh
case "$ENV" in
  hdev)
    COMPOSE="docker-compose.hdev.yml"; ENVFILE=".env.hdev"
    SOURCE="master"; BACKUP=0; ROLLBACK=0; CADDY="own"
    SMOKE_BASE_DEFAULT="http://localhost:8081"
    ;;
  uat)
    COMPOSE="docker-compose.uat.yml"; ENVFILE=".env.uat"
    SOURCE="tag"; BACKUP=1; ROLLBACK=1; CADDY="shared"
    SMOKE_BASE_DEFAULT=""
    ;;
  prod)
    COMPOSE="docker-compose.prod.yml"; ENVFILE=".env.prod"
    SOURCE="tag"; BACKUP=1; ROLLBACK=1; CADDY="shared"
    SMOKE_BASE_DEFAULT=""
    ;;
  *)
    echo "FOUT: onbekende omgeving '$ENV' — kies hdev, uat of prod." >&2
    exit 1
    ;;
esac

dc() { docker compose -f "$COMPOSE" --env-file "$ENVFILE" "$@"; }

# ── Ref bepalen ──────────────────────────────────────────────────────────────
REF=""
if [ "$SOURCE" = "tag" ]; then
  REF="${1:?Geef de te deployen release-tag op, bv: ./deploy.sh $ENV v2.0.0}"
  shift
fi
# Wat er overblijft gaat door naar `docker compose up` (bv. --remove-orphans).
UP_EXTRA=("$@")

# Rollback-doel (#395): onthoud wat er NU draait, vóór de checkout. Eén keer
# gezet; overleeft de re-exec en de eventuele rollback-exec via export.
if [ "$ROLLBACK" = 1 ]; then
  export DEPLOY_PREV_REF="${DEPLOY_PREV_REF:-$(git describe --tags --always 2>/dev/null || echo '')}"
fi

# ── Broncode ophalen ─────────────────────────────────────────────────────────
if [ "$SOURCE" = "master" ]; then
  # --tags zodat `git describe` een zinnige release-tag toont in de versie-log (#151).
  git fetch --tags --force origin master
  git reset --hard origin/master
else
  # Detached HEAD is hier gewenst: je draait een exacte commit, geen bewegende branch.
  git fetch --tags --prune origin
  git checkout --detach "$REF"
fi

# Robuustheid (#162): na de checkout draait mogelijk nog de vorige scriptversie.
# Re-exec één keer de nu-uitgecheckte versie zodat de rest (versie-export, build,
# smoke) uit de juiste scriptinhoud komt. De guard voorkomt een oneindige lus.
if [ -z "${DEPLOY_REEXEC:-}" ]; then
  export DEPLOY_REEXEC=1
  exec "$0" "$ENV" ${REF:+"$REF"} ${UP_EXTRA[@]+"${UP_EXTRA[@]}"}
fi

# Vang vanaf hier alle output (build + smoke) op in het diagnostiek-bestand én
# toon ze op je scherm (#291). Dit is meteen de RESET van de logfile: elke deploy
# begint met een schoon bestand; logging.sh voegt er daarna aan toe (append).
LOG_OUT="${LOG_OUT:-/tmp/${ENV}-diagnostics.log}"
exec > >(tee "$LOG_OUT") 2>&1

# Versie + commit voor de startup-log (#151); als build-args naar de backend-image.
export APP_VERSION="$(git describe --tags --always 2>/dev/null || echo onbekend)"
export GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo onbekend)"

# ── Pre-migratie-backup ──────────────────────────────────────────────────────
# Alembic draait bij containerstart, dus de dump moet vóór de rebuild. Credentials
# komen uit de db-container zelf. Expand/contract-regel (architectuurdoc §19.5):
# binnen een release enkel additieve migraties — anders is de rollback hieronder
# schijnveiligheid en is deze backup het enige pad terug.
if [ "$BACKUP" = 1 ]; then
  BACKUP_DIR="${BACKUP_DIR:-./backups}"; mkdir -p "$BACKUP_DIR"
  if [ -n "$(dc ps -q db 2>/dev/null)" ]; then
    TS=$(date +%Y%m%d-%H%M%S)
    dc exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
      | gzip > "$BACKUP_DIR/pre-deploy-$ENV-$TS.sql.gz"
    echo "Pre-migratie-backup: $BACKUP_DIR/pre-deploy-$ENV-$TS.sql.gz"
  else
    echo "db-container niet actief — pre-migratie-backup overgeslagen (eerste deploy?)"
  fi
fi

# ── Bouwen en starten ────────────────────────────────────────────────────────
dc up --build -d ${UP_EXTRA[@]+"${UP_EXTRA[@]}"}

# HDEV heeft een eigen Caddy in de stack. Herstart die zodat wijzigingen in
# Caddyfile.hdev (bind-mount) betrouwbaar actief zijn: `caddy reload` (admin-API)
# bleek de config niet altijd over te nemen — stale routing én verdwenen
# compressie waren het gevolg. Force-recreate laadt de config vers van schijf
# (#169). UAT/PROD delen één Caddy; die gaat apart via deploy-caddy.sh.
if [ "$CADDY" = "own" ]; then
  dc up -d --force-recreate caddy
  # De zonet herstarte Caddy heeft een paar seconden nodig; wacht tot ze weer
  # serveert vóór de rooktest, anders geeft de compressie-check een valse fail.
  for _ in $(seq 1 15); do
    curl -fsS -o /dev/null "${SMOKE_BASE_DEFAULT}/" && break
    sleep 1
  done
fi

# ── Post-deploy rooktest ─────────────────────────────────────────────────────
# STRIKT ALLEEN-LEZEN, maakt geen data aan (veilig op PROD). Doel-URL = de
# publieke origin uit het env-bestand (Caddy proxiet /api/* naar de backend);
# bij HDEV is dat de lokale poort.
SMOKE_BASE="${SMOKE_BASE:-$SMOKE_BASE_DEFAULT}"
if [ -z "$SMOKE_BASE" ]; then
  SMOKE_BASE="$(sed -nE "s/^FRONTEND_URL=[\"']?([^\"']*)[\"']?.*/\1/p" "$ENVFILE" | head -1)"
fi

if [ -z "$SMOKE_BASE" ]; then
  echo "FRONTEND_URL onbekend in $ENVFILE — rooktest overgeslagen"
  exit 0
fi

if BASE="$SMOKE_BASE" ./tests/run-all.sh; then
  echo "Smoke OK op ${REF:-master}."
  exit 0
fi

echo "!! SMOKE FAALDE op ${REF:-master}."
if [ "$ROLLBACK" != 1 ]; then
  exit 1
fi

# Smoke is een GATE (#395): faalt hij, dan rollen we één keer automatisch terug
# naar wat er vóór deze deploy draaide (loop-guard via DEPLOY_ROLLBACK).
CUR="$(git describe --tags --always 2>/dev/null || echo '')"
if [ -z "${DEPLOY_ROLLBACK:-}" ] && [ -n "$DEPLOY_PREV_REF" ] && [ "$DEPLOY_PREV_REF" != "$CUR" ]; then
  echo ">>> Automatische rollback naar $DEPLOY_PREV_REF (eenmalig)."
  DEPLOY_ROLLBACK=1 DEPLOY_REEXEC= exec "$0" "$ENV" "$DEPLOY_PREV_REF"
fi
echo "!! Geen (verdere) automatische rollback mogelijk — handmatig ingrijpen (runbook: architectuurdoc §19.5; backup in ${BACKUP_DIR:-./backups})."
exit 1
