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

# Versie + commit voor de startup-log (#151); als build-args naar de backend-image.
export APP_VERSION="$(git describe --tags --always 2>/dev/null || echo onbekend)"
export GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo onbekend)"

# Bouw en start HDEV.
docker compose -f docker-compose.hdev.yml --env-file .env.hdev up --build -d

# Post-deploy rooktest (alleen-lezen; maakt geen data aan).
BASE="${SMOKE_BASE:-http://localhost:8081}" ./tests/run-all.sh
