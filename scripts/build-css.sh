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
      brand: {DEFAULT:'#0051a4',ocean:'#0051a4','ocean-hover':'#02407c',accent:'#ffce00',
              indigo:'#460359',green:'#005d29',teal:'#3aba9b',danger:'#ee3a37',
              warning:'#f16532',pink:'#f17fb2'},
      // Tekst-/prose-links: een fellere merk-tint (= blue-500 #2367bd) zodat links
      // onderscheidend "poppen" naast het diepe merkblauw van koppen/chrome (#0051a4).
      // On-brand (afgeleid van de ocean-tint), niet het generieke Tailwind-linkblauw.
      link: '#2367bd',
      // Neutralen & oppervlakken (design-system §1.1) als utility-kleuren, zodat
      // text-ink-soft / border-line / bg-surface-2 bestaan i.p.v. gray-* te gokken.
      ink: {DEFAULT:'#14171c',soft:'#52607a'},
      line: '#d7e0ec', ground: '#eef3f9',
      surface: {DEFAULT:'#ffffff','2':'#f7fafd'},
      // Geel = "wachtend" (#528 as A). Het amber-palet vervalt: één gele schaal,
      // herschaald rond het merkaccent (400 = #ffce00), zodat yellow-* de token
      // IS — dezelfde truc als bij blue-700 = merkblauw.
      yellow: {50:'#fffbea',100:'#fff3c4',200:'#fce588',300:'#fadb5f',400:'#ffce00',
               500:'#e0b400',600:'#c29200',700:'#9c7500',800:'#7a5c00',900:'#5c4500',950:'#3d2e00'},
    },
    fontFamily: { brand: ['"Radio Canada Big"','system-ui','sans-serif'],
                  sans: ['Inter','system-ui','sans-serif'] },
  } }, plugins: [],
}
CFG
# Input-CSS: merkfont zelf-gehost (@font-face) + koppen in het merkfont (@layer base).
cat > "$TMP/in.css" << 'CSS'
@font-face{font-family:"Radio Canada Big";src:url("/static/fonts/RadioCanadaBig-VariableFont_wght.ttf") format("truetype");font-weight:400 700;font-style:normal;font-display:swap}
/* Inter als body-font, zelf-gehost (#528 as B). Bewust GEEN fonts.googleapis.com:
   een externe font-CDN ziet het IP van elke bezoeker — Europe-First/GDPR. woff2
   eerst, ttf als terugval voor oude browsers; font-display:swap zodat tekst
   meteen leesbaar is. */
