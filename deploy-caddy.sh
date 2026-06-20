#!/usr/bin/env bash
set -x

git pull

docker compose -f docker-compose.caddy.yml up -d

# `up -d` herstart de container NIET bij een loutere wijziging aan de bind-mounted
# Caddyfile.shared — herlaad daarom expliciet, zodat shared-config (zoals de
# compressie van #303) meteen actief wordt op alle domeinen (#312).
docker compose -f docker-compose.caddy.yml exec -T caddy caddy reload --config /etc/caddy/Caddyfile
