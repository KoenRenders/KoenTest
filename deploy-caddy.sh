#!/usr/bin/env bash
# Past de GEDEELDE Caddy-config toe en herstart de gedeelde Caddy, zodat de
# wijziging gegarandeerd én blijvend actief is.
# Draaien uit de caddy/-checkout (bv. /opt/raakmillegem/caddy):
#
#   ./deploy-caddy.sh              # elk deel uit de tag van zijn eigen omgeving
#   ./deploy-caddy.sh v1.15.0      # alles uit één expliciete ref
#
# LET OP: deze Caddy bedient UAT **en** PROD. Een fout hier legt productie plat.
#
# DE CONFIG VOLGT DE RELEASE-TAGS, NIET MASTER. Volgde de proxy master, dan zou
# een kleine ingreep ongevraagd alle sindsdien gemaakte proxywijzigingen naar
# productie duwen. Dat gebeurde bijna: master routeert alles naar de backend
# (React-exit #405) terwijl v1.14.0 nog een aparte frontend-container draait.
#
# De config is opgesplitst zodat UAT vooruit mag lopen op PROD:
#   caddy/parts/snippets.caddy    gedeeld -> tag van PROD (conservatief)
#   caddy/parts/sites-uat.caddy   UAT     -> tag van UAT
#   caddy/parts/sites-prod.caddy  PROD    -> tag van PROD
# Het gedeelde deel moet daarom expand/contract-gewijs wijzigen; zie CLAUDE.md,
# "Shared Caddy: expand/contract".
#
# De TOOLING (dit script, docker-compose.caddy.yml, tests/) komt uit master,
# zodat een veiligheidsfix niet op een release hoeft te wachten.
#
# Vier vangnetten, in deze volgorde:
#   1) `caddy validate` op de nieuwe config, VOOR de draaiende proxy geraakt wordt;
#   2) een rooktest tegen PROD na de recreate;
#   3) herstel van de vorige config als die rooktest faalt;
#   4) herstel van de vorige image-digest, voor het geval de Caddy-VERSIE zelf de
#      storing is — een config-rollback helpt daar niet tegen.
#
# Achtergrond (#312/#314): `caddy reload` (admin-API, in-memory) is onbetrouwbaar
# en overleeft geen herstart. We doen `up -d --force-recreate`, dat de config vers
# van schijf laadt, zodat compressie (#303) elke herstart overleeft.
set -euxo pipefail

cd "$(dirname "$0")"

COMPOSE="docker-compose.caddy.yml"

# ── Snapshot van wat er NU draait, vóór welke wijziging dan ook ───────────────
# Zowel de config als de image-digest. Overleeft de re-exec via export.
if [ -z "${CADDY_PREV_DIR:-}" ]; then
  CADDY_PREV_DIR="$(mktemp -d /tmp/caddy-prev.XXXXXX)"
  cp caddy/Caddyfile.shared "$CADDY_PREV_DIR/Caddyfile.shared"
  mkdir -p "$CADDY_PREV_DIR/parts"
  cp -a caddy/parts/. "$CADDY_PREV_DIR/parts/" 2>/dev/null || true
  export CADDY_PREV_DIR

  # De image-digest van de draaiende container. RepoDigest is stabiel, ook als de
  # tag later hergebruikt wordt; bij een lokaal gebouwde image valt het terug op
  # het image-id. Leeg = er draait nog niets (eerste deploy).
  CADDY_PREV_IMAGE=""
  _cid="$(docker compose -f "$COMPOSE" ps -q caddy 2>/dev/null || true)"
  if [ -n "$_cid" ]; then
    _iid="$(docker inspect "$_cid" --format '{{.Image}}' 2>/dev/null || true)"
    if [ -n "$_iid" ]; then
      CADDY_PREV_IMAGE="$(docker image inspect "$_iid" \
        --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}' 2>/dev/null || true)"
    fi
  fi
  export CADDY_PREV_IMAGE
fi

# ── Welke refs leveren de config? ────────────────────────────────────────────
# Argument > CADDY_REF > de tag van de betreffende omgeving. Er is BEWUST geen
# terugval op master: dat is precies de fout die we uitsluiten.
ref_of() {  # $1 = checkout-map; leeg resultaat = onbekend
  [ -d "$1/.git" ] || return 0
  git -C "$1" describe --tags --exact-match 2>/dev/null || true
}

EXPLICIT="${1:-${CADDY_REF:-}}"
if [ -n "$EXPLICIT" ]; then
  PROD_REF="$EXPLICIT"; UAT_REF="$EXPLICIT"
else
  # Relatieve paden, zodat er geen serverpaden in deze publieke repo staan.
  PROD_REF="$(ref_of "${PROD_CHECKOUT_DIR:-../prod}")"
  UAT_REF="$(ref_of "${UAT_CHECKOUT_DIR:-../uat}")"
fi
if [ -z "$PROD_REF" ]; then
  echo "FOUT: kon niet bepalen welke tag PROD draait." >&2
  echo "Geef een ref expliciet mee, bv: ./deploy-caddy.sh v1.14.0" >&2
  echo "(of zet PROD_CHECKOUT_DIR naar de prod-checkout)" >&2
  exit 1
fi
[ -n "$UAT_REF" ] || UAT_REF="$PROD_REF"

git fetch --tags --prune origin

# ── Tooling op master, daarna één re-exec (#162-patroon) ─────────────────────
git reset --hard origin/master
git checkout -B master origin/master
if [ -z "${CADDY_REEXEC:-}" ]; then
  export CADDY_REEXEC=1
  exec "$0" "$@"
