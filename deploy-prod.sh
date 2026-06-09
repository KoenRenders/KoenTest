#!/usr/bin/env bash
set -x

git pull

docker compose -f docker-compose.prod.yml --env-file .env.prod up --build -d
