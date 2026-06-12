#!/usr/bin/env bash
set -x

git pull

sudo docker compose -f docker-compose.dev.yml --env-file .env.dev up --build -d

# Post-deploy rooktest (alleen-lezen; maakt geen data aan).
BASE="${SMOKE_BASE:-http://localhost}" ./tests/run-all.sh
