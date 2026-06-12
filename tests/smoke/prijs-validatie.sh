#!/usr/bin/env bash
DESC="Product met negatieve prijs wordt geweigerd (prijs >= 0)"
# Controleert dat een admin geen product met een negatieve prijs kan aanmaken.
# Afscherming op twee niveaus: een vorm-validatie (nette 422) én een
# DB-constraint CHECK (price >= 0) als vangnet. We verwachten een weigering,
# nooit een 200.
#
# Admin-auth: leest een admin-JWT uit $ADMIN_TOKEN (zie lib.sh / README).
# Zonder token wordt deze test als SKIP getoond i.p.v. te falen.
#
# Geen neveneffect: bij correcte werking wordt er niets weggeschreven (de
# aanmaak faalt). We schrijven op een BESTAANDE component, zodat we zelf geen
# activiteit/onderdeel hoeven aan te maken.
set -uo pipefail
source "$(dirname "$0")/../lib.sh"

require_admin_token

read -r ACT_ID COMP_ID _ <<<"$(discover_product)"
[ -n "${COMP_ID:-}" ] || fatal "geen bestaande activiteit met onderdeel gevonden om op te testen"

prod_body='{"name":"Negatieve-prijs test","price":-1,"is_free":false}'
code=$(curl -s -o /tmp/prijs_neg -w '%{http_code}' -X POST \
  "${BASE}/api/v1/activities/${ACT_ID}/components/${COMP_ID}/products" \
  -H 'Content-Type: application/json' -H "$(auth_header)" -d "$prod_body")
# 422 = vorm-validatie; 400 = expliciete afwijzing; 500 = DB-constraint vangnet.
expect_status_one_of "$code" "negatieve prijs geweigerd (kreeg $code)" 422 400 500

t_summary
