#!/usr/bin/env bash
set -x

git pull

docker compose -f docker-compose.caddy.yml up -d
