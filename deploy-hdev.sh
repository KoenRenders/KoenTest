#!/usr/bin/env bash
set -euxo pipefail

# Sync met master — lokale wijzigingen worden weggegooid.
git fetch origin master
git reset --hard origin/master

# Versie + commit voor de startup-log (#151); als build-args naar de backend-image.
export APP_VERSION="$(git describe --tags --always 2>/dev/null || echo onbekend)"
export GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo onbekend)"

# Bouw en start HDEV.
docker compose -f docker-compose.hdev.yml --env-file .env.hdev up --build -d

# Post-deploy rooktest (alleen-lezen; maakt geen data aan).
BASE="${SMOKE_BASE:-http://localhost:8081}" ./tests/run-all.sh
