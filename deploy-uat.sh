#!/usr/bin/env bash
set -x

git pull

docker compose -f docker-compose.uat.yml --env-file .env.uat up --build -d
