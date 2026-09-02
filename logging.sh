#!/usr/bin/env bash
# Diagnostiek na een deploy — bundelt in ÉÉN bestand wat je anders los uitvoert,
# zodat je in één oogopslag ziet of er iets misloopt. Draait OP de server, in de
# repo-checkout. Bevat bewust geen secrets/IP's (deze repo is publiek).
#
#   ./logging.sh hdev | uat | prod
#
# Output:  /tmp/<env>-diagnostics.log   (override met LOG_OUT=…, regels met LOG_TAIL=…)
# Ophalen naar je laptop: zie het spiekbriefje (scp) of `raakctl fetch <env>`.
#
# Vervangt logging-hdev.sh / logging-uat.sh / logging-prod.sh, die regel voor
# regel identiek waren op drie variabelen en de herkomst van de caddy-logs na.
set -euo pipefail

cd "$(dirname "$0")"

ENV="${1:?Geef de omgeving op: hdev | uat | prod (bv. ./logging.sh uat)}"

# CADDY  own    = eigen Caddy in de stack (HDEV)
#        shared = de gedeelde proxy (apart compose-project, name: caddy). Die
#                 bedient UAT én PROD, dus de logs bevatten verkeer van beide.
case "$ENV" in
  hdev) COMPOSE="docker-compose.hdev.yml"; ENVFILE=".env.hdev"; CADDY="own" ;;
  uat)  COMPOSE="docker-compose.uat.yml";  ENVFILE=".env.uat";  CADDY="shared" ;;
  prod) COMPOSE="docker-compose.prod.yml"; ENVFILE=".env.prod"; CADDY="shared" ;;
  *)    echo "FOUT: onbekende omgeving '$ENV' — kies hdev, uat of prod." >&2; exit 1 ;;
esac

OUT="${LOG_OUT:-/tmp/${ENV}-diagnostics.log}"
TAIL="${LOG_TAIL:-100}"

dc() { docker compose -f "$COMPOSE" --env-file "$ENVFILE" "$@"; }
caddy_logs() {
  if [ "$CADDY" = "own" ]; then
    dc logs caddy --tail="${TAIL}" 2>&1 || echo "(caddy logs faalden)"
  else
    docker compose -f docker-compose.caddy.yml logs caddy --tail="${TAIL}" 2>&1 \
      || echo "(caddy logs faalden — draait de gedeelde Caddy?)"
  fi
}

# Output toont op je scherm ÉN gaat naar het bestand (tee). We APPENDEN (-a): de
# deploy (deploy.sh) reset de logfile bij start; dit voegt de post-deploy-
# diagnostiek toe, zodat één bestand de volledige deploy + diagnostiek bevat (#291).
{
  echo "=== Raak Millegem — ${ENV} diagnostiek ==="
  echo "Datum:   $(date -Is)"
  echo "Commit:  $(git rev-parse --short HEAD 2>/dev/null || echo onbekend) ($(git describe --tags --always 2>/dev/null || echo onbekend))"
  echo

  echo "--- containerstatus (alles 'running'/'healthy'? geen 'restarting'/'exited'?) ---"
  dc ps 2>&1 || echo "(docker compose ps faalde)"
  echo

  echo "--- alembic heads (moet er PRECIES ÉÉN zijn) ---"
  dc exec -T backend alembic heads 2>&1 || echo "(alembic heads faalde)"
  echo

  echo "--- alembic current (moet gelijk zijn aan de head hierboven) ---"
  dc exec -T backend alembic current 2>&1 || echo "(alembic current faalde)"
  echo

  echo "--- schijfruimte (volle disk geeft rare deploy-fouten) ---"
  df -h / 2>&1 || echo "(df faalde)"
  echo

  echo "--- snelle foutfilter: ERROR/Traceback/Exception in de laatste ${TAIL} backend-regels ---"
  if dc logs backend --tail="${TAIL}" 2>&1 | grep -iE 'error|traceback|exception' ; then
    : # treffers hierboven getoond
  else
    echo "(geen ERROR/Traceback/Exception in de laatste ${TAIL} regels)"
  fi
  echo

  echo "--- backend logs (laatste ${TAIL}) ---"
  dc logs backend --tail="${TAIL}" 2>&1 || echo "(backend logs faalden)"
  echo

  if [ "$CADDY" = "shared" ]; then
    echo "--- caddy logs (GEDEELDE Caddy — UAT én PROD, laatste ${TAIL}) ---"
  else
    echo "--- caddy logs (eigen Caddy, laatste ${TAIL}) ---"
  fi
  caddy_logs
} 2>&1 | tee -a "$OUT"

echo
echo "Diagnostiek toegevoegd aan: $OUT"