fi

restore_prev() {
  cp "$CADDY_PREV_DIR/Caddyfile.shared" caddy/Caddyfile.shared
  mkdir -p caddy/parts
  cp -a "$CADDY_PREV_DIR/parts/." caddy/parts/ 2>/dev/null || true
}

# ── Config schrijven uit de gekozen refs ─────────────────────────────────────
git show "$PROD_REF:caddy/Caddyfile.shared" > caddy/Caddyfile.shared

if grep -q '^import /etc/caddy/parts/' caddy/Caddyfile.shared; then
  # Gesplitste config: elk deel uit zijn eigen omgeving.
  mkdir -p caddy/parts
  git show "$PROD_REF:caddy/parts/snippets.caddy"   > caddy/parts/snippets.caddy
  git show "$PROD_REF:caddy/parts/sites-prod.caddy" > caddy/parts/sites-prod.caddy
  # Overgangsgeval: draait UAT nog een tag van vóór de splitsing, dan bestaat
  # dat deel daar niet. Val dan terug op PROD's versie (= het gedrag van vandaag)
  # i.p.v. halverwege af te breken met een half geschreven config.
  if git cat-file -e "$UAT_REF:caddy/parts/sites-uat.caddy" 2>/dev/null; then
    git show "$UAT_REF:caddy/parts/sites-uat.caddy" > caddy/parts/sites-uat.caddy
    echo "Config: gedeeld+PROD uit $PROD_REF, UAT uit $UAT_REF"
  else
    git show "$PROD_REF:caddy/parts/sites-uat.caddy" > caddy/parts/sites-uat.caddy
    echo "LET OP: $UAT_REF heeft nog geen caddy/parts/ — UAT-deel uit $PROD_REF genomen."
  fi
else
  # Oude, monolithische config (tags van vóór de splitsing). Dan bevat het ene
  # bestand óók de UAT-blokken en kan UAT niet apart vooruitlopen.
  echo "LET OP: $PROD_REF heeft nog de ongesplitste Caddyfile.shared."
  echo "        UAT en PROD volgen dus allebei $PROD_REF; UAT-first werkt pas"
  echo "        zodra PROD een tag mét caddy/parts/ draait."
fi

# Veiligheidscheck: de compressie (#303) hoort in de config te staan.
if ! grep -rq 'encode' caddy/Caddyfile.shared caddy/parts/ 2>/dev/null; then
  echo "FOUT: 'encode' ontbreekt in de Caddy-config — NIET toegepast." >&2
  restore_prev
  exit 1
fi

# ── VANGNET 1 — valideren vóór we de draaiende proxy aanraken ────────────────
# `run --rm --no-deps` publiceert geen poorten en start niets anders op; de
# env_file (.env.caddy) wordt wel geladen, zodat de {$DOMAIN}-placeholders
# ingevuld worden zoals bij een echte start.
if ! docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint caddy caddy \
     validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
  echo "!! CONFIG IS ONGELDIG — proxy niet aangeraakt." >&2
  restore_prev
  exit 1
fi

docker compose -f "$COMPOSE" up -d --force-recreate caddy

# ── VANGNET 2 — rooktest tegen PROD (de gate) ────────────────────────────────
domain_from_env() {
  sed -nE "s/^$1=[\"']?([^\"']*)[\"']?.*/\1/p" .env.caddy | head -1
}
PROD_DOMAIN="$(domain_from_env PROD_DOMAIN)"
UAT_DOMAIN="$(domain_from_env UAT_DOMAIN)"

if [ -n "$PROD_DOMAIN" ]; then
  if ! BASE="https://$PROD_DOMAIN" ./tests/run-all.sh; then
    echo "!! ROOKTEST FAALDE op PROD na de Caddy-wijziging." >&2

    # VANGNET 3 + 4 — vorige config én vorige image terugzetten.
    restore_prev
    if [ -n "$CADDY_PREV_IMAGE" ]; then
      echo ">>> Terug naar de vorige image: $CADDY_PREV_IMAGE"
      CADDY_IMAGE="$CADDY_PREV_IMAGE" docker compose -f "$COMPOSE" up -d --force-recreate caddy
    else
      docker compose -f "$COMPOSE" up -d --force-recreate caddy
    fi

    echo "!! TERUGGEROLD. De config uit $PROD_REF/$UAT_REF is NIET actief." >&2
    echo "!! LET OP: dit is een RUNTIME-rollback. Stond de storing in een nieuwe" >&2
    echo "!! Caddy-versie, dan wijst docker-compose.caddy.yml daar nog steeds naar" >&2
    echo "!! en haalt de volgende deploy hem opnieuw op. Draai de pin terug in git." >&2
    echo "!! Snapshot van de teruggezette config: $CADDY_PREV_DIR" >&2
    exit 1
  fi
  echo "Rooktest OK op PROD."
else
  echo "PROD_DOMAIN onbekend in .env.caddy — rooktest tegen PROD overgeslagen"
fi

# UAT testen we ook, maar enkel als waarschuwing: een om andere redenen
# platliggende UAT-stack mag geen goede config terugdraaien.
if [ -n "$UAT_DOMAIN" ]; then
  BASE="https://$UAT_DOMAIN" ./tests/run-all.sh \
    || echo "LET OP: rooktest tegen UAT faalde. Geen rollback (PROD is de gate) — controleer de UAT-stack."
fi

echo "Gedeelde Caddy hercreëerd — PROD-deel uit $PROD_REF, UAT-deel uit $UAT_REF."
