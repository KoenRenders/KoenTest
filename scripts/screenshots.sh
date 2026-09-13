#!/usr/bin/env bash
# Reproducible screenshot set for the design track (#785 step 0).
#
# Runs tests_e2e/screenshots.py against a live, SEEDED local backend:
#
#   sudo docker compose -f docker-compose.dev.yml --env-file .env.dev up -d
#   ... exec backend python seed_e2e.py        # once per fresh DB
#   ./scripts/screenshots.sh [outdir]          # default: ./screenshots
#
# Needs playwright-python + chromium on the host (pip install playwright &&
# playwright install chromium), or E2E_CHROMIUM_PATH pointing at a browser.
# E2E_BASE_URL overrides the default http://localhost:8000.
# Seed data only — never point this at UAT or PROD.
set -euo pipefail

cd "$(dirname "$0")/../backend"
exec python -m tests_e2e.screenshots "${1:-../screenshots}"
