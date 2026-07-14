#!/usr/bin/env bash
# Taalcatalogus (#407-T): extract -> update -> compile. Draai na het toevoegen
# of wijzigen van _()-strings en commit de .po/.mo mee.
set -euo pipefail
cd "$(dirname "$0")/../backend"
pybabel extract -F babel.cfg -o app/locales/messages.pot --project "Raak" .
for loc in nl_BE; do
  if [ -f "app/locales/$loc/LC_MESSAGES/messages.po" ]; then
    pybabel update -i app/locales/messages.pot -d app/locales -l "$loc"
  else
    pybabel init -i app/locales/messages.pot -d app/locales -l "$loc"
  fi
done
pybabel compile -d app/locales
echo "OK: catalogus geëxtraheerd en gecompileerd"
