#!/usr/bin/env bash
DESC="Platform antwoordt, en een module die er uit staat is er afwezig"
# Post-deploy smoke for the platform itself (#1530) — strictly READ-ONLY. Runs only
# when deploy.sh passes PLATFORM_BASE, the bare host that resolves to the platform.
# CR-19: a module that is off is absent, so /api/v1/activities answers 404 there;
# that is the module rule, checked on the running stack.
set -uo pipefail
source "$(dirname "$0")/../lib.sh"

[ -n "${PLATFORM_BASE:-}" ] || fatal "PLATFORM_BASE is not set"
code=$(curl -s -o /dev/null -w '%{http_code}' "${PLATFORM_BASE}/api/health" 2>/dev/null || echo 000)
expect_status 200 "$code" "platform: health-endpoint"
code=$(curl -s -o /dev/null -w '%{http_code}' "${PLATFORM_BASE}/api/v1/activities" 2>/dev/null || echo 000)
expect_status 404 "$code" "platform: activiteiten staan uit"

t_summary