@font-face{font-family:"Inter";src:url("/static/fonts/Inter-Regular.woff2") format("woff2"),url("/static/fonts/Inter-Regular.ttf") format("truetype");font-weight:400;font-style:normal;font-display:swap}
@font-face{font-family:"Inter";src:url("/static/fonts/Inter-Medium.woff2") format("woff2"),url("/static/fonts/Inter-Medium.ttf") format("truetype");font-weight:500;font-style:normal;font-display:swap}
@font-face{font-family:"Inter";src:url("/static/fonts/Inter-SemiBold.woff2") format("woff2"),url("/static/fonts/Inter-SemiBold.ttf") format("truetype");font-weight:600;font-style:normal;font-display:swap}
@font-face{font-family:"Inter";src:url("/static/fonts/Inter-Bold.woff2") format("woff2"),url("/static/fonts/Inter-Bold.ttf") format("truetype");font-weight:700;font-style:normal;font-display:swap}
@tailwind base;
@tailwind components;
@tailwind utilities;
@layer base{
  /* Merkkleuren als CSS-variabelen (#486): ÉÉN bron voor plekken met rauwe CSS
     (bv. de CMS-content-opmaak) i.p.v. hardgecodeerde hexes — zo blijft de
     merkkleur automatisch consistent en verandert een tint op één plek. */
  :root{--brand-ocean:#0051a4;--brand-accent:#ffce00;--brand-indigo:#460359;--brand-green:#005d29;--brand-teal:#3aba9b;--brand-danger:#ee3a37;--brand-warning:#f16532;--brand-pink:#f17fb2;
        /* Design-system-tokens (docs/design-system.html §1.1): dit zijn de namen
           waar rauwe CSS naar verwijst. Hex hoort ALLEEN hier thuis. */
        --primary:#0051a4;--primary-hover:#02407c;--link:#2367bd;--accent:#ffce00;
        --ground:#eef3f9;--surface:#ffffff;--surface-2:#f7fafd;
        --ink:#14171c;--ink-soft:#52607a;--line:#d7e0ec;
        --brand-font:"Radio Canada Big",system-ui,sans-serif;--sans:Inter,system-ui,sans-serif}
  html{font-family:Inter,system-ui,sans-serif}
  h1,h2,h3{font-family:"Radio Canada Big",system-ui,sans-serif}
  /* Automatische consistentie (#482): elk tekst-input/select/textarea krijgt
     standaard dezelfde stijl — geen macro of losse klassen nodig. Checkboxes,
     radios, files en knoppen blijven ongemoeid.

     De `html `-prefix is essentieel (#614). Met enkel `:where(...)` staat de regel
     op specificiteit 0,0,0 en verliest ze van Tailwinds preflight
     (`button,input,optgroup,select,textarea{padding:0;font-size:100%}`, 0,0,1):
     rand en radius kwamen door, padding en font-size niet. Dat gaf controls met
     een kader maar zonder hoogte — de scheve filterbalken van #611.

     `html :where(...)` tilt de regel naar 0,0,1: gelijk aan preflight, en omdat ze
     ná preflight in app.css staat wint ze. Utilities blijven winnen (`.px-2` is
     0,1,0), dus de oorspronkelijke bedoeling blijft overeind. Een kale selector
     zónder `:where()` zou dat wél breken: `input[type="text"]` is 0,1,1 en zou
     `.px-2` verslaan. */
  html :where(input[type="text"],input[type="email"],input[type="tel"],input[type="number"],input[type="password"],input[type="search"],input[type="url"],input[type="date"],input[type="time"],input[type="datetime-local"],input:not([type]),select,textarea){border:1px solid #d1d5db;border-radius:.5rem;padding:.5rem .75rem;font-size:.875rem;line-height:1.25rem;background-color:#fff;color:#111827}
  /* Expliciete hoogte (#677). Gelijke padding en lettergrootte volstaan NIET: een
     <select> krijgt van de browser intrinsieke ruimte voor zijn pijltje en een
     eigen minimumhoogte, een <input> niet. Enkele pixels verschil, en omdat de
     compacte vormen `items-end` gebruiken zakt het LABEL boven de kortere kolom
     mee — zelfde zichtbare fout als #656, andere oorzaak.

     2.375rem = 1.25rem regelhoogte + 2 × .5rem padding + 2 × 1px rand. Hier en
     nergens anders: de maatvoering van een control staat in deze base-layer, niet
     óók in `_control_base`, zodat er geen twee bronnen zijn die elkaar bevechten.

     `date`/`time` staan er expliciet bij: die dragen in elke browser hun eigen
     intrinsieke maat en staan op het activiteitdetail naast gewone tekstvelden.

     Een <textarea> hoort er NIET bij — die groeit met `rows` en moet dat kunnen. */
  html :where(input[type="text"],input[type="email"],input[type="tel"],input[type="number"],input[type="password"],input[type="search"],input[type="url"],input[type="date"],input[type="time"],input[type="datetime-local"],input:not([type]),select){height:2.375rem}
  html :where(input[type="text"],input[type="email"],input[type="tel"],input[type="number"],input[type="password"],input[type="search"],input[type="url"],input[type="date"],input[type="time"],input[type="datetime-local"],input:not([type]),select,textarea):focus{border-color:var(--brand-ocean);box-shadow:0 0 0 3px rgba(0,81,164,.15);outline:none}
}
/* ── Wacht- en overgangsfeedback voor htmx (#634) ────────────────────────────
   BEWUST buiten @layer components: Tailwind snoeit de components-laag op wat het
   in de templates terugvindt, en deze klassen zet htmx pas tijdens de request op
   het element (`htmx-request`, `htmx-settling`) of wij vanuit JS op de <body>
   (`htmx-loading`). In een laag zouden ze dus stilzwijgend wegvallen. Gewone CSS
   ná @tailwind utilities is hier ook inhoudelijk juist: `pointer-events:none`
   tijdens een verzoek hoort een utility te overrulen. */
/* Elk element dat zelf een htmx-verzoek stuurt (knop of formulier) dimt en is
   onklikbaar zolang het loopt — dekt alle bestaande hx-post-acties in één regel. */
.htmx-request{opacity:.6;cursor:wait}
.htmx-request,.htmx-request *{pointer-events:none}
/* Ingeswapte fragmenten faden in i.p.v. te knipperen. */
.htmx-settling{animation:raak-fade-in 150ms ease-out}
@keyframes raak-fade-in{from{opacity:0}to{opacity:1}}
/* Voortgangsbalk bovenaan (ui.htmx_ux()): 2px in de merkkleur, boven de sticky
   omgevingsbanner. `width` loopt tijdens de request naar 80% en verdwijnt erna. */
#nprogress{position:fixed;top:0;left:0;height:2px;width:0;background:var(--brand-ocean);z-index:70;opacity:0;transition:width .3s ease-out,opacity .2s ease-out;pointer-events:none}
body.htmx-loading #nprogress{width:80%;opacity:1}
/* View Transitions bij gebooste navigatie: kort, anders voelt het traag. */
@view-transition{navigation:auto}
::view-transition-old(root),::view-transition-new(root){animation-duration:120ms}
/* Design-system §5 (Motion): wie bewegingsreductie heeft ingesteld, krijgt de
   feedback zonder animatie — de balk en de dimming blijven, het bewegen niet. */
@media (prefers-reduced-motion: reduce){
  .htmx-settling{animation:none}
  #nprogress{transition:none}
  ::view-transition-old(root),::view-transition-new(root){animation:none}
}
CSS
"$BIN" -c "$TMP/tailwind.config.js" -i "$TMP/in.css" \
  -o backend/app/static/app.css --minify
rm -rf "$TMP"
echo "OK: backend/app/static/app.css"
