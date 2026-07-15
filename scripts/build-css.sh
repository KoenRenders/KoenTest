#!/usr/bin/env bash
# Genereert backend/app/static/app.css uit de Jinja-templates (#396, §21).
# Nul Node (React-exit #405): gebruikt de Tailwind standalone-CLI. De binary
# wordt eenmalig gedownload naar .cache/ (staat in .gitignore).
# Draai dit na elke template-wijziging en commit de gegenereerde CSS mee.
set -euo pipefail
cd "$(dirname "$0")/.."

TW_VERSION="v3.4.17"
BIN=".cache/tailwindcss-${TW_VERSION}"
if [ ! -x "$BIN" ]; then
  mkdir -p .cache
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) ASSET="tailwindcss-linux-x64" ;;
    Linux-aarch64) ASSET="tailwindcss-linux-arm64" ;;
    Darwin-arm64) ASSET="tailwindcss-macos-arm64" ;;
    *) echo "Onbekend platform: $(uname -s)-$(uname -m)"; exit 1 ;;
  esac
  curl -sSfL -o "$BIN" \
    "https://github.com/tailwindlabs/tailwindcss/releases/download/${TW_VERSION}/${ASSET}"
  chmod +x "$BIN"
fi

TMP=$(mktemp -d)
cat > "$TMP/tailwind.config.js" << 'CFG'
module.exports = {
  content: ["backend/app/ui/templates/**/*.html",
            "backend/app/domains/**/templates/**/*.html"],
  theme: { extend: {
    colors: {
      // Ocean Blue (#0051a4) als DE merkblauw: het hele blue-palet herschaald,
      // zodat bestaande blue-*-klassen automatisch de merkkleur krijgen (700 = merk).
      blue: {50:'#edf4fc',100:'#d2e3f6',200:'#a6c7ed',300:'#79a9e2',400:'#4a86d2',
             500:'#2367bd',600:'#0f57ac',700:'#0051a4',800:'#02407c',900:'#062f59',950:'#041d38'},
      // Raak-merkpalet (stijlgids): expliciete tokens voor accenten buiten het blauw.
      brand: {DEFAULT:'#0051a4',ocean:'#0051a4',accent:'#ffce00',indigo:'#460359',
              green:'#005d29',teal:'#3aba9b',danger:'#ee3a37',warning:'#f16532',pink:'#f17fb2'},
    },
    fontFamily: { brand: ['"Radio Canada Big"','system-ui','sans-serif'] },
  } }, plugins: [],
}
CFG
# Input-CSS: merkfont zelf-gehost (@font-face) + koppen in het merkfont (@layer base).
cat > "$TMP/in.css" << 'CSS'
@font-face{font-family:"Radio Canada Big";src:url("/static/fonts/RadioCanadaBig-VariableFont_wght.ttf") format("truetype");font-weight:400 700;font-style:normal;font-display:swap}
@tailwind base;
@tailwind components;
@tailwind utilities;
@layer base{h1,h2,h3{font-family:"Radio Canada Big",system-ui,sans-serif}}
CSS
"$BIN" -c "$TMP/tailwind.config.js" -i "$TMP/in.css" \
  -o backend/app/static/app.css --minify
rm -rf "$TMP"
echo "OK: backend/app/static/app.css"
