#!/usr/bin/env bash
set -euo pipefail

# Diagnostiek na een PROD-deploy — bundelt in ÉÉN bestand wat je anders los
# uitvoert, zodat je in één oogopslag ziet of er iets misloopt en zelf beslist of
# je het bestand naar Claude doorstuurt. Draait OP de server, in de repo-checkout.
# Bevat bewust geen secrets/IP's (dit repo is publiek); het kopiëren naar je laptop
# doe je met een losse scp (zie de slotregels).
#
# Caddy draait bij UAT/PROD als een APART, gedeeld compose-project
# (docker-compose.caddy.yml, name: caddy) — niet in de env-stack. De caddy-logs
# komen daarom uit dat project en bevatten verkeer van álle omgevingen (uat+prod).
#
# Gebruik:  ./logging-prod.sh
# Output:   /tmp/prod-diagnostics.log  (override met LOG_OUT=..., aantal regels met LOG_TAIL=...)

ENV=prod
COMPOSE="docker-compose.prod.yml"
ENVFILE=".env.prod"
OUT="${LOG_OUT:-/tmp/${ENV}-diagnostics.log}"
TAIL="${LOG_TAIL:-100}"

dc() { docker compose -f "$COMPOSE" --env-file "$ENVFILE" "$@"; }
caddy_dc() { docker compose -f docker-compose.caddy.yml "$@"; }

# Output toont op je scherm ÉN gaat naar het bestand (tee). We APPENDEN (-a): de
# deploy (deploy-prod.sh) reset de logfile bij start; dit voegt de post-deploy-
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

  echo "--- frontend logs (laatste ${TAIL}) ---"
  dc logs frontend --tail="${TAIL}" 2>&1 || echo "(frontend logs faalden)"
  echo

  echo "--- caddy logs (GEDEELDE Caddy — alle omgevingen, laatste ${TAIL}) ---"
  caddy_dc logs caddy --tail="${TAIL}" 2>&1 || echo "(caddy logs faalden — draait de gedeelde Caddy?)"
} 2>&1 | tee -a "$OUT"

echo
echo "Diagnostiek toegevoegd aan: $OUT"
echo "Kopieer naar je laptop met (pas sleutel/host/pad aan):"
echo "  scp -i ~/.ssh/<jouw-sleutel> <user>@<server>:$OUT ~/Nextcloud/Temp/${ENV}-diagnostics.log"
