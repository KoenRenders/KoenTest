#!/usr/bin/env bash
DESC="Live stack antwoordt: publieke endpoints geven 200, admin is afgeschermd"
# Post-deploy ROOKTEST — strikt ALLEEN-LEZEN. Maakt GEEN data aan (geen leden,
# pagina's, betalingen of inschrijvingen). Veilig om op PROD te draaien.
#
# Doel: na een deploy in één oogopslag bevestigen dat de echte draaiende stack
# leeft — app antwoordt, DB is verbonden (publieke lijsten laden), en de
# admin-administratie is afgeschermd. Logica/regressie zit in de pytest-suite
# (CI + lokaal), niet hier.
set -uo pipefail
source "$(dirname "$0")/../lib.sh"

# 1) Wachten tot de stack klaar is: poll /api/health tot 200 (max ~60s).
ready=0
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/api/health" 2>/dev/null || echo 000)
  [ "$code" = "200" ] && { ready=1; break; }
  sleep 2
done
[ "$ready" = "1" ] || fatal "stack niet gezond binnen de tijd (/api/health gaf geen 200 op ${BASE})"

# 2) Publieke leesendpoints moeten 200 geven (app + DB verbonden).
check_get() {  # URL OMSCHRIJVING
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}$1" 2>/dev/null || echo 000)
  expect_status 200 "$code" "$2"
}
check_get "/api/health"            "health-endpoint"
check_get "/api/v1/activities"     "publieke activiteitenlijst"
check_get "/api/v1/postal-codes"   "postcode-lookup"
check_get "/api/v1/pages"          "publieke CMS-pagina's"
check_get "/api/v1/sponsors"       "sponsorlijst (footer)"

# 3) Admin-administratie moet afgeschermd zijn zonder token (geen datalek).
code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/api/v1/payment-status/records" 2>/dev/null || echo 000)
expect_status 401 "$code" "betaaladministratie eist auth"
code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/api/v1/admin/media" 2>/dev/null || echo 000)
expect_status_one_of "$code" "media-beheer eist auth" 401 403

t_summary
