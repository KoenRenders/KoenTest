#!/usr/bin/env bash
# Draait alle smoke-tests in deze map en toont één samenvattend overzicht.
#
#   BASE=http://localhost:8081 ./run-all.sh
#
# Per test: PASS (groen) of FAIL (rood). Bij falen wordt de volledige uitvoer
# van die test onderaan getoond zodat je meteen ziet wat er behartigd moet
# worden. Exit-code 0 = alles OK, 1 = minstens één test faalde.
set -uo pipefail

cd "$(dirname "$0")"

GREEN=$'\e[32m'; RED=$'\e[31m'; BOLD=$'\e[1m'; RESET=$'\e[0m'
# Geen kleur als de uitvoer niet naar een terminal gaat (bv. logbestand).
[ -t 1 ] || { GREEN=""; RED=""; BOLD=""; RESET=""; }

BASE="${BASE:-http://localhost:8081}"
echo "${BOLD}== Smoke-tests tegen ${BASE} ==${RESET}"
echo

PASSED=0; FAILED=0
declare -a FAILED_NAMES
declare -a FAILED_OUTPUT

for script in *.sh; do
  # Sla de runner zelf over.
  [ "$script" = "run-all.sh" ] && continue
  name="${script%.sh}"
  out=$(BASE="$BASE" bash "$script" 2>&1)
  code=$?
  if [ "$code" -eq 0 ]; then
    echo "  ${GREEN}PASS${RESET}  ${name}"
    PASSED=$((PASSED + 1))
  else
    echo "  ${RED}FAIL${RESET}  ${name}"
    FAILED=$((FAILED + 1))
    FAILED_NAMES+=("$name")
    FAILED_OUTPUT+=("$out")
  fi
done

echo
echo "${BOLD}Resultaat: ${PASSED} geslaagd, ${FAILED} gefaald${RESET}"

if [ "$FAILED" -gt 0 ]; then
  echo
  echo "${BOLD}${RED}Te behartigen:${RESET}"
  for i in "${!FAILED_NAMES[@]}"; do
    echo
    echo "${RED}──── ${FAILED_NAMES[$i]} ────${RESET}"
    echo "${FAILED_OUTPUT[$i]}"
  done
  exit 1
fi

echo "${GREEN}${BOLD}ALLES OK ✅${RESET}"
