#!/usr/bin/env bash
# Smoke: invoervalidatie bij inschrijving die je niet via de GUI kunt forceren
# (de GUI blokkeert zulke invoer al; dit test de server zelf).
#   - ongeldig e-mailadres        -> 422 (EmailStr)
#   - negatief aantal             -> 400
#   - absurd hoog aantal          -> 400 (boven MAX_ITEM_QUANTITY)
set -uo pipefail
source "$(dirname "$0")/../lib.sh"

read -r ACT COMP PROD <<<"$(discover_product)"
[ -n "${ACT:-}" ] || fatal "geen activiteit met producten gevonden (maak er één aan, PAID_PRODUCTS)"

reg() {  # JSON-body -> echoot statuscode (body in /tmp/smoke_t)
  curl -s -o /tmp/smoke_t -w '%{http_code}' -X POST \
    "${BASE}/api/v1/activities/${ACT}/register" \
    -H 'Content-Type: application/json' -d "$1"
}

# Ongeldig e-mailadres -> 422
code=$(reg "{\"contact_name\":\"X\",\"contact_email\":\"geen-email\",\"component_id\":${COMP},\"items\":[{\"product_id\":${PROD},\"quantity\":1}]}")
expect_status 422 "$code" "ongeldig e-mailadres geweigerd"

# Negatief aantal -> 400
code=$(reg "{\"contact_name\":\"X\",\"contact_email\":\"t+neg@example.com\",\"component_id\":${COMP},\"items\":[{\"product_id\":${PROD},\"quantity\":-1}]}")
expect_status 400 "$code" "negatief aantal geweigerd"

# Absurd hoog aantal -> 400
code=$(reg "{\"contact_name\":\"X\",\"contact_email\":\"t+hoog@example.com\",\"component_id\":${COMP},\"items\":[{\"product_id\":${PROD},\"quantity\":100000}]}")
expect_status 400 "$code" "te hoog aantal geweigerd"

t_summary
