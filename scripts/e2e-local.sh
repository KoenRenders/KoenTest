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

URL="postgresql+psycopg2://postgres:postgres@db:5432/${DB_NAAM}"
NAAM="raake2e-${slug}"
NETWERK="dev_internal"
IMAGE="raaktest-backend:${slug}"
POORT=8000

"${COMPOSE[@]}" up -d db >/dev/null
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

docker exec "$NAAM" sh -c 'alembic upgrade head >/dev/null 2>&1 && python seed_postal_codes.py >/dev/null'
docker exec -e E2E_SEED=1 "$NAAM" python seed_e2e.py | tail -1

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
docker exec -d -e CHAT_ENABLED=true -e STT_MODE=native_first -e STT_PROVIDER=mock \
  -e PLATFORM_HOSTS=platform.localhost \
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
exec docker exec \
  -e E2E_BASE_URL="http://127.0.0.1:${POORT}" -e E2E_SEEDED=1 \
  "$NAAM" python -m pytest -o cache_dir=/tmp/pytest_cache "${DOEL[@]}"
