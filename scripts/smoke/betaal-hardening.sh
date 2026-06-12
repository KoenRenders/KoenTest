#!/usr/bin/env bash
# Smoke-test: betaal-hardening (product-id-validatie + refresh-auth).
#
# Draait tegen een lopende omgeving (HDEV/UAT). Geen secrets nodig; gebruikt
# enkel publieke endpoints + een onbevoegde call om de afscherming te testen.
#
#   BASE=http://localhost:8081 ./betaal-hardening.sh
#   BASE=https://hdev.jouw-domein ./betaal-hardening.sh
#
# Vereist: curl, jq.
set -uo pipefail

BASE="${BASE:-http://localhost:8081}"

pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; FAILED=1; }
FAILED=0

echo "== Betaal-hardening tegen ${BASE} =="

# --- Zoek een activiteit met minstens één product ---------------------------
acts=$(curl -fsS "${BASE}/api/v1/activities") || { echo "Kan /activities niet bereiken"; exit 1; }

read -r ACT_ID COMP_ID PROD_ID < <(echo "$acts" | jq -r '
  [ .[] as $a | $a.sub_registrations[]? as $c | $c.products[]? as $p
    | "\($a.id) \($c.id) \($p.id)" ] | first // empty')

if [ -z "${ACT_ID:-}" ]; then
  echo "Geen activiteit met producten gevonden — maak er eentje aan (PAID_PRODUCTS) en draai opnieuw."
  exit 1
fi
echo "Gevonden: activiteit=${ACT_ID} component=${COMP_ID} product=${PROD_ID}"

# --- Test 1: vreemd product_id moet geweigerd worden (400) ------------------
echo "[1] Inschrijving met VALS product_id (999999) -> verwacht 400"
resp=$(curl -s -o /tmp/smoke_body1 -w '%{http_code}' -X POST \
  "${BASE}/api/v1/activities/${ACT_ID}/register" \
  -H 'Content-Type: application/json' \
  -d "{\"contact_name\":\"Test Vals\",\"contact_email\":\"test+vals@example.com\",
       \"component_id\":${COMP_ID},\"items\":[{\"product_id\":999999,\"quantity\":1}]}")
if [ "$resp" = "400" ] && grep -q "Ongeldig product" /tmp/smoke_body1; then
  pass "geweigerd met 'Ongeldig product' (400)"
else
  fail "verwacht 400/'Ongeldig product', kreeg ${resp}: $(cat /tmp/smoke_body1)"
fi

# --- Test 2: geldig product_id, zonder betaling -> moet lukken --------------
echo "[2] Inschrijving met GELDIG product_id (${PROD_ID}), geen betaling -> verwacht 200"
resp=$(curl -s -o /tmp/smoke_body2 -w '%{http_code}' -X POST \
  "${BASE}/api/v1/activities/${ACT_ID}/register" \
  -H 'Content-Type: application/json' \
  -d "{\"contact_name\":\"Test Geldig\",\"contact_email\":\"test+ok@example.com\",
       \"component_id\":${COMP_ID},\"items\":[{\"product_id\":${PROD_ID},\"quantity\":1}]}")
if [ "$resp" = "200" ] || [ "$resp" = "201" ]; then
  pass "inschrijving aanvaard (${resp}) -- regressie OK"
else
  fail "verwacht 200, kreeg ${resp}: $(cat /tmp/smoke_body2)"
fi

# --- Test 3: refresh-endpoint moet auth eisen (geen token -> 401/403) -------
echo "[3] Refresh zonder admin-token -> verwacht 401/403"
resp=$(curl -s -o /tmp/smoke_body3 -w '%{http_code}' -X POST \
  "${BASE}/api/v1/payment-status/records/00000000-0000-0000-0000-000000000000/refresh")
if [ "$resp" = "401" ] || [ "$resp" = "403" ]; then
  pass "afgeschermd (${resp})"
else
  fail "verwacht 401/403, kreeg ${resp}: $(cat /tmp/smoke_body3)"
fi

echo
[ "$FAILED" = "0" ] && echo "ALLES OK" || { echo "ER ZIJN FOUTEN"; exit 1; }
