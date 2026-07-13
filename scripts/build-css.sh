#!/usr/bin/env bash
# Genereert backend/app/static/app.css uit de Jinja-templates (#396, §21).
# Interim (hybride periode): draait via npx; bij de React-exit (#405) verhuist
# dit naar de Tailwind standalone-CLI in de backend-Dockerfile (nul Node).
# Draai dit na elke template-wijziging en commit de gegenereerde CSS mee.
set -euo pipefail
cd "$(dirname "$0")/.."
TMP=$(mktemp -d)
cat > "$TMP/tailwind.config.js" << 'CFG'
module.exports = {
  content: ["backend/app/ui/templates/**/*.html",
            "backend/app/domains/**/templates/**/*.html"],
  theme: { extend: {} }, plugins: [],
}
CFG
echo '@tailwind base; @tailwind components; @tailwind utilities;' > "$TMP/in.css"
(cd frontend && npx tailwindcss@3.4.17 -c "$TMP/tailwind.config.js" -i "$TMP/in.css" \
  -o ../backend/app/static/app.css --minify)
rm -rf "$TMP"
echo "OK: backend/app/static/app.css"
