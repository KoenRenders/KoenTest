#!/usr/bin/env bash
set -x

git pull

sudo docker compose -f docker-compose.dev.yml --env-file .env.dev up --build -d
