#!/usr/bin/env bash
# Draait de playwright-e2e's lokaal tegen een VERSE databank (#719/#728).
#
# Waarom vers en niet hergebruikt: de e2e's verbruiken hun seed. Ze bevestigen de
# openstaande betaling, schrappen het lidmaatschap, wijzigen aantallen — allemaal
# eenrichtingsverkeer. Een tweede run tegen dezelfde databank vindt die data dus
# al opgebruikt en zakt op dingen die niets met je wijziging te maken hebben:
# gemeten viel `test_een_lopende_actie_is_zichtbaar` om met "geen openstaande
# betaling om te bevestigen", en `test_bestelregel_wijzigen…` vond geen bewerkbaar
# detailpaneel meer.
#
# In CI valt dat nooit op — daar is de databank elke run vers — dus het is geen
# CI-probleem maar een eigenschap van de tests die CI toevallig verbergt. Dit
# script maakt die eigenschap onschadelijk door hetzelfde te doen als CI.
#
# Gebruik:
#   scripts/e2e-local.sh                                   # alle e2e's
#   scripts/e2e-local.sh tests_e2e/test_iets.py            # één bestand
#   scripts/e2e-local.sh -k navigatie                      # elk pytest-argument
#
# Omgevingsvariabelen:
#   E2E_DB_NAME   overschrijft de afgeleide databanknaam
#   VERS=1        bouwt de hulpcontainer opnieuw op
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/docker-compose.dev.yml")

slug="$(basename "$ROOT" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | sed 's/_\+/_/g; s/^_//; s/_$//')"
DB_NAAM="${E2E_DB_NAME:-raake2e_${slug}}"

# ── Vangrail ─────────────────────────────────────────────────────────────────
# Staat vóór élke docker-aanroep. Dit script DROPT zijn doeldatabank — nog een
# stap destructiever dan test-local.sh, dat alleen het schema hermaakt. Leest de
# naam niet als e2e-databank, dan raken we niets aan.
case "$DB_NAAM" in
  raake2e|raake2e_*) ;;
  *)
    echo "e2e-local.sh: GEWEIGERD — '$DB_NAAM' leest niet als een e2e-databank." >&2
    echo "  Dit script DROPT zijn doel en bouwt het opnieuw op. Een naam die niet" >&2
    echo "  met 'raake2e' begint kan een echte databank zijn." >&2
    echo "  Bedoelde je een eigen naam, zet die dan via E2E_DB_NAME=raake2e_<iets>." >&2
    exit 2
    ;;
esac

NAAM="raake2e-${slug}"
NETWERK="dev_internal"
IMAGE="raaktest-backend:${slug}"
POORT=8000

# `--no-recreate`: the dev project (`name: dev`) is shared by every worktree, and
# each passes its own path to the compose file. Without the flag compose sees a
# changed configuration and REPLACES the db container on every run from another
# worktree — killing the test run that worktree had going. With it, compose only
# starts the database when it is not running, and leaves a running one alone.
"${COMPOSE[@]}" up -d --no-recreate db >/dev/null

# The credentials come from the running db container, not from this file: the
# dev database carries whatever password its volume was initialised with, and a
# hardcoded `postgres:postgres` fails the moment that is anything else (CLAUDE.md:
# never hardcode them). Read after `up`, so the container exists.
DB_USER="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_USER)"
DB_PASS="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_PASSWORD)"
URL="postgresql+psycopg2://${DB_USER}:${DB_PASS}@db:5432/${DB_NAAM}"
docker build -q -t "$IMAGE" "$ROOT/backend" >/dev/null

if [ "${VERS:-}" = "1" ]; then
  docker rm -f "$NAAM" >/dev/null 2>&1 || true
fi

if ! docker inspect -f '{{.State.Running}}' "$NAAM" >/dev/null 2>&1; then
  docker rm -f "$NAAM" >/dev/null 2>&1 || true
  echo "→ hulpcontainer $NAAM opbouwen (eenmalig; playwright + chromium, ~115 MB)…"
  docker run -d --name "$NAAM" --network "$NETWERK" \
    -v "$ROOT:/app" -w /app/backend \
    -e APP_ENV=dev -e JOBS_ENABLED=false \
    -e DATABASE_URL="$URL" \
    -e SECRET_KEY="e2e-lokaal-secret-lang-genoeg-voor-hs256" \
    -u root "$IMAGE" sleep infinity >/dev/null
  docker exec "$NAAM" pip install -q pytest playwright
  docker exec "$NAAM" playwright install --with-deps chromium >/dev/null
fi

