#!/usr/bin/env bash
# Past de GEDEELDE Caddy-config (caddy/Caddyfile.shared) toe en herstart de
# gedeelde Caddy zodat de wijziging gegarandeerd én blijvend actief is.
# Draaien uit de caddy/-checkout (bv. /opt/raakmillegem/caddy):  ./deploy-caddy.sh
#
# LET OP: deze Caddy bedient UAT **en** PROD. Een fout hier legt productie plat.
# Daarom drie vangnetten, in deze volgorde:
#   1) `caddy validate` op de nieuwe config, VOOR de draaiende proxy geraakt wordt;
#   2) een rooktest tegen PROD na de recreate;
#   3) automatische, eenmalige rollback naar de vorige commit als die rooktest faalt.
#
# Achtergrond (#312/#314) — twee valkuilen die we hier hard dichttimmeren:
#   1) `caddy reload` (admin-API, in-memory) is onbetrouwbaar en overleeft geen
#      herstart. We doen `up -d --force-recreate`, dat de config vers van schijf
#      laadt, zodat compressie (#303) elke herstart overleeft.
#   2) Een caddy-map op een DETACHED HEAD laat `git pull` stilvallen, waardoor de
#      config nooit bijwerkt. We forceren de map onvoorwaardelijk op master HEAD.
set -euxo pipefail

cd "$(dirname "$0")"

COMPOSE="docker-compose.caddy.yml"

# Rollback-doel: onthoud wat er NU draait, vóór de reset. Eén keer gezet; overleeft
# de re-exec en de eventuele rollback-exec via export.
export CADDY_PREV_REF="${CADDY_PREV_REF:-$(git rev-parse HEAD 2>/dev/null || echo '')}"

# Zet de map onvoorwaardelijk op de laatste master (werkt ook vanaf een detached
# HEAD of een vervuilde werkmap). Bij een rollback checken we een exacte commit uit.
if [ -n "${CADDY_ROLLBACK:-}" ]; then
  git checkout --detach "$CADDY_PREV_REF"
else
  git fetch origin
  git reset --hard origin/master
  git checkout -B master origin/master
fi

# Robuustheid (#162-patroon, zoals deploy-uat.sh): na de checkout staat er mogelijk
# een nieuwere versie van dit script op schijf dan degene die nu draait. Re-exec
# één keer, zodat de validatie en de rollback hieronder uit de juiste scriptinhoud
# komen. De guard voorkomt een oneindige lus.
if [ -z "${CADDY_REEXEC:-}" ]; then
  export CADDY_REEXEC=1
  exec "$0" "$@"
fi

# Veiligheidscheck: de compressie (#303) hoort in de gedeelde config te staan.
# Zo niet, dan klopt de checkout niet — stoppen i.p.v. een kapotte config laden.
if ! grep -q 'encode' caddy/Caddyfile.shared; then
  echo "FOUT: 'encode' ontbreekt in caddy/Caddyfile.shared — config NIET toegepast." >&2
  exit 1
fi

# VANGNET 1 — valideer de config in een wegwerpcontainer, VOOR we de draaiende
# proxy aanraken. `run --rm --no-deps` publiceert geen poorten en start niets
# anders op; de env_file (.env.caddy) wordt wel geladen, zodat de {$DOMAIN}-
# placeholders ingevuld worden zoals bij een echte start. Een syntaxfout stopt de
# deploy hier, met de oude proxy nog gewoon in de lucht.
docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint caddy caddy \
  validate --config /etc/caddy/Caddyfile --adapter caddyfile

# Verse container = config vers van schijf (overleeft herstarts), i.p.v. de
# onbetrouwbare in-memory `caddy reload`.
docker compose -f "$COMPOSE" up -d --force-recreate caddy

# VANGNET 2 — rooktest tegen PROD. Het domein komt uit .env.caddy (niet in git).
# PROD is de gate: die mag niet stuk. UAT testen we ook, maar enkel als waarschuwing
# — ligt de UAT-stack om een andere reden plat, dan is dat geen reden om een
# geslaagde Caddy-config terug te draaien.
PROD_DOMAIN="$(sed -nE 's/^PROD_DOMAIN=["'"'"']?([^"'"'"']*)["'"'"']?.*/\1/p' .env.caddy | head -1)"
UAT_DOMAIN="$(sed -nE 's/^UAT_DOMAIN=["'"'"']?([^"'"'"']*)["'"'"']?.*/\1/p' .env.caddy | head -1)"

if [ -n "$PROD_DOMAIN" ]; then
  if ! BASE="https://$PROD_DOMAIN" ./tests/run-all.sh; then
    echo "!! ROOKTEST FAALDE op PROD na de Caddy-wijziging."
    # VANGNET 3 — eenmalige automatische rollback naar de vorige commit.
    CUR="$(git rev-parse HEAD 2>/dev/null || echo '')"
    if [ -z "${CADDY_ROLLBACK:-}" ] && [ -n "$CADDY_PREV_REF" ] && [ "$CADDY_PREV_REF" != "$CUR" ]; then
      echo ">>> Automatische rollback naar $CADDY_PREV_REF (eenmalig)."
      CADDY_ROLLBACK=1 CADDY_REEXEC= exec "$0" "$@"
    fi
    echo "!! Geen (verdere) automatische rollback mogelijk — handmatig ingrijpen." >&2
    echo "!! Vorige commit was: ${CADDY_PREV_REF:-onbekend}" >&2
    exit 1
  fi
  echo "Rooktest OK op PROD."
else
  echo "PROD_DOMAIN onbekend in .env.caddy — rooktest tegen PROD overgeslagen"
fi

if [ -n "$UAT_DOMAIN" ]; then
  BASE="https://$UAT_DOMAIN" ./tests/run-all.sh \
    || echo "LET OP: rooktest tegen UAT faalde. Geen rollback (PROD is de gate) — controleer de UAT-stack."
fi

if [ -n "${CADDY_ROLLBACK:-}" ]; then
  echo "Caddy TERUGGEROLD naar $CADDY_PREV_REF — de nieuwe config is NIET actief." >&2
  exit 1
fi

echo "Gedeelde Caddy hercreëerd op master ($(git rev-parse --short HEAD)) — dekt alle domeinen."
