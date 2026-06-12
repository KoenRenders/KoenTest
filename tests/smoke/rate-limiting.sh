#!/usr/bin/env bash
DESC="Login blokkeert na te veel pogingen per minuut (429)"
# Rate limiting op de login (request-login). Niet via de GUI te testen.
#
# De login-limiter staat op 5 pogingen per minuut per IP. We sturen tot 11
# pogingen met een ONBEKEND e-mailadres — dat heeft geen neveneffecten (een
# onbekende gebruiker krijgt geen mail, geen token) — en verwachten dat er
# na de limiet een 429 volgt.
set -uo pipefail
source "$(dirname "$0")/../lib.sh"

saw_429=0
attempts=0
for _ in $(seq 1 11); do
  attempts=$((attempts + 1))
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST \
    "${BASE}/api/v1/auth/request-login" \
    -H 'Content-Type: application/json' \
    -d '{"email":"ratelimit-test@example.com"}')
  if [ "$code" = "429" ]; then
    saw_429=1
    break
  fi
done

expect_true "$saw_429" "login-limiter geeft 429 (na ${attempts} pogingen binnen 1 min)"

t_summary
