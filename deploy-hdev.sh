#!/usr/bin/env bash
set -euxo pipefail

# Sync met master — lokale wijzigingen worden weggegooid.
git fetch origin master
git reset --hard origin/master

# Bouw en start HDEV.
docker compose -f docker-compose.hdev.yml --env-file .env.hdev up --build -d

# Post-deploy rooktest (alleen-lezen; maakt geen data aan).
BASE="${SMOKE_BASE:-http://localhost:8081}" ./tests/run-all.sh
