#!/usr/bin/env bash
# Deployt één omgeving. Vervangt deploy-hdev.sh / deploy-uat.sh / deploy-prod.sh;
# die bestonden na #576 nog als dunne wrappers en zijn met #577 verwijderd, nadat
# v2.0.0 op UAT én PROD draaide. Ze waren dragend tijdens de cutover: het
# deploy-script van v1.14.0 doet na de checkout een `exec "$0"` (#162), en dan moet
# de oude bestandsnaam in de NIEUWE tag nog bestaan.
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
# KETEN_GATE / LOG_GATE  na-controle (#604): 1 = poort (falen rolt terug op de
#          omgevingen die ROLLBACK=1 hebben), 0 = rapporterend. Zie "Na-controle".
case "$ENV" in
  hdev)
    COMPOSE="docker-compose.hdev.yml"; ENVFILE=".env.hdev"
    SOURCE="master"; BACKUP=0; ROLLBACK=0; CADDY="own"
    KETEN_GATE=0; LOG_GATE=0
    SMOKE_BASE_DEFAULT="http://localhost:8081"
    ;;
  uat)
    COMPOSE="docker-compose.uat.yml"; ENVFILE=".env.uat"
    SOURCE="tag"; BACKUP=1; ROLLBACK=1; CADDY="shared"
    KETEN_GATE=1; LOG_GATE=0
    SMOKE_BASE_DEFAULT=""
    ;;
  prod)
    COMPOSE="docker-compose.prod.yml"; ENVFILE=".env.prod"
    SOURCE="tag"; BACKUP=1; ROLLBACK=1; CADDY="shared"
    KETEN_GATE=1; LOG_GATE=0
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
# komen uit de db-container zelf.
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
    echo "Pre-migratie-backup: $BACKUP_FILE"
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
fi

# ── Na-controle: migratieketen en schone start (#604) ────────────────────────
# Na élke deploy horen drie dingen te kloppen: precies één alembic-head, een
# `current` die daaraan gelijk is, en een opstart zonder fouten. `raakctl diagnose`
# verzamelt ze keurig — maar dat draai je ápart, ná de deploy, en dat rapport heeft
# geen exit-code die iets tegenhoudt. Vergeet je het, dan merkt niemand het.
#
# De rooktest ziet deze twee fouten niet: hij toetst dat publieke pagina's 200 geven
# en dat de admin afgeschermd is. Een gesplitste migratieketen en een backend die pas
# ná die eerste geslaagde request stukloopt, passeren dat ongemerkt.
#
#   | check          | hdev         | uat / prod   |
#   |----------------|--------------|--------------|
#   | migratieketen  | rapporterend | POORT        |
#   | schone start   | rapporterend | rapporterend |
#
# De ketencheck is deterministisch — twee heads zijn twee heads — dus die mag meteen
# een poort zijn. De logcheck niet: een valse terugrol op PROD door één ERROR-regel
# is duurder dan de melding missen, en we weten nog niet hoe stil die logs werkelijk
# zijn. Ze draait daarom eerst een release lang luid mee. Zet LOG_GATE=1 in het
# configblok zodra dat wel bekend is.
#
# Beide draaien via `dc exec -T backend`, dus met het env-bestand van deze omgeving —
# hetzelfde patroon als logging.sh. En ze draaien binnen dezelfde DEPLOY_ROLLBACK-
# guard als de rooktest, zodat een deploy nooit twee keer terugrolt.
_revisies() { sed -nE 's/^([0-9a-z_]+)([[:space:]].*)?$/\1/p'; }

migratieketen_ok() {
  local heads current aantal
  heads="$(dc exec -T backend alembic heads 2>/dev/null | _revisies || true)"
  current="$(dc exec -T backend alembic current 2>/dev/null | _revisies || true)"
  aantal="$(printf '%s\n' "$heads" | grep -c . || true)"
  if [ "$aantal" -ne 1 ]; then
    echo "!! Migratieketen: $aantal heads i.p.v. 1 — de keten is gesplitst: [$(echo $heads)]"
    return 1
  fi
  if [ "$current" != "$heads" ]; then
    echo "!! Migratieketen: alembic current is [$(echo $current)] en niet [$heads] — een migratie raakte niet toegepast."
    return 1
  fi
  echo "Migratieketen OK: één head ($heads), current gelijk."
}

schone_start_ok() {
  # STRAK gescoped op het opstartvenster: van "==> Running database migrations..."
  # (de eerste regel die startup.sh print) tot "Uvicorn running". Verkeer ná de start
  # telt bewust NIET mee — een Mollie-webhook die 404't of een gebruiker die een
  # ongeldige aanvraag doet in de seconden na een deploy, mag geen terugrol worden.
  # Bij een herstart neemt awk het LAATSTE venster: elke startmarkering begint opnieuw.
  local venster fouten
  venster="$(dc logs backend --tail=500 2>&1 | awk '
      /==> Running database migrations/ { buf = ""; bezig = 1 }
      bezig { buf = buf $0 "\n" }
      bezig && /Uvicorn running on/ { bezig = 0 }
      END { printf "%s", buf }')"
  if [ -z "$venster" ]; then
    echo "!! Schone start: geen opstartvenster in de laatste 500 backend-regels — is de backend gestart?"
    return 1
  fi
  if ! printf '%s' "$venster" | grep -q 'Uvicorn running on'; then
    echo "!! Schone start: de backend bereikte 'Uvicorn running' niet; het opstarten liep vast."
    return 1
  fi
  fouten="$(printf '%s' "$venster" | grep -iE 'error|traceback|exception' || true)"
  if [ -n "$fouten" ]; then
    echo "!! Schone start: fouten tijdens het opstarten:"
    printf '%s\n' "$fouten"
    return 1
  fi
  echo "Schone start OK: geen ERROR/Traceback/Exception tussen containerstart en 'Uvicorn running'."
}

