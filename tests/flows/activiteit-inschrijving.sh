#!/usr/bin/env bash
DESC="Betaalde activiteit aanmaken (admin) en er publiek voor inschrijven werkt end-to-end"
# Flow: admin maakt een activiteit met één onderdeel en één betaald product;
# daarna schrijft een bezoeker zich publiek in voor dat product.
#
# Test de echte keten: activiteit -> onderdeel -> betaald product -> publieke
# inschrijving -> betaalrecord. Betaalmethode "transfer" zodat er GEEN externe
# Mollie-call nodig is (geen afhankelijkheid van MOLLIE_API_KEY op HDEV).
#
# Admin-auth: deze flow leest een admin-JWT uit $ADMIN_TOKEN (zie lib.sh /
# README). Zonder token wordt de flow als SKIP getoond i.p.v. te falen.
#
# LET OP: dit schrijft echte (test)data weg (activiteit + inschrijving). Het
# wordt NIET opgeruimd — een activiteit met een inschrijving en betaalrecord kan
# niet veilig verwijderd worden zonder die afhankelijkheden. Draai enkel op
# HDEV/UAT, nooit op PROD.
set -uo pipefail
source "$(dirname "$0")/../lib.sh"

require_admin_token

# 1) Activiteit aanmaken (toekomstige datum, zodat inschrijven open is).
act_body='{"name":"Flowtest betaalde activiteit","date":"2099-12-31","location":"Teststraat"}'
code=$(curl -s -o /tmp/flow_act -w '%{http_code}' -X POST "${BASE}/api/v1/activities" \
  -H 'Content-Type: application/json' -H "$(auth_header)" -d "$act_body")
expect_status 200 "$code" "activiteit aangemaakt (admin)"
ACT_ID=$(jq -r '.id // empty' /tmp/flow_act 2>/dev/null)
[ -n "${ACT_ID:-}" ] || fatal "geen activiteit-id terug (admin-token geldig?)"

# 2) Onderdeel (component) toevoegen aan de activiteit.
comp_body='{"name":"Flowtest onderdeel"}'
code=$(curl -s -o /tmp/flow_comp -w '%{http_code}' -X POST \
  "${BASE}/api/v1/activities/${ACT_ID}/components" \
  -H 'Content-Type: application/json' -H "$(auth_header)" -d "$comp_body")
expect_status 200 "$code" "onderdeel toegevoegd"
COMP_ID=$(jq -r '.id // empty' /tmp/flow_comp 2>/dev/null)
[ -n "${COMP_ID:-}" ] || fatal "geen onderdeel-id terug"

# 3) Betaald product toevoegen (is_free=false, price > 0).
PRICE="7.50"
prod_body="{\"name\":\"Flowtest product\",\"price\":${PRICE},\"is_free\":false}"
code=$(curl -s -o /tmp/flow_prod -w '%{http_code}' -X POST \
  "${BASE}/api/v1/activities/${ACT_ID}/components/${COMP_ID}/products" \
  -H 'Content-Type: application/json' -H "$(auth_header)" -d "$prod_body")
expect_status 200 "$code" "betaald product toegevoegd"
PROD_ID=$(jq -r '.id // empty' /tmp/flow_prod 2>/dev/null)
[ -n "${PROD_ID:-}" ] || fatal "geen product-id terug"

# 4) Publiek inschrijven voor dat product (1 stuk), via overschrijving.
reg_body=$(cat <<JSON
{"contact_name":"Flow Inschrijver","contact_email":"flow+act@example.com",
 "payment_method":"transfer","component_id":${COMP_ID},
 "items":[{"product_id":${PROD_ID},"quantity":1}]}
JSON
)
code=$(curl -s -o /tmp/flow_reg -w '%{http_code}' -X POST \
  "${BASE}/api/v1/activities/${ACT_ID}/register" \
  -H 'Content-Type: application/json' -d "$reg_body")
expect_status 200 "$code" "publieke inschrijving geslaagd"
REG_ID=$(jq -r '.id // empty' /tmp/flow_reg 2>/dev/null)
[ -n "${REG_ID:-}" ] || fatal "geen inschrijving-id terug"

# 5) Totaalbedrag verifiëren via het admin betaalrecord-endpoint: het bedrag
#    moet exact overeenkomen met de productprijs (1 × 7.50).
code=$(curl -s -o /tmp/flow_pay -w '%{http_code}' \
  "${BASE}/api/v1/payment-status/records/registration/${REG_ID}" \
  -H "$(auth_header)")
expect_status 200 "$code" "betaalrecord opgevraagd (admin)"
amount=$(jq -r '.[0].amount // empty' /tmp/flow_pay 2>/dev/null)
matches=$(awk -v a="$amount" -v p="$PRICE" 'BEGIN { print (a + 0 == p + 0) ? 1 : 0 }')
expect_true "$matches" "totaalbedrag = productprijs (verwacht ${PRICE}, kreeg ${amount})"

t_summary
