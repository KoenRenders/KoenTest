#!/usr/bin/env bash
# Draait de pytest-suite lokaal tegen de dev-stack (#719).
#
# Waarom Docker en geen venv: de backend draait op python:3.12-slim en postgres:16,
# deze machine heeft Python 3.13 en PostgreSQL 17. Een venv zou de suite draaien op
# een runtime die nergens bestaat — dan betekent een groene lokale run iets anders
# dan een groene CI-run, en dat is erger dan geen lokale run.
#
# Draait dezelfde poort als CI: eerst mypy, dan de css-controle, dan pytest (#739).
# Since CR-29 also what the `lint` job runs — `ruff format --check` and `ruff check`,
# before mypy — and pytest in four processes as CI does, each on its own database
# (`<name>_gw0` … `_gw3`, made by the suite itself: tests/_worker_db.py).
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
#   scripts/test-local.sh                          # de hele poort, pytest in vier processen
#   scripts/test-local.sh tests/test_iets.py       # één bestand (nog steeds mét poort),
#                                                  # in één proces: een selectie splits je niet
#   SNEL=1 scripts/test-local.sh -k naam           # alleen pytest, tijdens het bouwen
#
# Omgevingsvariabelen:
#   SNEL=1              sla ruff, mypy en de css-controle over, en draai in één proces
#                       (de STANDAARD is de volle poort)
#   TEST_DB_NAME        overschrijft de afgeleide databanknaam
#   TEST_DATABASE_URL   overschrijft de hele URL (wordt óók door de vangrail getoetst)
#   VERS                zet dit op 1 om de hulpcontainer opnieuw op te bouwen
#   EXISTING_DB_URL, EXISTING_DB_SOCKET_DIR
#                       a database server that already runs, in place of the dev
#                       stack's (#1891) — see scripts/local-db-lib.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/docker-compose.dev.yml")
# shellcheck source=scripts/local-db-lib.sh
. "$ROOT/scripts/local-db-lib.sh"

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
  # Parsed, not cut (#1891): in a URL over a unix socket the last "/" stands
  # inside ?host=, so "everything after the last /" read the wrong name.
  if ! db_url_parse "$TEST_DATABASE_URL"; then
    echo "test-local.sh: GEWEIGERD — TEST_DATABASE_URL leest niet als een databank-URL." >&2
    exit 2
  fi
  DB_NAAM="$DB_URL_NAME"
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

# #1891: a database server that already runs, in place of the dev stack's — also
# decided before any docker call. What the switch is: scripts/local-db-lib.sh.
existing_db test-local.sh "$DB_NAAM"

# ── Dev-stack en hulpcontainer ───────────────────────────────────────────────
# De databank draait in het gedeelde dev-project; de suite draait in een eigen,
# langlevende container per worktree. Langlevend omdat een wegwerpcontainer bij
# élke run opnieuw pytest en mypy zou installeren — dat is precies de lus van
# seconden die dit script moet opleveren.
NAAM="raaktest-${slug}"
NETWERK="dev_internal"

# `--no-recreate`: the dev project (`name: dev`) is shared by every worktree, and
# each passes its own path to the compose file. Without the flag compose sees a
# changed configuration and REPLACES the db container on every run from another
# worktree — killing the test run that worktree had going. With it, compose only
# starts the database when it is not running, and leaves a running one alone.
if [ -z "${EXISTING_DB_URL:-}" ]; then
  "${COMPOSE[@]}" up -d --no-recreate db >/dev/null

  # The credentials come from the running db container, not from this file: the
  # dev database carries whatever password its volume was initialised with, and a
  # hardcoded `postgres:postgres` fails the moment that is anything else (CLAUDE.md:
  # never hardcode them). Read after `up`, so the container exists.
  DB_USER="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_USER)"
  DB_PASS="$("${COMPOSE[@]}" exec -T db printenv POSTGRES_PASSWORD)"
  URL="${TEST_DATABASE_URL:-postgresql+psycopg2://${DB_USER}:${DB_PASS}@db:5432/${DB_NAAM}}"
  RUN_ARGS=(--network "$NETWERK")
fi

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
  docker run -d --name "$NAAM" "${RUN_ARGS[@]}" \
    -v "$ROOT:/app" -w /app/backend \
    -e APP_ENV=dev -e JOBS_ENABLED=false \
    "$IMAGE" sleep infinity >/dev/null
