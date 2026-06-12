#!/usr/bin/env bash
set -x

git pull

docker compose -f docker-compose.prod.yml --env-file .env.prod up --build -d

# Post-deploy rooktest — STRIKT ALLEEN-LEZEN, maakt geen data aan (veilig op PROD).
# Doel-URL = de publieke origin uit .env.prod (Caddy proxiet /api/* naar de backend).
SMOKE_BASE="${SMOKE_BASE:-$(sed -nE "s/^FRONTEND_URL=[\"']?([^\"']*)[\"']?.*/\1/p" .env.prod | head -1)}"
if [ -n "$SMOKE_BASE" ]; then
  BASE="$SMOKE_BASE" ./tests/run-all.sh || true
else
  echo "FRONTEND_URL onbekend in .env.prod — rooktest overgeslagen"
fi
