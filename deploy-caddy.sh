#!/usr/bin/env bash
# Past de GEDEELDE Caddy-config (caddy/Caddyfile.shared) toe en herstart de
# gedeelde Caddy zodat de wijziging gegarandeerd én blijvend actief is.
# Draaien uit de caddy/-checkout (bv. /opt/raakmillegem/caddy):
#
#   ./deploy-caddy.sh              # config van de tag die PROD nu draait
#   ./deploy-caddy.sh v1.15.0      # config van een expliciete tag
#   ./deploy-caddy.sh master       # bewust master (alleen als je weet waarom)
#
# LET OP: deze Caddy bedient UAT **en** PROD. Een fout hier legt productie plat.
#
# DE CONFIG VOLGT DE RELEASE-TAG, NIET MASTER. UAT en PROD draaien een vastgepinde
# tag; volgde de proxy master, dan zou een kleine Caddy-ingreep ongevraagd alle
# sindsdien gemaakte proxywijzigingen naar productie duwen. Concreet gebeurde dat
# bijna: master routeert alles naar de backend (React-exit #405), terwijl v1.14.0
# nog een aparte frontend-container heeft — dat had de site platgelegd.
#
# De SPLITSING is bewust:
#   - de CONFIG (caddy/Caddyfile.shared) komt uit de gekozen tag;
#   - de TOOLING (dit script, docker-compose.caddy.yml, tests/) komt uit master,
#     zodat veiligheidsverbeteringen niet hoeven te wachten op een release.
#
# Drie vangnetten, in deze volgorde:
#   1) `caddy validate` op de nieuwe config, VOOR de draaiende proxy geraakt wordt;
#   2) een rooktest tegen PROD na de recreate;
#   3) automatisch herstel van de vorige config als die rooktest faalt.
#
# Achtergrond (#312/#314): `caddy reload` (admin-API, in-memory) is onbetrouwbaar
# en overleeft geen herstart. We doen `up -d --force-recreate`, dat de config vers
# van schijf laadt, zodat compressie (#303) elke herstart overleeft.
set -euxo pipefail

cd "$(dirname "$0")"

COMPOSE="docker-compose.caddy.yml"

# Snapshot van de NU draaiende config, vóór welke git-operatie dan ook — dit is
# het bestand dat in de container gemount is. Overleeft de re-exec via export.
if [ -z "${CADDY_PREV_CONF:-}" ]; then
  CADDY_PREV_CONF="$(mktemp /tmp/caddyfile-prev.XXXXXX)"
  cp caddy/Caddyfile.shared "$CADDY_PREV_CONF"
  export CADDY_PREV_CONF
fi

# Welke ref levert de config? Argument > CADDY_REF > de tag die PROD nu draait.
# Er is BEWUST geen terugval op master: dat is precies de fout die we uitsluiten.
REF="${1:-${CADDY_REF:-}}"
if [ -z "$REF" ]; then
  # Relatief pad, zodat er geen serverpaden in deze publieke repo staan.
  PROD_DIR="${PROD_CHECKOUT_DIR:-../prod}"
  if [ -d "$PROD_DIR/.git" ]; then
    # --exact-match: staat PROD niet op een tag, dan raden we niet.
    REF="$(git -C "$PROD_DIR" describe --tags --exact-match 2>/dev/null || true)"
  fi
fi
if [ -z "$REF" ]; then
  echo "FOUT: kon niet bepalen welke tag PROD draait." >&2
  echo "Geef de tag expliciet mee, bv: ./deploy-caddy.sh v1.14.0" >&2
  echo "(of zet PROD_CHECKOUT_DIR naar de prod-checkout)" >&2
  exit 1
fi

git fetch --tags --prune origin

# TOOLING op master. Hierna kan dit script zelf gewijzigd zijn, dus re-exec één
# keer (#162-patroon) zodat de rest uit de juiste scriptinhoud komt.
git reset --hard origin/master
git checkout -B master origin/master
if [ -z "${CADDY_REEXEC:-}" ]; then
  export CADDY_REEXEC=1
  exec "$0" "$@"
fi

# CONFIG uit de gekozen ref. Dit maakt de werkmap bewust "vuil" voor dit ene
# bestand; de volgende deploy zet hem weer recht.
git show "$REF:caddy/Caddyfile.shared" > caddy/Caddyfile.shared
echo "Caddy-config genomen uit: $REF"

# Veiligheidscheck: de compressie (#303) hoort in de gedeelde config te staan.
if ! grep -q 'encode' caddy/Caddyfile.shared; then
  echo "FOUT: 'encode' ontbreekt in caddy/Caddyfile.shared — config NIET toegepast." >&2
  cp "$CADDY_PREV_CONF" caddy/Caddyfile.shared
  exit 1
fi

# VANGNET 1 — valideer in een wegwerpcontainer, VOOR we de draaiende proxy
# aanraken. `run --rm --no-deps` publiceert geen poorten en start niets anders op;
# de env_file (.env.caddy) wordt wel geladen, zodat de {$DOMAIN}-placeholders
# ingevuld worden zoals bij een echte start. Faalt dit, dan blijft de oude proxy
# gewoon draaien en zetten we het configbestand terug.
if ! docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint caddy caddy \
     validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
  echo "!! CONFIG UIT $REF IS ONGELDIG — proxy niet aangeraakt." >&2
  cp "$CADDY_PREV_CONF" caddy/Caddyfile.shared
  exit 1
fi

# Verse container = config vers van schijf (overleeft herstarts).
docker compose -f "$COMPOSE" up -d --force-recreate caddy

# VANGNET 2 — rooktest tegen PROD. Domeinen komen uit .env.caddy (niet in git).
# PROD is de gate; UAT testen we ook maar enkel als waarschuwing, want een om
# andere redenen platliggende UAT-stack mag geen goede config terugdraaien.
domain_from_env() {
  sed -nE "s/^$1=[\"']?([^\"']*)[\"']?.*/\1/p" .env.caddy | head -1
}
PROD_DOMAIN="$(domain_from_env PROD_DOMAIN)"
UAT_DOMAIN="$(domain_from_env UAT_DOMAIN)"

if [ -n "$PROD_DOMAIN" ]; then
  if ! BASE="https://$PROD_DOMAIN" ./tests/run-all.sh; then
    echo "!! ROOKTEST FAALDE op PROD na de Caddy-wijziging." >&2
    # VANGNET 3 — zet de vorige config terug en hercreëer.
    echo ">>> Vorige config terugzetten en opnieuw hercreëren."
    cp "$CADDY_PREV_CONF" caddy/Caddyfile.shared
    docker compose -f "$COMPOSE" up -d --force-recreate caddy
    echo "!! TERUGGEROLD naar de vorige config. De config uit $REF is NIET actief." >&2
    echo "!! Snapshot van de teruggezette config: $CADDY_PREV_CONF" >&2
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

echo "Gedeelde Caddy hercreëerd met de config uit $REF — dekt alle domeinen."
