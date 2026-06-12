#!/usr/bin/env bash
DESC="Betaalstatus bijwerken weigert een onmogelijk betaald bedrag (negatief of hoger dan verschuldigd)"
# Controleert de admin-PATCH op een betaalrecord: het 'amount_paid' mag niet
# negatief zijn en niet hoger dan het verschuldigde bedrag. Beide moeten 400
# geven, zonder het record te wijzigen.
#
# Admin-auth: leest een admin-JWT uit $ADMIN_TOKEN (zie lib.sh / README).
# Zonder token wordt deze test als SKIP getoond i.p.v. te falen.
#
# Geen neveneffect: we sturen enkel ONGELDIGE waarden, die geweigerd horen te
# worden; bij correcte werking blijft het bestaande record onveranderd. We
# gebruiken een BESTAAND record (geen nieuw aangemaakt).
set -uo pipefail
source "$(dirname "$0")/../lib.sh"

require_admin_token

# Pak een bestaand betaalrecord (id + verschuldigd bedrag) op.
code=$(curl -s -o /tmp/pay_records -w '%{http_code}' \
  "${BASE}/api/v1/payment-status/records" -H "$(auth_header)")
[ "$code" = "200" ] || fatal "kon betaalrecords niet opvragen (status $code; admin-token geldig?)"

REC_ID=$(jq -r '.[0].id // empty' /tmp/pay_records 2>/dev/null)
AMOUNT=$(jq -r '.[0].amount // empty' /tmp/pay_records 2>/dev/null)
[ -n "${REC_ID:-}" ] || fatal "geen enkel betaalrecord aanwezig om op te testen"

# 1) Negatief bedrag -> 400.
code=$(curl -s -o /dev/null -w '%{http_code}' -X PATCH \
  "${BASE}/api/v1/payment-status/records/${REC_ID}" \
  -H 'Content-Type: application/json' -H "$(auth_header)" \
  -d '{"amount_paid":-5}')
expect_status 400 "$code" "negatief amount_paid geweigerd"

# 2) Hoger dan het verschuldigde bedrag -> 400.
TOO_HIGH=$(awk -v a="$AMOUNT" 'BEGIN { printf "%.2f", a + 1000 }')
code=$(curl -s -o /dev/null -w '%{http_code}' -X PATCH \
  "${BASE}/api/v1/payment-status/records/${REC_ID}" \
  -H 'Content-Type: application/json' -H "$(auth_header)" \
  -d "{\"amount_paid\":${TOO_HIGH}}")
expect_status 400 "$code" "amount_paid hoger dan verschuldigd geweigerd"

t_summary
