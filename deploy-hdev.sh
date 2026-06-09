#!/usr/bin/env bash
set -x

git pull

docker compose -f docker-compose.hdev.yml --env-file .env.hdev up --build -d
