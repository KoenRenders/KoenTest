#!/usr/bin/env bash
# Draait de pytest-suite lokaal tegen de dev-stack (#719).
#
# Waarom Docker en geen venv: de backend draait op python:3.12-slim en postgres:16,
# deze machine heeft Python 3.13 en PostgreSQL 17. Een venv zou de suite draaien op
# een runtime die nergens bestaat — dan betekent een groene lokale run iets anders
# dan een groene CI-run, en dat is erger dan geen lokale run.
#
# Draait dezelfde poort als CI: eerst mypy, dan de css-controle, dan pytest (#739).
# "Lokaal groen" hoort hetzelfde te betekenen als "CI groen"; toen dit script alleen
# pytest draaide, meldde het 1532 passed terwijl CI omviel op een typefout en een
# niet-herbouwde app.css. Dat is dezelfde valse zekerheid waar #719 tegen geschreven
# is, alleen aan de andere kant.
#
# Volgorde als in CI: mypy eerst, want een typefout hoeft geen suite van anderhalf
# duizend tests af te wachten.
#
# BEWUST NIET meegenomen: de `boot`-job. Die start de echte applicatie met migraties
# en seeds — waardevol, maar traag, en hij overlapt met wat een deploy naar HDEV
# sowieso doet. Dat is een keuze, geen vergetelheid.
#
# Gebruik:
#   scripts/test-local.sh                          # de hele poort
#   scripts/test-local.sh tests/test_iets.py       # één bestand (nog steeds mét poort)
#   SNEL=1 scripts/test-local.sh -k naam           # alleen pytest, tijdens het bouwen
#
# Omgevingsvariabelen:
#   SNEL=1              sla mypy en de css-controle over (de STANDAARD is de volle poort)
#   TEST_DB_NAME        overschrijft de afgeleide databanknaam
#   TEST_DATABASE_URL   overschrijft de hele URL (wordt óók door de vangrail getoetst)
#   VERS                zet dit op 1 om de hulpcontainer opnieuw op te bouwen
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/docker-compose.dev.yml")

# ── Eigen databank per worktree ──────────────────────────────────────────────
# De suite DROPT en hermaakt het schema van haar doeldatabank. Draaien twee
# worktrees tegen dezelfde `raaktest`, dan wist de ene het schema onder de voeten
# van de andere weg, midden in een run — met foutmeldingen over ontbrekende
# tabellen die niets met de wijziging te maken hebben. De scheiding hoort dus in
# de naam te zitten en niet in een afspraak over wie wanneer draait.
#
# Afgeleid uit de MAPNAAM, niet uit de tak: een tak wisselt, een worktree niet.
slug="$(basename "$ROOT" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | sed 's/_\+/_/g; s/^_//; s/_$//')"
DB_NAAM="${TEST_DB_NAME:-raaktest_${slug}}"

# ── Vangrail ─────────────────────────────────────────────────────────────────
# Staat vóór élke docker-aanroep, zodat een weigering nooit iets aanraakt. De
# suite is destructief en `DATABASE_URL` en `TEST_DATABASE_URL` schelen één woord;
# leest de doelnaam niet als testdatabank, dan stoppen we hier.
if [ -n "${TEST_DATABASE_URL:-}" ]; then
  # Laatste padsegment van de URL, zonder eventuele ?querystring.
  DB_NAAM="${TEST_DATABASE_URL##*/}"
  DB_NAAM="${DB_NAAM%%\?*}"
fi

case "$DB_NAAM" in
  raaktest|raaktest_*) ;;
  *)
    echo "test-local.sh: GEWEIGERD — '$DB_NAAM' leest niet als een testdatabank." >&2
    echo "  De suite dropt en hermaakt het schema van haar doel. Een naam die niet" >&2
    echo "  met 'raaktest' begint kan een echte databank zijn, dus we raken niets aan." >&2
    echo "  Bedoelde je een eigen naam, zet die dan via TEST_DB_NAME=raaktest_<iets>." >&2
    exit 2
    ;;
esac

URL="${TEST_DATABASE_URL:-postgresql+psycopg2://postgres:postgres@db:5432/${DB_NAAM}}"

