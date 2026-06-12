#!/usr/bin/env bash
DESC="Prijs niet manipuleerbaar (vals product_id geweigerd) en betaalstatus enkel door admin te verversen"
# Een vals/onbestaand product_id mag geen gratis regel opleveren, en het
# refresh-endpoint moet admin-auth eisen.
set -uo pipefail
source "$(dirname "$0")/../lib.sh"

read -r ACT COMP PROD <<<"$(discover_product)"
[ -n "${ACT:-}" ] || fatal "geen activiteit met producten gevonden (maak er één aan, PAID_PRODUCTS)"

# 1. Vreemd/onbestaand product_id moet geweigerd worden (400 "Ongeldig product").
code=$(curl -s -o /tmp/smoke_t -w '%{http_code}' -X POST \
  "${BASE}/api/v1/activities/${ACT}/register" \
  -H 'Content-Type: application/json' \
  -d "{\"contact_name\":\"Vals\",\"contact_email\":\"t+vals@example.com\",\"component_id\":${COMP},\"items\":[{\"product_id\":999999,\"quantity\":1}]}")
expect_status 400 "$code" "vals product_id geweigerd"
expect_contains /tmp/smoke_t "Ongeldig product" "foutmelding 'Ongeldig product'"

# 2. Refresh-endpoint moet admin-auth eisen (geen token -> 401/403).
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST \
  "${BASE}/api/v1/payment-status/records/00000000-0000-0000-0000-000000000000/refresh")
expect_status_one_of "$code" "refresh vereist admin-auth" 401 403

t_summary
