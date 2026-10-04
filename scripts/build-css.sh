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
      gray: {50:'rgb(var(--c-gray-50) / <alpha-value>)', 100:'rgb(var(--c-gray-100) / <alpha-value>)', 200:'rgb(var(--c-gray-200) / <alpha-value>)', 300:'rgb(var(--c-gray-300) / <alpha-value>)', 400:'rgb(var(--c-gray-400) / <alpha-value>)', 500:'rgb(var(--c-gray-500) / <alpha-value>)', 600:'rgb(var(--c-gray-600) / <alpha-value>)', 700:'rgb(var(--c-gray-700) / <alpha-value>)', 800:'rgb(var(--c-gray-800) / <alpha-value>)', 900:'rgb(var(--c-gray-900) / <alpha-value>)', 950:'rgb(var(--c-gray-950) / <alpha-value>)'},
      red: {50:'rgb(var(--c-red-50) / <alpha-value>)', 100:'rgb(var(--c-red-100) / <alpha-value>)', 200:'rgb(var(--c-red-200) / <alpha-value>)', 300:'rgb(var(--c-red-300) / <alpha-value>)', 400:'rgb(var(--c-red-400) / <alpha-value>)', 500:'rgb(var(--c-red-500) / <alpha-value>)', 600:'rgb(var(--c-red-600) / <alpha-value>)', 700:'rgb(var(--c-red-700) / <alpha-value>)', 800:'rgb(var(--c-red-800) / <alpha-value>)', 900:'rgb(var(--c-red-900) / <alpha-value>)', 950:'rgb(var(--c-red-950) / <alpha-value>)'},
      green: {50:'rgb(var(--c-green-50) / <alpha-value>)', 100:'rgb(var(--c-green-100) / <alpha-value>)', 200:'rgb(var(--c-green-200) / <alpha-value>)', 300:'rgb(var(--c-green-300) / <alpha-value>)', 400:'rgb(var(--c-green-400) / <alpha-value>)', 500:'rgb(var(--c-green-500) / <alpha-value>)', 600:'rgb(var(--c-green-600) / <alpha-value>)', 700:'rgb(var(--c-green-700) / <alpha-value>)', 800:'rgb(var(--c-green-800) / <alpha-value>)', 900:'rgb(var(--c-green-900) / <alpha-value>)', 950:'rgb(var(--c-green-950) / <alpha-value>)'},
      orange: {50:'rgb(var(--c-orange-50) / <alpha-value>)', 100:'rgb(var(--c-orange-100) / <alpha-value>)', 200:'rgb(var(--c-orange-200) / <alpha-value>)', 300:'rgb(var(--c-orange-300) / <alpha-value>)', 400:'rgb(var(--c-orange-400) / <alpha-value>)', 500:'rgb(var(--c-orange-500) / <alpha-value>)', 600:'rgb(var(--c-orange-600) / <alpha-value>)', 700:'rgb(var(--c-orange-700) / <alpha-value>)', 800:'rgb(var(--c-orange-800) / <alpha-value>)', 900:'rgb(var(--c-orange-900) / <alpha-value>)', 950:'rgb(var(--c-orange-950) / <alpha-value>)'},
      'control-line': 'rgb(var(--c-control-line) / <alpha-value>)', focus: 'rgb(var(--c-focus) / <alpha-value>)',
      nav: {DEFAULT:'rgb(var(--c-nav) / <alpha-value>)', 'ink':'rgb(var(--c-nav-ink) / <alpha-value>)', 'soft':'rgb(var(--c-nav-soft) / <alpha-value>)', 'hover':'rgb(var(--c-nav-hover) / <alpha-value>)', 'active':'rgb(var(--c-nav-active) / <alpha-value>)', 'active-ink':'rgb(var(--c-nav-active-ink) / <alpha-value>)', 'active-line':'rgb(var(--c-nav-active-line) / <alpha-value>)'},
      yellow: {50:'rgb(var(--c-yellow-50) / <alpha-value>)', 100:'rgb(var(--c-yellow-100) / <alpha-value>)', 200:'rgb(var(--c-yellow-200) / <alpha-value>)', 300:'rgb(var(--c-yellow-300) / <alpha-value>)', 400:'rgb(var(--c-yellow-400) / <alpha-value>)', 500:'rgb(var(--c-yellow-500) / <alpha-value>)', 600:'rgb(var(--c-yellow-600) / <alpha-value>)', 700:'rgb(var(--c-yellow-700) / <alpha-value>)', 800:'rgb(var(--c-yellow-800) / <alpha-value>)', 900:'rgb(var(--c-yellow-900) / <alpha-value>)', 950:'rgb(var(--c-yellow-950) / <alpha-value>)'},
    },
    // Cobalt-kaartradius (#996, Koens nabouwronde): 10px zoals de mockup's
    // --r. Eén token; de uitrol per scherm volgt met de clusters.
    // CR-11 block 1 (#1482): lg/xl/2xl are tokens too, Tailwind's values in
    // :root and the admin's (controls 6 px, cards 10 px) under its shell.
    borderRadius: { card: '0.625rem', lg: 'var(--r-lg)', xl: 'var(--r-xl)', '2xl': 'var(--r-2xl)' },
    // #1482: the brand face is a token, so the admin shell can be Inter only.
    fontFamily: { brand: ['var(--font-brand)'],
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
        --brand-font:"Radio Canada Big",system-ui,sans-serif;--sans:Inter,system-ui,sans-serif;
        /* CR-11 block 1 (#1482): Tailwind's own scales, radii and the brand face as
           tokens. These are Tailwind's values: outside the admin shell nothing renders
           differently. The admin shell redefines them below. */
        --c-gray-50:249 250 251;--c-gray-100:243 244 246;--c-gray-200:229 231 235;--c-gray-300:209 213 219;--c-gray-400:156 163 175;--c-gray-500:107 114 128;--c-gray-600:75 85 99;--c-gray-700:55 65 81;--c-gray-800:31 41 55;--c-gray-900:17 24 39;--c-gray-950:3 7 18;
        --c-red-50:254 242 242;--c-red-100:254 226 226;--c-red-200:254 202 202;--c-red-300:252 165 165;--c-red-400:248 113 113;--c-red-500:239 68 68;--c-red-600:220 38 38;--c-red-700:185 28 28;--c-red-800:153 27 27;--c-red-900:127 29 29;--c-red-950:69 10 10;
        --c-green-50:240 253 244;--c-green-100:220 252 231;--c-green-200:187 247 208;--c-green-300:134 239 172;--c-green-400:74 222 128;--c-green-500:34 197 94;--c-green-600:22 163 74;--c-green-700:21 128 61;--c-green-800:22 101 52;--c-green-900:20 83 45;--c-green-950:5 46 22;
        --c-orange-50:255 247 237;--c-orange-100:255 237 213;--c-orange-200:254 215 170;--c-orange-300:253 186 116;--c-orange-400:251 146 60;--c-orange-500:249 115 22;--c-orange-600:234 88 12;--c-orange-700:194 65 12;--c-orange-800:154 52 18;--c-orange-900:124 45 18;--c-orange-950:67 20 7;
        --c-control-line:209 213 219;--c-focus:59 130 246;
        --r-lg:.5rem;--r-xl:.75rem;--r-2xl:1rem;
        --font-brand:"Radio Canada Big",system-ui,sans-serif}
  /* ── Ontwerpspoor golf 1 (#913): de PUBLIEKE schil in de Cobalt-richting ──
     Gekozen door Koen op de makersronde-mockups (#785, 13 september 2026):
     kobaltblauw draagt actie en selectie, koelere neutralen, zelfde
     statuskleuren (groen/geel/rood/oranje wijzigen NIET — betekenis is
     schil-onafhankelijk). Alleen waarden: geen template weet hiervan.
     Golf 2 trok de beheerschil bij in hetzelfde blok — beide schillen dragen
     nu Cobalt; het per-schil-mechanisme blijft staan voor de dag dat ze weer
     uiteen willen. Die dag kwam met CR-11 block 1 (#1482): the admin shell has
     its own block below, and this one is the site's alone. */
  body[data-shell="site"]{
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
  /* ── CR-11 block 1 (#1482): the admin shell in palette Atelier ─────────────
     Decided by Koen on 2 October 2026; the norm is design-system-end-state.md
     §1.1, §1.2, §1.6. The brand blue 37 78 115 carries action and selection, the
     neutrals are cool greys, and the house style's eight colours are no longer
     the admin's palette. Warning is a real orange, 194 65 12 (block 3). Tailwind's
     scales the templates already use are redefined here, so not one template
     changes: blue around the brand, gray as the Atelier neutrals, red as danger,
     green as success, orange 600–800 as warning. Radius: controls 6 px, cards
     10 px; the face is Inter alone (Radio Canada Big leaves the admin). */
  body[data-shell="admin"]{
        --c-blue-50:230 239 247;--c-blue-100:210 224 236;--c-blue-200:156 184 210;--c-blue-300:118 152 182;--c-blue-400:72 116 154;--c-blue-500:25 95 157;--c-blue-600:31 70 110;--c-blue-700:37 78 115;--c-blue-800:25 57 88;--c-blue-900:20 45 70;--c-blue-950:12 28 45;
        --c-brand:37 78 115;--c-brand-ocean:37 78 115;--c-brand-ocean-hover:25 57 88;--c-brand-danger:166 37 37;--c-brand-warning:194 65 12;
        --c-link:37 78 115;--c-kop:33 45 58;
        --c-ink:33 45 58;--c-ink-soft:83 99 115;
        --c-line:216 224 230;--c-ground:244 246 248;--c-surface:255 255 255;--c-surface-2:240 243 246;
        --c-control-line:126 143 158;--c-focus:25 95 157;
        --c-nav:255 255 255;--c-nav-ink:50 66 81;--c-nav-soft:92 106 118;--c-nav-hover:240 244 247;--c-nav-active:230 239 247;--c-nav-active-ink:29 65 98;--c-nav-active-line:210 224 236;
        --c-gray-50:244 246 248;--c-gray-100:240 243 246;--c-gray-200:216 224 230;--c-gray-300:190 201 210;--c-gray-400:126 143 158;--c-gray-500:83 99 115;--c-gray-600:83 99 115;--c-gray-700:50 66 81;--c-gray-800:33 45 58;--c-gray-900:33 45 58;--c-gray-950:20 28 36;
        --c-red-50:251 236 236;--c-red-100:248 222 222;--c-red-200:238 190 190;--c-red-300:222 150 150;--c-red-400:200 90 90;--c-red-500:184 52 52;--c-red-600:166 37 37;--c-red-700:146 31 31;--c-red-800:125 26 26;--c-red-900:100 21 21;--c-red-950:60 12 12;
        --c-green-50:226 243 231;--c-green-100:214 237 222;--c-green-200:180 222 196;--c-green-300:130 196 158;--c-green-400:70 160 118;--c-green-500:40 130 92;--c-green-600:30 115 80;--c-green-700:24 103 72;--c-green-800:24 103 72;--c-green-900:18 78 55;--c-green-950:10 45 32;
        --c-orange-100:255 237 213;--c-orange-600:194 65 12;--c-orange-700:194 65 12;--c-orange-800:194 65 12;
        /* Yellow is the admin's warning tone (the `yellow` badge: Openstaand,
           Terug te betalen, a draft, a blocked answer) and the accent is not used
           in the admin at all (§1.1), so its scale is the warning orange here. */
        --c-yellow-50:255 247 237;--c-yellow-100:255 237 213;--c-yellow-200:254 215 170;--c-yellow-300:253 186 116;--c-yellow-400:251 146 60;--c-yellow-500:234 88 12;--c-yellow-600:194 65 12;--c-yellow-700:194 65 12;--c-yellow-800:194 65 12;--c-yellow-900:154 52 18;--c-yellow-950:67 20 7;
        --r-lg:6px;--r-xl:10px;--r-2xl:10px;
        --font-brand:Inter,system-ui,sans-serif}
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
  html :where(input[type="text"],input[type="email"],input[type="tel"],input[type="number"],input[type="password"],input[type="search"],input[type="url"],input[type="date"],input[type="time"],input[type="datetime-local"],input:not([type]),select,textarea){border:1px solid rgb(var(--c-control-line));border-radius:var(--r-lg);padding:.5rem .75rem;font-size:.875rem;line-height:1.25rem;background-color:#fff;color:#111827}
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
/* ── De teller verbergt de ingebouwde pijltjes (#1200, punt 2) ──────────────
   `ui.stepper` bestaat omdat iOS Safari bij een `type="number"` NOOIT pijltjes
   toont; op een desktopbrowser staan ze er wél, en dan zijn er twee bedieningen
   voor hetzelfde ding — zichtbaar op Koens HDEV-afdrukken, binnen het getalveld.

   Hier en niet als utility: een pseudo-element is in Tailwind niet uit te
   drukken. Buiten @layer om dezelfde reden als de htmx-klassen hierboven — de
   components-laag wordt gesnoeid op wat er in de templates staat, en een
   pseudo-element-regel zou daar stil wegvallen.

   BEWUST op `.teller-veld` en niet op `input[type=number]`: de focuspunten van de
   Design Studio stappen met 0,05 en het nieuwsbriefplafond met 1 — daar zijn die
   pijltjes juist nuttig. Eén scherm repareren mag de andere niet uitkleden. */
.teller-veld::-webkit-inner-spin-button,
.teller-veld::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}
.teller-veld{-moz-appearance:textfield;appearance:textfield}
/* ── Tile strip: a label is one line (#1426, #1432) ──────────────────────────
   Activities, Payments and Members each write a strip of tiles — a label, a
   number, sometimes a foot line. A label that broke over two lines pushed its
   number below its neighbours' (#1426); a subgrid of the strip's rows lined
   the numbers up but made every short label's tile as tall as the long one,
   its number far under the text (Koen, 1 October 2026, #1432). So a label is
   ONE line: too long, it ends in "…" and the screen gives it a `title` with the
   whole text. Every label one line tall puts every number at the same height,
   right under its label, as before #1426. One rule for the three strips.
   The label may shrink in the phone's row too (`min-width:0`), the number never
   does; and a tile does not grow to fit its label (`min-width:0` on the tile),
   so the tiles of a strip stay as wide as each other, as before #1426.
   Outside @layer so Tailwind does not prune it. */
.kpi-strip>*{min-width:0}
.kpi-strip>*>:first-child{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.kpi-strip>*>:nth-child(2){flex-shrink:0}
/* ── CR-11 block 1 (#1482): the admin frame ─────────────────────────────────
   design-system-end-state §1.4. The sidebar is fixed and the frame beside it
   keeps its distance with `--nav-current`: 224 px, 64 px as a rail (the class
   `nav-rail` on <html>, set by `raakNav` in admin_base.html from the width and
   the user's choice), 0 below 768 px, where the same element is a drawer
   (`is-open`). In the rail the labels go and the label is the tooltip; a
   group's heading becomes a thin line. Outside @layer: these classes are set
   by script and state, and Tailwind would prune them. No value here that is
   not a token or a size of the norm. */
body[data-shell="admin"]{--nav-current:224px}
html.nav-rail body[data-shell="admin"]{--nav-current:64px}
.admin-sidebar{position:fixed;bottom:0;left:0;z-index:30;width:var(--nav-current);display:flex;flex-direction:column;background:rgb(var(--c-nav));border-right:1px solid rgb(var(--c-line));color:rgb(var(--c-nav-ink));overflow:hidden}
.admin-frame{margin-left:var(--nav-current);min-width:0}
.admin-content:has([data-list-page]){max-width:none}
/* CR-11 block 6 (#1558), design-system-end-state §1.4, §3.2. A record page
   (it carries the record head) takes the frame like a list page; inside it the reading group is 768 + 24 +
   300 px, left-aligned; the summary stands beside the form while the form keeps
   640 px (964 px of frame), else above it. The form grid has four tracks, 12 px apart; it goes to
   one column when the section is narrower than 532 px inside (two half fields
   of 260 px and their gap) — a container query, which a utility cannot say.
   32 px between the sections of a form column. */
.admin-content:has([data-record-head]){max-width:none}
.record-frame{container-type:inline-size}
.record-columns{display:grid;grid-template-columns:minmax(0,768px);gap:24px;align-items:start}
.record-form-column{min-width:0}
.form-flow{display:grid;gap:32px;min-width:0}
.record-summary-column{min-width:0;order:-1}
@container (min-width:964px){.record-columns:has(>.record-summary-column){grid-template-columns:minmax(0,768px) 300px}.record-summary-column{order:0}}
.form-section{container-type:inline-size;min-width:0}
.form-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;align-items:start}
.form-grid>[data-span="full"]{grid-column:1/-1}
.form-grid>[data-span="half"]{grid-column:span 2}
.form-grid>[data-span="quarter"]{grid-column:span 1}
@container (max-width:531.98px){.form-grid>[data-span]{grid-column:1/-1}}
/* ── CR-11 block 4 (#1556): the list's table ────────────────────────────────
   design-system-end-state §2.1 (the list, the row as the way in). What the
   utility classes cannot say: the row's click area, and what the table does
   by the width of the LIST (a container query) instead of the window — a list
   beside an open panel is narrower than its window. Outside @layer, like the
   frame above: the selectors are data attributes the kit's macros write.

   - The row is the way in: the link in the first cell (`data-row-link`) lays
     its click area over the whole row; what must stay clickable itself — a
     reference, the row's one action, its menu — sits above it
     (`data-above-row`). No nested anchors.
   - Optional columns leave by list width in a fixed order: priority 1 below
     1 100 px, priority 2 below 980 px (`data-p` on the cells). The prototype
     of brief 04 put them at 1 240 and 1 120; the issue asks seven columns on a
     1 440 px window, where the list is 1 168 px wide, so both moved down. The table says
     per priority whether that is automatic, always shown or always hidden
     (`data-p1`, `data-p2`: auto | show | hide) — the column chooser.
   - `table-layout:fixed`: the columns take the widths the screen gives them
     and the first one the rest, so a column the chooser forces to show on a
     narrow list makes the others tighter — never the page wider (measured:
     with an automatic layout, "Tonen" at 988 px gave a page of 1 182 px).
   - Below 900 px the table is one continuous list of stacked rows, no cards:
     name and reference, the context, then the badge and the amount on one
     line, the row's action and `⋯` at the top right. The head stays for a
     screen reader. Never a horizontal scroll. */
.data-table-frame{container-type:inline-size;container-name:datatable}
.data-table{width:100%;border-collapse:separate;border-spacing:0;table-layout:fixed}
.data-table th,.data-table td{overflow-wrap:anywhere}
.data-table [data-row]{position:relative}
.data-table [data-row]:hover{background:rgb(var(--c-surface-2))}
.data-table [data-row-link]::after{content:"";position:absolute;inset:0;z-index:1;cursor:pointer}
.data-table [data-row-link]:focus-visible{outline:none}
.data-table [data-row-link]:focus-visible::after{outline:2px solid rgb(var(--c-blue-600));outline-offset:-3px}
.data-table [data-above-row]{position:relative;z-index:2}
.data-table[data-p1="hide"] [data-p="1"],.data-table[data-p2="hide"] [data-p="2"]{display:none}
@container datatable (max-width:1099px){.data-table[data-p1="auto"] [data-p="1"]{display:none}}
@container datatable (max-width:979px){.data-table[data-p2="auto"] [data-p="2"]{display:none}}
@container datatable (max-width:899px){
  .data-table,.data-table tbody{display:block}
  .data-table thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
  .data-table tr{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;padding:12px;border-bottom:1px solid rgb(var(--c-line))}
  .data-table tbody:last-child tr:last-child{border-bottom:0}
  .data-table td,.data-table th{display:block;width:auto;height:auto;border:0;padding:0}
  .data-table [data-cell="name"]{grid-column:1;grid-row:1}
  .data-table [data-cell="actions"]{grid-column:2;grid-row:1}
  .data-table [data-cell="context"]{display:block!important;grid-column:1/-1;grid-row:2}
  .data-table[data-p2="hide"] [data-cell="context"]{display:none!important}
  .data-table [data-cell="status"]{grid-column:1;grid-row:3;align-self:center}
  .data-table [data-cell="amount"]{grid-column:2;grid-row:3;align-self:center}
  .data-table [data-cell="extra"]{display:none!important}
  .data-table [data-sum] [data-cell="context"],.data-table [data-sum] [data-cell="status"],.data-table [data-sum] [data-cell="actions"]{display:none!important}
  .data-table [data-sum] [data-cell="amount"]{grid-row:1}
}
/* CR-11 block 7 (#1559), design-system-end-state §3.3: the repeating group.
   12 px between rows with a thin line in that space. A simple row in edit mode
   is [handle 44] [fields] [⋯ 44]; its labels stand once, in the group's head,
   and are hidden per row — until the section is too narrow for two half fields
   (the same 532 px), where the head goes, the fields stack with their labels and
   the handle and ⋯ take the first line. A composite item keeps its handle in a
   gutter of 44 px at the left of the whole block. A child group is indented
   behind a vertical line: 16 px, 12 on a phone. While dragging: the origin
   dotted and dimmed, a brand line where the row will land. */
.group-rows>[data-group-row]+[data-group-row]{margin-top:12px;padding-top:12px;border-top:1px solid rgb(var(--c-line))}
.group-row--edit.group-row--simple{display:grid;grid-template-columns:minmax(0,1fr) 44px;column-gap:8px;align-items:end}
.group-row--edit.group-row--simple.group-row--handle{grid-template-columns:44px minmax(0,1fr) 44px}
.group-row--edit.group-row--composite.group-row--handle{display:grid;grid-template-columns:44px minmax(0,1fr);column-gap:8px;align-items:start}
.group-handle{display:flex;align-items:center;justify-content:center;width:44px;height:44px;color:rgb(var(--c-ink-soft));cursor:grab;touch-action:none}
.group-head{margin-bottom:4px;padding-right:52px}
.group-head--handle{padding-left:52px}
.group-row--edit.group-row--simple [data-field]>label{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.group-child{margin-top:16px;padding-left:16px;border-left:1px solid rgb(var(--c-line))}
.group-dragging{opacity:.5;outline:1px dashed rgb(var(--c-control-line));outline-offset:2px}
.group-drop-before{box-shadow:0 -2px 0 rgb(var(--c-brand))}
.group-drop-after{box-shadow:0 2px 0 rgb(var(--c-brand))}
@container (max-width:531.98px){
  .group-head{display:none}
  .group-row--edit.group-row--simple,.group-row--edit.group-row--simple.group-row--handle{grid-template-columns:44px minmax(0,1fr) 44px;row-gap:4px;align-items:center}
  .group-row--edit.group-row--simple>.group-body{grid-column:1/-1;grid-row:2}
  .group-row--edit.group-row--simple:not(.group-row--handle)>.relative{grid-column:3}
  .group-row--edit.group-row--simple [data-field]>label{position:static;width:auto;height:auto;margin:0 0 4px;overflow:visible;clip:auto;white-space:normal}
  .group-child{padding-left:12px}
}
.nav-drawer-only,.nav-when-rail{display:none}
html.nav-rail .admin-sidebar:not(.is-open) .nav-label{display:none}
html.nav-rail .admin-sidebar:not(.is-open) .nav-rail-mark{display:block}
html.nav-rail .admin-sidebar:not(.is-open) .nav-link{justify-content:center;padding-inline:0}
html.nav-rail .admin-sidebar:not(.is-open) .admin-sidebar-brand{justify-content:center;padding-inline:8px}
html.nav-rail .admin-sidebar:not(.is-open) .nav-heading{height:8px;padding:0;border-top:1px solid rgb(var(--c-line)/.5);pointer-events:none}
html.nav-rail .nav-when-rail{display:inline-flex}
html.nav-rail .nav-when-wide{display:none}
.admin-backdrop{position:fixed;inset:0;z-index:40;background:rgb(var(--c-ink)/.32)}
@media (width < 768px){
  html body[data-shell="admin"],html.nav-rail body[data-shell="admin"]{--nav-current:0px}
  .admin-sidebar{display:none}
  .admin-sidebar.is-open{display:flex;top:0;width:312px;max-width:100%;z-index:50;box-shadow:0 12px 40px rgb(var(--c-ink)/.16)}
  .admin-sidebar.is-open .nav-drawer-only{display:inline-flex}
  .admin-sidebar.is-open .nav-link{min-height:44px}
  .nav-desktop-only{display:none}
}
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