applicatielog_regel() {
  # INFORMATIEF, nooit een poort (#766). De controle die dit issue vraagt is: staat
  # er na de deploy nog iets in dat van vóór de deploy komt? Dat lees je hieraan af —
  # is de oudste regel ouder dan deze deploy, dan heeft het log de container
  # overleefd. Een lege of ontbrekende map is geen reden om iets terug te rollen; het
  # is wel iets wat je hier hoort te zien in plaats van te moeten gaan zoeken.
  local uit
  uit="$(dc exec -T backend sh -c \
    'f=/var/log/raak/app.log; [ -f "$f" ] || exit 3; echo "$(wc -l < "$f") regels, oudste: $(head -1 "$f" | cut -c1-19)"' \
    2>/dev/null || true)"
  if [ -z "$uit" ]; then
    echo "Applicatielog: /var/log/raak/app.log nog niet aanwezig — bij de eerste deploy ná #766 is dat normaal."
  else
    echo "Applicatielog (overleeft de deploy): $uit"
  fi
}

nacontrole() {
  local mislukt=0
  echo "== Na-controle (#604): migratieketen en schone start =="
  if ! migratieketen_ok; then
    if [ "$KETEN_GATE" = 1 ]; then mislukt=1; else echo "   (rapporterend op $ENV — dit rolt niets terug)"; fi
  fi
  if ! schone_start_ok; then
    if [ "$LOG_GATE" = 1 ]; then mislukt=1; else echo "   (rapporterend op $ENV — dit rolt niets terug)"; fi
  fi
  applicatielog_regel
  return $mislukt
}

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

# Wacht tot de site antwoordt vóór de rooktest begint (#800). Deze lus stond
# eerder BINNEN de `own`-tak en pollde `$SMOKE_BASE_DEFAULT` — dat is leeg op UAT
# en PROD, dus daar draaide ze nooit. De bescherming zat op de omgeving die haar
# het minst nodig heeft, en ontbrak op de twee waar een terugrol echte gevolgen
# heeft: de compressie-check kreeg een 502 (Caddy comprimeert een foutpagina niet),
# de rooktest faalde, en het script rolde een gezonde deploy terug.
#
# Gemeten op 9 september 2026 bij het gelijkzetten van UAT met v2.0.1: `1 OK ·
# 1 gefaald` op de compressie, automatische terugrol, dezelfde fout op de
# teruggerolde versie, en een minuut later drie keer netjes `content-encoding:
# zstd`. De stack was gezond; alleen de test was te vroeg.
#
# `curl -fsS` faalt al op een 502, dus dit wacht op een échte 200 en niet op
# "iets antwoordt". Dertig pogingen: antwoordt de backend daarna nog niet, dan is
# dat een echte fout en hoort de rooktest gewoon te falen.
for _ in $(seq 1 30); do
  curl -fsS -o /dev/null "${SMOKE_BASE}/" && break
  sleep 1
done

FAAL=""
if ! BASE="$SMOKE_BASE" ./tests/run-all.sh; then
  FAAL="SMOKE"
elif ! nacontrole; then
  FAAL="NA-CONTROLE"
fi

if [ -z "$FAAL" ]; then
  echo "Smoke + na-controle OK op ${REF:-master}."
  exit 0
fi

echo "!! $FAAL FAALDE op ${REF:-master}."
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
    echo "     DEPLOY_ROLLBACK=1 ./deploy.sh $ENV $DEPLOY_PREV_REF"
  else
    echo "   This deploy took no dump (the db container was not running); see ${BACKUP_DIR:-./backups}."
  fi
  return 1
}

# Smoke en na-controle zijn samen de GATE (#395, #604): faalt er een, dan rollen we
# één keer automatisch terug
# naar wat er vóór deze deploy draaide (loop-guard via DEPLOY_ROLLBACK) — unless
# this release adds a migration (#1203), see `rollback_can_start`.
CUR="$(git describe --tags --always 2>/dev/null || echo '')"
if [ -z "${DEPLOY_ROLLBACK:-}" ] && [ -n "$DEPLOY_PREV_REF" ] && [ "$DEPLOY_PREV_REF" != "$CUR" ]; then
  if ! rollback_can_start; then
    exit 1
  fi
  echo ">>> Automatische rollback naar $DEPLOY_PREV_REF (eenmalig)."
  DEPLOY_ROLLBACK=1 DEPLOY_REEXEC= exec "$0" "$ENV" "$DEPLOY_PREV_REF"
fi
echo "!! Geen (verdere) automatische rollback mogelijk — handmatig ingrijpen (runbook: architectuurdoc §19.5; backup in ${BACKUP_DIR:-./backups})."
exit 1
