#!/usr/bin/env bash
# Draait alle tests (smoke/ en flows/) en toont één beknopt overzicht.
#
#   BASE=http://localhost:8081 ./run-all.sh
#
# Per test één regel: PASS / FAIL / SKIP. Bij FAIL of SKIP wordt onderaan
# enkel de uitvoer van díe test getoond — geen muur van geslaagde checks.
# Exit-code 0 = alles OK, 1 = minstens één test faalde.
set -uo pipefail
cd "$(dirname "$0")"

GREEN=$'\e[32m'; RED=$'\e[31m'; YELLOW=$'\e[33m'; BOLD=$'\e[1m'; RESET=$'\e[0m'
[ -t 1 ] || { GREEN=""; RED=""; YELLOW=""; BOLD=""; RESET=""; }

BASE="${BASE:-http://localhost:8081}"
echo "${BOLD}== Tests tegen ${BASE} ==${RESET}"
echo

PASS=0; FAIL=0; SKIP=0
declare -a PROBLEM_NAMES PROBLEM_OUTPUT

shopt -s nullglob
for script in smoke/*.sh flows/*.sh; do
  [ "$(basename "$script")" = "lib.sh" ] && continue
  # Toon de DESC-zin uit het script (één zin die zegt wat het garandeert),
  # met de bestandsnaam als terugval.
  desc=$(sed -n 's/^DESC="\(.*\)"$/\1/p' "$script" | head -n1)
  label="${desc:-$script}"

  out=$(BASE="$BASE" bash "$script" 2>&1)
  code=$?
  case "$code" in
    0)
      echo "  ${GREEN}PASS${RESET}  ${label}"
      PASS=$((PASS + 1)) ;;
    2)
      echo "  ${YELLOW}SKIP${RESET}  ${label}  (kon niet draaien)"
      SKIP=$((SKIP + 1))
      PROBLEM_NAMES+=("${script} — ${label}")
      PROBLEM_OUTPUT+=("$out") ;;
    *)
      echo "  ${RED}FAIL${RESET}  ${label}"
      FAIL=$((FAIL + 1))
      PROBLEM_NAMES+=("${script} — ${label}")
      PROBLEM_OUTPUT+=("$out") ;;
  esac
done

echo
echo "${BOLD}Resultaat: ${PASS} OK · ${FAIL} gefaald · ${SKIP} overgeslagen${RESET}"

if [ "${#PROBLEM_NAMES[@]}" -gt 0 ]; then
  echo
  echo "${BOLD}${RED}Te behartigen:${RESET}"
  for i in "${!PROBLEM_NAMES[@]}"; do
    echo
    echo "${RED}──── ${PROBLEM_NAMES[$i]} ────${RESET}"
    echo "${PROBLEM_OUTPUT[$i]}"
  done
fi

if [ "$FAIL" -eq 0 ] && [ "$SKIP" -eq 0 ]; then
  echo "${GREEN}${BOLD}ALLES OK ✅${RESET}"
  exit 0
fi
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
