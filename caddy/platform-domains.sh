#!/usr/bin/env bash
# Leidt de platformdomeinen van de gedeelde Caddy af uit de app-configuratie (#866).
#
# EEN FEIT, EEN BEWAARPLAATS. "Dit domein is het platform" stond op twee plaatsen:
# PLATFORM_HOSTS in .env.<env> (wat de app als platform-host herkent) en
# PLATFORM_*_DOMAIN in .env.caddy (wat de proxy bedient). Niets controleerde of ze
# gelijk waren, en op PROD waren ze dat niet: Caddy bediende het subdomein terwijl
# de app alleen het apex-domein kende. Het verzoek viel door de laatste regel van
# `resolve_request` en belandde op de standaardtenant — Raak Millegem in plaats van
# de platform-landing. Op UAT stonden ze wél gelijk, en daar werkte het; dat was
# meteen het bewijs dat het configuratie was en geen code.
#
# Dit is dezelfde vorm als #860, en dezelfde keuze: maak het onmogelijk in plaats
# van het te controleren. De app-variabele is de bron, de proxy leidt af. Die
# richting en niet andersom, omdat één gedeelde Caddy twee omgevingen bedient met
# elk hun eigen platformdomein — de waarde hoort dus per omgeving te staan, en daar
# staat ze al.
#
# Gebruik (source, geen aanroep): . caddy/platform-domains.sh
# Zet PLATFORM_UAT_DOMAIN en PLATFORM_PROD_DOMAIN in de omgeving; docker-compose
# .caddy.yml geeft ze door aan de container.

# Leest PLATFORM_HOSTS uit het env-bestand van één omgeving.
#
# PLATFORM_HOSTS is een komma-gescheiden lijst; een Caddy-siteadres scheidt meerdere
# hosts met een SPATIE. Beide vormen bestaan al, dus dit vertaalt ze in plaats van er
# een derde bij te verzinnen.
platformdomein_van() {  # $1 = omgeving (uat|prod), $2 = checkout-map
  local omgeving="$1" map="$2" bestand="$2/.env.$1" waarde
  if [ ! -f "$bestand" ]; then
    echo "FOUT: $bestand niet gevonden — kan het platformdomein van $omgeving niet afleiden." >&2
    echo "  De gedeelde Caddy leidt dat af uit PLATFORM_HOSTS van die omgeving (#866)." >&2
    echo "  Zet ${omgeving^^}_CHECKOUT_DIR naar de juiste checkout." >&2
    return 1
  fi
  waarde="$(sed -nE 's/^PLATFORM_HOSTS=["'"'"']?([^"'"'"']*)["'"'"']?.*/\1/p' "$bestand" | head -1)"
  waarde="$(echo "$waarde" | tr ',' ' ' | tr -s ' ' | sed 's/^ *//; s/ *$//')"
  if [ -z "$waarde" ]; then
    # Leeg is gevaarlijker dan fout: een leeg siteadres maakt de HELE Caddy-config
    # ongeldig, dus dan start de proxy niet en ligt PROD plat. Liever hier stoppen.
    echo "FOUT: PLATFORM_HOSTS is leeg of ontbreekt in $bestand ($omgeving)." >&2
    echo "  De gedeelde Caddy leidt het platformdomein van $omgeving daaruit af (#866);" >&2
    echo "  een lege waarde geeft een leeg siteadres en daarmee een ongeldige config" >&2
    echo "  voor ALLE sites." >&2
    return 1
  fi
  echo "$waarde"
}

PLATFORM_UAT_DOMAIN="$(platformdomein_van uat "${UAT_CHECKOUT_DIR:-../uat}")" || return 1 2>/dev/null || exit 1
PLATFORM_PROD_DOMAIN="$(platformdomein_van prod "${PROD_CHECKOUT_DIR:-../prod}")" || return 1 2>/dev/null || exit 1
export PLATFORM_UAT_DOMAIN PLATFORM_PROD_DOMAIN
