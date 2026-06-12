# tests/lib.sh — gedeelde helpers voor uniforme, beknopte testuitvoer.
#
# Principe: STIL bij succes, GERICHT bij falen. Een geslaagde test toont enkel
# "N checks OK"; een gefaalde toont precies welke check faalde en waarom.
#
# Source dit bovenaan een testscript:
#   source "$(dirname "$0")/../lib.sh"
#
# Exit-codes die testscripts teruggeven via t_summary:
#   0 = alles OK   1 = minstens één check faalde   2 = kon niet draaien (setup)

RED=$'\e[31m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; BOLD=$'\e[1m'; RESET=$'\e[0m'
# Geen kleurcodes als de uitvoer niet naar een terminal gaat (bv. logbestand).
[ -t 1 ] || { RED=""; GREEN=""; YELLOW=""; BOLD=""; RESET=""; }

BASE="${BASE:-http://localhost:8081}"
_PASS=0
_FAIL=0

# expect_status VERWACHT ACTUEEL OMSCHRIJVING
expect_status() {
  if [ "$1" = "$2" ]; then
    _PASS=$((_PASS + 1))
  else
    _FAIL=$((_FAIL + 1))
    echo "  ${RED}✗${RESET} $3 — verwacht status $1, kreeg $2"
  fi
}

# expect_status_one_of ACTUEEL OMSCHRIJVING VERWACHT...
expect_status_one_of() {
  local actual="$1" desc="$2"; shift 2
  local e
  for e in "$@"; do
    [ "$e" = "$actual" ] && { _PASS=$((_PASS + 1)); return; }
  done
  _FAIL=$((_FAIL + 1))
  echo "  ${RED}✗${RESET} $desc — verwacht één van [$*], kreeg $actual"
}

# expect_contains BESTAND NAALD OMSCHRIJVING
expect_contains() {
  if grep -q "$2" "$1" 2>/dev/null; then
    _PASS=$((_PASS + 1))
  else
    _FAIL=$((_FAIL + 1))
    echo "  ${RED}✗${RESET} $3 — '$2' niet gevonden in respons"
  fi
}

# expect_true WAARDE OMSCHRIJVING   (WAARDE "1" = waar)
expect_true() {
  if [ "$1" = "1" ]; then
    _PASS=$((_PASS + 1))
  else
    _FAIL=$((_FAIL + 1))
    echo "  ${RED}✗${RESET} $2"
  fi
}

# fatal OMSCHRIJVING — onmiddellijke stop, test kon niet draaien (exit 2).
fatal() { echo "  ${RED}✗ setup: $1${RESET}"; exit 2; }

# t_summary — beknopte slotregel + juiste exit-code.
t_summary() {
  if [ "$_FAIL" -eq 0 ]; then
    echo "  ${GREEN}${_PASS} checks OK${RESET}"
    exit 0
  fi
  echo "  ${RED}${_FAIL}/$((_PASS + _FAIL)) checks gefaald${RESET}"
  exit 1
}

# discover_product — zoekt een activiteit met minstens één product.
# Echoot "ACT_ID COMP_ID PROD_ID" of niets. Vereist jq.
discover_product() {
  curl -fsS "${BASE}/api/v1/activities" 2>/dev/null | jq -r '
    [ .[] as $a | $a.sub_registrations[]? as $c | $c.products[]? as $p
      | "\($a.id) \($c.id) \($p.id)" ] | first // empty'
}
