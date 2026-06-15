#!/usr/bin/env bash
# Deployt een EXACTE release-tag naar PROD (geen bewegende branch).
# Gebruik: ./deploy-prod.sh v1.2.1
#
# UAT/PROD draaien bewust op een vastgepinde tag — we gaan er NIET van uit dat
# master gelijk is aan de laatste release. master kan al verder staan.
set -euxo pipefail

REF="${1:?Geef de te deployen release-tag op, bv: ./deploy-prod.sh v1.2.1}"

# Haal de tags op en check de exacte commit uit (detached HEAD is hier gewenst).
git fetch --tags --prune origin
git checkout --detach "$REF"

# Robuustheid (#162): na de checkout draait mogelijk nog de vorige scriptversie.
# Re-exec één keer de nu-uitgecheckte versie zodat de rest (versie-export, build,
# smoke) uit de juiste scriptinhoud komt. De guard voorkomt een oneindige lus.
if [ -z "${DEPLOY_REEXEC:-}" ]; then
  export DEPLOY_REEXEC=1
  exec "$0" "$@"
fi

# Versie + commit voor de startup-log (#151); als build-args naar de backend-image.
export APP_VERSION="$(git describe --tags --always 2>/dev/null || echo onbekend)"
export GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo onbekend)"

docker compose -f docker-compose.prod.yml --env-file .env.prod up --build -d

# Post-deploy rooktest — STRIKT ALLEEN-LEZEN, maakt geen data aan (veilig op PROD).
# Doel-URL = de publieke origin uit .env.prod (Caddy proxiet /api/* naar de backend).
SMOKE_BASE="${SMOKE_BASE:-$(sed -nE "s/^FRONTEND_URL=[\"']?([^\"']*)[\"']?.*/\1/p" .env.prod | head -1)}"
if [ -n "$SMOKE_BASE" ]; then
  BASE="$SMOKE_BASE" ./tests/run-all.sh || true
else
  echo "FRONTEND_URL onbekend in .env.prod — rooktest overgeslagen"
fi
