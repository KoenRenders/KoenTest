#!/usr/bin/env bash
set -euxo pipefail

# Sync met master — lokale wijzigingen worden weggegooid. --tags zodat
# `git describe` een zinnige release-tag toont in de versie-log (#151).
git fetch --tags --force origin master
git reset --hard origin/master

# Robuustheid (#162): na de reset draait mogelijk nog de vorige scriptversie.
# Re-exec één keer de nu-uitgecheckte versie zodat de rest (versie-export, build,
# smoke) uit de juiste scriptinhoud komt. De guard voorkomt een oneindige lus.
if [ -z "${DEPLOY_REEXEC:-}" ]; then
  export DEPLOY_REEXEC=1
  exec "$0" "$@"
fi

# Vang vanaf hier alle output (build + smoke) op in het diagnostiek-bestand én
# toon ze op je scherm (#291). Dit is meteen de RESET van de logfile: elke deploy
# begint met een schoon bestand; logging-hdev.sh voegt er daarna aan toe (append).
LOG_OUT="${LOG_OUT:-/tmp/hdev-backend.log}"
exec > >(tee "$LOG_OUT") 2>&1

# Versie + commit voor de startup-log (#151); als build-args naar de backend-image.
export APP_VERSION="$(git describe --tags --always 2>/dev/null || echo onbekend)"
export GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo onbekend)"

# Bouw en start HDEV.
docker compose -f docker-compose.hdev.yml --env-file .env.hdev up --build -d

# Herlaad de eigen hdev-Caddy zodat wijzigingen in Caddyfile.hdev (bind-mount)
# meteen actief zijn — `up -d` herstart de caddy-container niet bij een loutere
# bestandswijziging. (#169)
docker compose -f docker-compose.hdev.yml --env-file .env.hdev exec -T caddy caddy reload --config /etc/caddy/Caddyfile

# Post-deploy rooktest (alleen-lezen; maakt geen data aan).
BASE="${SMOKE_BASE:-http://localhost:8081}" ./tests/run-all.sh
