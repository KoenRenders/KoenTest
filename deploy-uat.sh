#!/usr/bin/env bash
# Deployt een EXACTE release-tag naar UAT (geen bewegende branch).
# Gebruik: ./deploy-uat.sh v1.2.1
#
# UAT/PROD draaien bewust op een vastgepinde tag — we gaan er NIET van uit dat
# master gelijk is aan de laatste release. master kan al verder staan.
set -euxo pipefail

REF="${1:?Geef de te deployen release-tag op, bv: ./deploy-uat.sh v1.2.1}"

# Haal de tags op en check de exacte commit uit (detached HEAD is hier gewenst).
git fetch --tags --prune origin
git checkout --detach "$REF"

docker compose -f docker-compose.uat.yml --env-file .env.uat up --build -d

# Post-deploy rooktest (alleen-lezen; maakt geen data aan). Doel-URL = de
# publieke origin uit .env.uat (Caddy proxiet /api/* naar de backend).
SMOKE_BASE="${SMOKE_BASE:-$(sed -nE "s/^FRONTEND_URL=[\"']?([^\"']*)[\"']?.*/\1/p" .env.uat | head -1)}"
if [ -n "$SMOKE_BASE" ]; then
  BASE="$SMOKE_BASE" ./tests/run-all.sh || true
else
  echo "FRONTEND_URL onbekend in .env.uat — rooktest overgeslagen"
fi
