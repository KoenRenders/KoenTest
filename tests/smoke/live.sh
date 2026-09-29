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

# 2) Publieke pagina's moeten 200 geven (app + DB verbonden). Wat een bezoeker
#    ziet, niet een JSON-route die niemand anders gebruikt (CR-13 fase 4b, #1251):
#    de startpagina draagt de footer met sponsors, de activiteitenlijst leest de
#    activiteiten, "Word lid" leest de postcodes.
check_get() {  # URL OMSCHRIJVING
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}$1" 2>/dev/null || echo 000)
  expect_status 200 "$code" "$2"
}
check_get "/api/health"            "health-endpoint"
check_get "/"                      "startpagina (met sponsors in de footer)"
check_get "/activiteiten"          "publieke activiteitenlijst"
check_get "/lid-worden"            "word-lid (postcodes uit de DB)"

# 3) De beheerschermen moeten afgeschermd zijn zonder sessie (geen datalek).
code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/admin/betalingen" 2>/dev/null || echo 000)
expect_status 401 "$code" "betaalbeheer eist een sessie"
code=$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/admin/media" 2>/dev/null || echo 000)
expect_status 401 "$code" "mediabeheer eist een sessie"

t_summary
