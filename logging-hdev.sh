#!/usr/bin/env bash
set -euo pipefail

# Diagnostiek na een HDEV-deploy — bundelt in ÉÉN bestand wat je anders los
# uitvoert: alembic heads/current (migratiestatus) + de backend-logs. Draait OP de
# server, in de repo-checkout. Bevat bewust geen secrets/IP's (dit repo is publiek);
# het kopiëren naar je laptop doe je met een losse scp (zie de slotregels).
#
# Gebruik:  ./logging-hdev.sh
# Output:   /tmp/hdev-backend.log  (override met LOG_OUT=..., aantal regels met LOG_TAIL=...)

ENV=hdev
COMPOSE="docker-compose.hdev.yml"
ENVFILE=".env.hdev"
OUT="${LOG_OUT:-/tmp/${ENV}-backend.log}"
TAIL="${LOG_TAIL:-100}"

dc() { docker compose -f "$COMPOSE" --env-file "$ENVFILE" "$@"; }

# Output toont op je scherm ÉN gaat naar het bestand (tee), zodat je meteen ziet
# of er iets misloopt en zelf beslist of je het bestand naar Claude doorstuurt.
{
  echo "=== Raak Millegem — ${ENV} diagnostiek ==="
  echo "Datum:   $(date -Is)"
  echo "Commit:  $(git rev-parse --short HEAD 2>/dev/null || echo onbekend) ($(git describe --tags --always 2>/dev/null || echo onbekend))"
  echo
  echo "--- alembic heads (moet er PRECIES ÉÉN zijn) ---"
  dc exec -T backend alembic heads 2>&1 || echo "(alembic heads faalde)"
  echo
  echo "--- alembic current (moet gelijk zijn aan de head hierboven) ---"
  dc exec -T backend alembic current 2>&1 || echo "(alembic current faalde)"
  echo
  echo "--- backend logs (laatste ${TAIL}) ---"
  dc logs backend --tail="${TAIL}" 2>&1 || echo "(backend logs faalden)"
} 2>&1 | tee "$OUT"

echo
echo "Diagnostiek weggeschreven naar: $OUT"
echo "Kopieer naar je laptop met (pas sleutel/host/pad aan):"
echo "  scp -i ~/.ssh/<jouw-sleutel> <user>@<server>:$OUT ~/Nextcloud/Temp/${ENV}-backend.log"
