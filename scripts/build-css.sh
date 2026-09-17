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
      // Ontwerpspoor golf 0 (#913, triage A16): elke kleur-utility verwijst naar
      // een CSS-variabele (RGB-triplet, zodat de /alpha-modifier blijft werken).
      // De WAARDEN staan één keer, in de :root van in.css hieronder. Daardoor kan
      // een schil (body[data-shell]) in een latere golf zijn palet omschakelen
      // zonder dat één template verandert. Visueel verandert deze stap niets.
      blue: {50:'rgb(var(--c-blue-50) / <alpha-value>)', 100:'rgb(var(--c-blue-100) / <alpha-value>)', 200:'rgb(var(--c-blue-200) / <alpha-value>)', 300:'rgb(var(--c-blue-300) / <alpha-value>)', 400:'rgb(var(--c-blue-400) / <alpha-value>)', 500:'rgb(var(--c-blue-500) / <alpha-value>)', 600:'rgb(var(--c-blue-600) / <alpha-value>)', 700:'rgb(var(--c-blue-700) / <alpha-value>)', 800:'rgb(var(--c-blue-800) / <alpha-value>)', 900:'rgb(var(--c-blue-900) / <alpha-value>)', 950:'rgb(var(--c-blue-950) / <alpha-value>)'},
      brand: {DEFAULT:'rgb(var(--c-brand) / <alpha-value>)', 'ocean':'rgb(var(--c-brand-ocean) / <alpha-value>)', 'ocean-hover':'rgb(var(--c-brand-ocean-hover) / <alpha-value>)', 'accent':'rgb(var(--c-brand-accent) / <alpha-value>)', 'indigo':'rgb(var(--c-brand-indigo) / <alpha-value>)', 'green':'rgb(var(--c-brand-green) / <alpha-value>)', 'teal':'rgb(var(--c-brand-teal) / <alpha-value>)', 'danger':'rgb(var(--c-brand-danger) / <alpha-value>)', 'warning':'rgb(var(--c-brand-warning) / <alpha-value>)', 'pink':'rgb(var(--c-brand-pink) / <alpha-value>)'},
      link: 'rgb(var(--c-link) / <alpha-value>)',
      kop: 'rgb(var(--c-kop) / <alpha-value>)',
      ink: {DEFAULT:'rgb(var(--c-ink) / <alpha-value>)', 'soft':'rgb(var(--c-ink-soft) / <alpha-value>)'},
      line: 'rgb(var(--c-line) / <alpha-value>)', ground: 'rgb(var(--c-ground) / <alpha-value>)',
      surface: {DEFAULT:'rgb(var(--c-surface) / <alpha-value>)', 2:'rgb(var(--c-surface-2) / <alpha-value>)'},
      yellow: {50:'rgb(var(--c-yellow-50) / <alpha-value>)', 100:'rgb(var(--c-yellow-100) / <alpha-value>)', 200:'rgb(var(--c-yellow-200) / <alpha-value>)', 300:'rgb(var(--c-yellow-300) / <alpha-value>)', 400:'rgb(var(--c-yellow-400) / <alpha-value>)', 500:'rgb(var(--c-yellow-500) / <alpha-value>)', 600:'rgb(var(--c-yellow-600) / <alpha-value>)', 700:'rgb(var(--c-yellow-700) / <alpha-value>)', 800:'rgb(var(--c-yellow-800) / <alpha-value>)', 900:'rgb(var(--c-yellow-900) / <alpha-value>)', 950:'rgb(var(--c-yellow-950) / <alpha-value>)'},
    },
    // Cobalt-kaartradius (#996, Koens nabouwronde): 10px zoals de mockup's
    // --r. Eén token; de uitrol per scherm volgt met de clusters.
    borderRadius: { card: '0.625rem' },
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
  /* Ontwerpspoor golf 0 (#913): de --c-*-tripletten zijn DE ene bron van elke
     kleur; de Tailwind-utilities hierboven en de leesbare aliassen hieronder
     verwijzen ernaar. Een schil schakelt in een latere golf om door dezelfde
     namen te herdefiniëren onder body[data-shell="…"] — templates blijven
     onaangeraakt. Hex hoort ALLEEN hier thuis. */
  :root{
        --c-blue-50:237 244 252;--c-blue-100:210 227 246;--c-blue-200:166 199 237;--c-blue-300:121 169 226;--c-blue-400:74 134 210;--c-blue-500:35 103 189;--c-blue-600:15 87 172;--c-blue-700:0 81 164;--c-blue-800:2 64 124;--c-blue-900:6 47 89;--c-blue-950:4 29 56;
        --c-yellow-50:255 251 234;--c-yellow-100:255 243 196;--c-yellow-200:252 229 136;--c-yellow-300:250 219 95;--c-yellow-400:255 206 0;--c-yellow-500:224 180 0;--c-yellow-600:194 146 0;--c-yellow-700:156 117 0;--c-yellow-800:122 92 0;--c-yellow-900:92 69 0;--c-yellow-950:61 46 0;
        --c-brand:0 81 164;--c-brand-ocean:0 81 164;--c-brand-ocean-hover:2 64 124;--c-brand-accent:255 206 0;--c-brand-indigo:70 3 89;--c-brand-green:0 93 41;--c-brand-teal:58 186 155;--c-brand-danger:238 58 55;--c-brand-warning:241 101 50;--c-brand-pink:241 127 178;
        --c-ink:20 23 28;--c-ink-soft:82 96 122;
        --c-surface:255 255 255;--c-surface-2:247 250 253;
        --c-link:35 103 189;--c-line:215 224 236;--c-ground:238 243 249;
        --brand-ocean:rgb(var(--c-brand-ocean));--brand-accent:rgb(var(--c-brand-accent));--brand-indigo:rgb(var(--c-brand-indigo));--brand-green:rgb(var(--c-brand-green));--brand-teal:rgb(var(--c-brand-teal));--brand-danger:rgb(var(--c-brand-danger));--brand-warning:rgb(var(--c-brand-warning));--brand-pink:rgb(var(--c-brand-pink));
        --primary:rgb(var(--c-brand-ocean));--primary-hover:rgb(var(--c-brand-ocean-hover));--link:rgb(var(--c-link));--accent:rgb(var(--c-brand-accent));
        --ground:rgb(var(--c-ground));--surface:rgb(var(--c-surface));--surface-2:rgb(var(--c-surface-2));
        --ink:rgb(var(--c-ink));--ink-soft:rgb(var(--c-ink-soft));--line:rgb(var(--c-line));
        --brand-font:"Radio Canada Big",system-ui,sans-serif;--sans:Inter,system-ui,sans-serif}
  /* ── Ontwerpspoor golf 1 (#913): de PUBLIEKE schil in de Cobalt-richting ──
     Gekozen door Koen op de makersronde-mockups (#785, 13 september 2026):
     kobaltblauw draagt actie en selectie, koelere neutralen, zelfde
     statuskleuren (groen/geel/rood/oranje wijzigen NIET — betekenis is
     schil-onafhankelijk). Alleen waarden: geen template weet hiervan.
     Golf 2 trok de beheerschil bij in hetzelfde blok — beide schillen dragen
     nu Cobalt; het per-schil-mechanisme blijft staan voor de dag dat ze weer
     uiteen willen. */
  body[data-shell="site"],body[data-shell="admin"]{
        --c-blue-50:234 240 255;--c-blue-100:220 230 253;--c-blue-200:189 207 250;--c-blue-300:150 175 244;--c-blue-400:100 136 234;--c-blue-500:61 99 218;--c-blue-600:44 83 206;--c-blue-700:36 75 197;--c-blue-800:29 60 158;--c-blue-900:23 46 119;--c-blue-950:15 29 75;
        --c-brand:36 75 197;--c-brand-ocean:36 75 197;--c-brand-ocean-hover:29 60 158;
        --c-link:36 75 197;
        --c-ink:25 38 56;--c-ink-soft:83 97 116;
        --c-line:210 217 227;--c-ground:244 246 250;--c-surface-2:239 243 250}
  /* Kopkleur per schil (golf 8-feedbackronde 3, 15 sep 2026): het beheer volgt
     de Cobalt-mockup — koppen in ink, blauw is voor acties/links/selectie. De
     publieke schil houdt de merkblauwe koppen tot de golf 10-tokenronde die
     kant expliciet langsgaat. Templates schrijven text-kop en weten van geen
     schil. */
  body[data-shell="site"]{--c-kop:36 75 197}
  body[data-shell="admin"]{--c-kop:25 38 56}
  html{font-family:Inter,system-ui,sans-serif}
  /* Koppen in Inter (golf 1 variant B, door Koen gekozen op het
     goedkeuringspakket; golf 2 trok de beheerschil bij — één typografie,
     zoals de Cobalt-richting). Het woordmerk draagt Radio Canada Big via de
     font-brand-klasse; dat is identiteit, geen kop. */
  h1,h2,h3{font-family:Inter,system-ui,sans-serif}
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
  html :where(input[type="text"],input[type="email"],input[type="tel"],input[type="number"],input[type="password"],input[type="search"],input[type="url"],input[type="date"],input[type="time"],input[type="datetime-local"],input:not([type]),select,textarea):focus{border-color:var(--brand-ocean);box-shadow:0 0 0 3px rgb(var(--c-brand-ocean)/.15);outline:none}
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