# ── Dev-stack en hulpcontainer ───────────────────────────────────────────────
# De databank draait in het gedeelde dev-project; de suite draait in een eigen,
# langlevende container per worktree. Langlevend omdat een wegwerpcontainer bij
# élke run opnieuw pytest en mypy zou installeren — dat is precies de lus van
# seconden die dit script moet opleveren.
NAAM="raaktest-${slug}"
NETWERK="dev_internal"

"${COMPOSE[@]}" up -d db >/dev/null

if [ "${VERS:-}" = "1" ]; then
  docker rm -f "$NAAM" >/dev/null 2>&1 || true
fi

# Zelf bouwen uit backend/Dockerfile in plaats van de imagenaam bij compose op te
# vragen: `docker compose config --images <service>` geeft ook de images van de
# afhankelijkheden terug, in wisselende volgorde — de eerste run pikte daardoor
# postgres:16 op en struikelde over een ontbrekende `pip`. Dit is dezelfde
# Dockerfile en dus dezelfde runtime (python:3.12-slim), zonder die gok.
IMAGE="raaktest-backend:${slug}"
docker build -q -t "$IMAGE" "$ROOT/backend" >/dev/null

if ! docker inspect -f '{{.State.Running}}' "$NAAM" >/dev/null 2>&1; then
  docker rm -f "$NAAM" >/dev/null 2>&1 || true
  echo "→ hulpcontainer $NAAM opbouwen (eenmalig)…"
  # De broncode komt van de host (bind mount), niet uit het image: anders zou elke
  # wijziging een rebuild vragen en test je niet wat er in je werkmap staat.
  #
  # De HELE repo wordt gemount, niet alleen backend/: er zijn tests die naar
  # bestanden buiten backend/ kijken (de vangrail van dit script zelf, #719). Met
  # /app als repowortel en /app/backend als werkmap ligt de indeling in de container
  # gelijk aan die in de checkout, dus `parents[2]` klopt hier én in CI.
  docker run -d --name "$NAAM" --network "$NETWERK" \
    -v "$ROOT:/app" -w /app/backend \
    -e APP_ENV=dev -e JOBS_ENABLED=false \
    "$IMAGE" sleep infinity >/dev/null
  docker exec "$NAAM" pip install -q -r requirements-dev.txt
fi

# ── Databank aanmaken als ze nog niet bestaat ────────────────────────────────
# Foutloos herhaalbaar: bestaat ze al, dan is er niets te doen.
"${COMPOSE[@]}" exec -T db sh -c \
  "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tc \"SELECT 1 FROM pg_database WHERE datname='${DB_NAAM}'\" \
   | grep -q 1 || psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c 'CREATE DATABASE ${DB_NAAM}'" >/dev/null

# ── De rest van de poort ─────────────────────────────────────────────────────
if [ "${SNEL:-}" != "1" ]; then
  echo "→ mypy"
  # --cache-dir buiten /app: de werkmap is een bind mount en de container draait als
  # een andere gebruiker, dus mypy kan er zijn cache niet aanmaken. Zonder dit stopt
  # hij met een INTERNAL ERROR en een PermissionError die eruitziet als een bug in
  # mypy zelf.
  docker exec "$NAAM" python -m mypy --cache-dir=/tmp/mypy_cache

  echo "→ app.css"
  # Zelfde controle als de css-job: herbouwen en eisen dat er niets wijzigt. Draait
  # op de host, want daar staat de Tailwind-binary (scripts/build-css.sh, .cache/).
  # Wijkt het af, dan is het bestand nú herbouwd — je hoeft het alleen te committen.
  "$ROOT/scripts/build-css.sh" >/dev/null
  if ! git -C "$ROOT" diff --quiet -- backend/app/static/app.css; then
    echo "test-local.sh: app.css liep niet gelijk met de templates." >&2
    echo "  Het bestand is zojuist herbouwd; commit backend/app/static/app.css mee." >&2
    git -C "$ROOT" diff --stat -- backend/app/static/app.css >&2
    exit 1
  fi
fi

echo "→ pytest tegen ${DB_NAAM}"
# cache_dir buiten /app: die map is een bind mount naar de werkmap en de container
# draait als een andere gebruiker, dus pytest kreeg daar geen schrijfrechten (en het
# hoort er ook niet thuis).
exec docker exec -e TEST_DATABASE_URL="$URL" "$NAAM" \
  python -m pytest -o cache_dir=/tmp/pytest_cache "$@"
