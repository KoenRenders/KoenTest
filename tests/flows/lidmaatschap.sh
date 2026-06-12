#!/usr/bin/env bash
DESC="Lid worden via overschrijving werkt end-to-end (lidgeld berekend)"
# Flow: publiek lid worden via overschrijving (geen Mollie).
#
# Test de echte keten: postcode-lookup -> persoon -> lidmaatschap -> betaalrecord.
# Betaalmethode "transfer" zodat er geen Mollie-betaling wordt aangemaakt.
#
# LET OP: dit schrijft een echt (test)lid weg. Draai enkel op HDEV/UAT, nooit PROD.
set -uo pipefail
source "$(dirname "$0")/../lib.sh"

PC=$(discover_postal_code)
[ -n "${PC:-}" ] || fatal "geen postcodes beschikbaar (seed_postal_codes nog niet gedraaid?)"

body=$(cat <<JSON
{"street":"Teststraat","house_number":"1","postal_code":"${PC}","payment_method":"transfer",
 "members":[{"last_name":"Testlid","first_name":"Smoke","relation_type":"HOOFDLID","email":"flow+lid@example.com"}]}
JSON
)

code=$(curl -s -o /tmp/flow_t -w '%{http_code}' -X POST "${BASE}/api/v1/families" \
  -H 'Content-Type: application/json' -d "$body")
expect_status 201 "$code" "lidmaatschap aangemaakt"

status=$(jq -r '.status // empty' /tmp/flow_t 2>/dev/null)
expect_eq "registered" "$status" "status = registered (overschrijving, geen online betaling)"

amount=$(jq -r '.amount // 0' /tmp/flow_t 2>/dev/null)
positive=$(awk -v a="$amount" 'BEGIN { print (a + 0 > 0) ? 1 : 0 }')
expect_true "$positive" "lidgeld berekend (> 0, kreeg ${amount})"

t_summary
