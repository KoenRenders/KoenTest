#!/usr/bin/env bash
set -x

git pull

docker compose -f docker-compose.uat.yml --env-file .env.uat up --build -d

# Post-deploy rooktest (alleen-lezen; maakt geen data aan). Doel-URL = de
# publieke origin uit .env.uat (Caddy proxiet /api/* naar de backend).
SMOKE_BASE="${SMOKE_BASE:-$(sed -nE "s/^FRONTEND_URL=[\"']?([^\"']*)[\"']?.*/\1/p" .env.uat | head -1)}"
if [ -n "$SMOKE_BASE" ]; then
  BASE="$SMOKE_BASE" ./tests/run-all.sh || true
else
  echo "FRONTEND_URL onbekend in .env.uat — rooktest overgeslagen"
fi