# ── Verse databank ───────────────────────────────────────────────────────────
echo "→ ${DB_NAAM} opnieuw opbouwen"
"${COMPOSE[@]}" exec -T db sh -c \
  "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c 'DROP DATABASE IF EXISTS ${DB_NAAM} WITH (FORCE)' \
   && psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c 'CREATE DATABASE ${DB_NAAM}'" >/dev/null

# The URL at every exec and not only at creation: a helper container that already
# exists keeps the environment it was created with, so a changed password would
# otherwise only reach it after VERS=1.
# And the migration's output only when it fails: a silent `>/dev/null 2>&1` made a
# refused connection end the script with exit 1 and nothing on the screen.
if ! MIGRATIE="$(docker exec -e DATABASE_URL="$URL" "$NAAM" alembic upgrade head 2>&1)"; then
  echo "e2e-local.sh: alembic upgrade head failed on ${DB_NAAM}:" >&2
  printf '%s\n' "$MIGRATIE" | tail -20 >&2
  exit 1
fi
docker exec -e DATABASE_URL="$URL" "$NAAM" python seed_postal_codes.py >/dev/null
docker exec -e DATABASE_URL="$URL" -e E2E_SEED=1 "$NAAM" python seed_e2e.py | tail -1

# ── Server ───────────────────────────────────────────────────────────────────
# Een herstart is de eenvoudigste manier om een draaiende uvicorn te stoppen: het
# image heeft geen pkill, en de code wordt bij het importeren gelezen — een oude
# server zou dus je vorige wijziging blijven serveren.
docker restart "$NAAM" >/dev/null
# CHAT_ENABLED hier en niet bij het aanmaken van de container: anders zou een
# bestaande hulpcontainer de vlag missen tot iemand VERS=1 gebruikt, en dan toetst de
# suite stilzwijgend een scherm zonder invoerveld (#570).
# STT_MODE/STT_PROVIDER erbij (#788). `native_first` en NIET `provider_only`: de
# knop kiest dan per browser. Zonder `SpeechRecognition` — de gewone toestand in een
# headless Chromium — valt hij terug op ONZE WebSocket, en dat is het pad dat de
# dicteer-e2e toetst; een test die de Web Speech API nabootst (#762) neemt in dezelfde
# opstelling nog steeds het native pad. Met `provider_only` zou dat tweede pad
# onbereikbaar worden en die test stilzwijgend iets anders toetsen dan haar naam zegt.
# `mock` transcribeert zonder Mistral, dus dit belt niemand.
# PLATFORM_HOSTS (#870-G): de landingspagina verschijnt alleen op een platform-host,
# dus zonder dit vindt die test zijn beginpunt niet. Bewust een ANDERE naam dan de host
# waarop de rest van de suite draait (127.0.0.1): zou `localhost` hier staan, dan werd
# élke andere e2e-test een platformverzoek en kreeg `/` de landing in plaats van de
# tenantsite. Chromium resolvet `*.localhost` zelf naar loopback, dus dit heeft geen DNS
# nodig.
# ADMIN_CHAT_ENABLED (#1075): de dicteer-e2e draait ook op de Raakje-overlay van het
# activiteitenscherm, en die bestaat alleen met de beheer-assistent aan — deze
# schakelaar plus de tenantschakelaar die seed_e2e.py zet. Zelfde waarde als de e2e-job.
docker exec -d -e DATABASE_URL="$URL" -e CHAT_ENABLED=true -e STT_MODE=native_first -e STT_PROVIDER=mock \
  -e PLATFORM_HOSTS=platform.localhost -e ADMIN_CHAT_ENABLED=true \
  "$NAAM" sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${POORT} > /tmp/uvicorn.log 2>&1"
for _ in $(seq 1 30); do
  if docker exec "$NAAM" python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:${POORT}/')" 2>/dev/null; then
    break
  fi
  sleep 1
done

echo "→ playwright tegen ${DB_NAAM}"
# Begint het eerste argument met `tests_e2e`, dan is het een pad en bepaalt de
# aanroeper zelf wat er draait; anders zijn het vlaggen en gaat de hele map erbij.
#
# Niet op "zijn er argumenten?" testen: `-q` is ook een argument, en dan draaide
# pytest zónder pad — vanuit de rootdir dus óók tests/, die een TEST_DATABASE_URL
# verwacht. Dat leverde honderden errors op in plaats van een e2e-run.
case "${1:-}" in
  tests_e2e*) DOEL=("$@") ;;
  *)          DOEL=(tests_e2e/ "$@") ;;
esac
exec docker exec -e DATABASE_URL="$URL" \
  -e E2E_BASE_URL="http://127.0.0.1:${POORT}" -e E2E_SEEDED=1 \
  "$NAAM" python -m pytest -o cache_dir=/tmp/pytest_cache "${DOEL[@]}"