fi

# The helper container lives long, so its packages must follow the requirement
# files: a container built before CR-29 has no pytest-xdist and would stop on
# `-n`. Installed when the files changed since the last install, not on every run.
SOM="$(cat "$ROOT/backend/requirements.txt" "$ROOT/backend/requirements-dev.txt" | sha256sum | cut -c1-16)"
docker exec "$NAAM" sh -c "[ \"\$(cat /tmp/requirements.som 2>/dev/null)\" = '$SOM' ] \
  || { pip install -q -r requirements-dev.txt && echo '$SOM' > /tmp/requirements.som; }"

# ── Databank aanmaken als ze nog niet bestaat ────────────────────────────────
# Foutloos herhaalbaar: bestaat ze al, dan is er niets te doen.
if [ -n "${EXISTING_DB_URL:-}" ]; then
  # No db container to ask: the helper container makes it, over the given URL.
  docker exec -e ADMIN_DATABASE_URL="$EXISTING_DB_URL" "$NAAM" \
    python -m tests._local_db create "$DB_NAAM"
else
  "${COMPOSE[@]}" exec -T db sh -c \
    "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tc \"SELECT 1 FROM pg_database WHERE datname='${DB_NAAM}'\" \
   | grep -q 1 || psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c 'CREATE DATABASE ${DB_NAAM}'" >/dev/null
fi

# ── De rest van de poort ─────────────────────────────────────────────────────
if [ "${SNEL:-}" != "1" ]; then
  echo "→ ruff"
  # What CI's `lint` job blocks on (CR-29 D4), with the ruff of requirements-dev.txt.
  # --no-cache: the work folder is a bind mount the container cannot write its cache to.
  # `python -m`, like mypy and pytest below (#1891): pip installs for the image's
  # user outside the PATH, so in a helper container built fresh the bare `ruff`
  # was not found and the gate stopped on its first line.
  docker exec "$NAAM" python -m ruff format --check --no-cache .
  docker exec "$NAAM" python -m ruff check --no-cache .

  echo "→ mypy"
  # --cache-dir buiten /app: de werkmap is een bind mount en de container draait als
  # een andere gebruiker, dus mypy kan er zijn cache niet aanmaken. Zonder dit stopt
  # hij met een INTERNAL ERROR en een PermissionError die eruitziet als een bug in
  # mypy zelf.
  docker exec "$NAAM" python -m mypy --cache-dir=/tmp/mypy_cache

  echo "→ app.css"
  # Zelfde controle als de css-job, maar op de juiste vergelijking. CI draait in een
  # verse checkout en kan dus `git diff` gebruiken: daar betekent élk verschil "niet
  # herbouwd". Lokaal niet — daar staat een terecht herbouwde maar nog niet
  # gecommitte app.css óók als verschil in git, en dan blijft deze controle rood tot
  # je commit. Wat we hier willen weten is of de HERBOUW iets verandert.
  CSS="$ROOT/backend/app/static/app.css"
  VOOR="$(mktemp)"
  cp "$CSS" "$VOOR"
  "$ROOT/scripts/build-css.sh" >/dev/null
  if ! cmp -s "$VOOR" "$CSS"; then
    rm -f "$VOOR"
    echo "test-local.sh: app.css liep niet gelijk met de templates." >&2
    echo "  Het bestand is zojuist herbouwd; commit backend/app/static/app.css mee." >&2
    exit 1
  fi
  rm -f "$VOOR"
fi

# CR-29: the full run uses four processes, as CI does; a partial run — SNEL=1 or
# any pytest argument — stays in one. The next line is the whole of that choice (Q2).
WORKERS=(-n 4 --dist loadgroup)
if [ "${SNEL:-}" = "1" ] || [ "$#" -gt 0 ]; then WORKERS=(); fi

echo "→ pytest tegen ${DB_NAAM}"
# cache_dir buiten /app: die map is een bind mount naar de werkmap en de container
# draait als een andere gebruiker, dus pytest kreeg daar geen schrijfrechten (en het
# hoort er ook niet thuis).
exec docker exec -e TEST_DATABASE_URL="$URL" "$NAAM" \
  python -m pytest -o cache_dir=/tmp/pytest_cache "${WORKERS[@]}" "$@"
