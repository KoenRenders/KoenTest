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
  /* CR-11 pilot B (#1588): the public site in palette Atelier (decision 01,
     §1.1): the same brand blue and cool greys as the back office, plus the ONE
     warm accent `238 193 94` (text `37 44 53`) for the site's one call to
     action. Tailwind's scales are redefined, so no template changes: blue
     around the brand, gray as the Atelier neutrals. Radius: controls 6 px,
     cards 14 px. ONE family on both shells (#1606, Koen, 5 October 2026;
     §1.6): `font-brand` resolves to Inter here as in the back office — the
     serif heading face of P1 (#1588) is gone, with its font file. The public
     headings are a little LARGER than the admin's, in Inter 600 at line
     height 1.15: see the scale under this block.
     `--c-site-header` is the header's band WITHOUT a tenant colour: what it was
     before these tokens (36 75 197), so a tenant that set nothing keeps its
     header (`site_header_color` overrides it as before). */
  body[data-shell="site"]{
        --c-blue-50:230 239 247;--c-blue-100:210 224 236;--c-blue-200:156 184 210;--c-blue-300:118 152 182;--c-blue-400:72 116 154;--c-blue-500:25 95 157;--c-blue-600:31 70 110;--c-blue-700:37 78 115;--c-blue-800:25 57 88;--c-blue-900:20 45 70;--c-blue-950:12 28 45;
        --c-brand:37 78 115;--c-brand-ocean:37 78 115;--c-brand-ocean-hover:25 57 88;
        --c-accent:238 193 94;--c-on-accent:37 44 53;
        --c-site-header:36 75 197;
        --c-link:37 78 115;--c-kop:33 45 58;
        --c-ink:33 45 58;--c-ink-soft:83 99 115;
        --c-line:216 224 230;--c-ground:244 246 248;--c-surface:255 255 255;--c-surface-2:240 243 246;
        --c-control-line:126 143 158;--c-focus:25 95 157;
        --c-gray-50:244 246 248;--c-gray-100:240 243 246;--c-gray-200:216 224 230;--c-gray-300:190 201 210;--c-gray-400:126 143 158;--c-gray-500:83 99 115;--c-gray-600:83 99 115;--c-gray-700:50 66 81;--c-gray-800:33 45 58;--c-gray-900:33 45 58;--c-gray-950:20 28 36;
        --r-lg:6px;--r-xl:10px;--r-2xl:14px;
        --font-brand:Inter,system-ui,sans-serif}
  /* The readable aliases are resolved where they are declared (:root), so the
     shell declares them again — otherwise `var(--brand-ocean)` in the CMS
     content rules would stay the root's blue (measured: a CMS heading in
     0 81 164 on the platform home). */
  body[data-shell="site"]{
        --brand-ocean:rgb(var(--c-brand-ocean));--primary:rgb(var(--c-brand-ocean));--primary-hover:rgb(var(--c-brand-ocean-hover));--link:rgb(var(--c-link));
        --ground:rgb(var(--c-ground));--surface:rgb(var(--c-surface));--surface-2:rgb(var(--c-surface-2));
        --ink:rgb(var(--c-ink));--ink-soft:rgb(var(--c-ink-soft));--line:rgb(var(--c-line))}
  /* The public heading scale (#1606, §1.6, §2.6): page title 32 px on a phone
     and 40 px from 768, section head 24 px, card title 18 px — Inter 600, line
     height 1.15. On the heading's tag and not in a template: a page writes
     `<h1>`, `<h2>`, `<h3>` and the shell sizes them, so no public page can
     come to differ. A section of a FORM keeps the kit's head (16 px, its own
     line height): that is a field group's label, the same in both shells.

     #1621 (Koen, 5 October 2026): a title INSIDE a card (`ui.card`, the
     `.rounded-2xl` box) is the scale's CARD title — 18 px (CR-11 Q61) — on
     Tailwind's line of 28 px, at every width. Measured on master: the `h2`
     rule above made an activity card's title a section head, 24 px on a line
     of 27.6 px, so it stood tight on its dates; v2.12.0 rendered 20 px on a
     phone and 18 px from 768, both on 28 px. A page title in a card (the
     sign-in page) stays a page title. */
  body[data-shell="site"] :is(h1,h2,h3){font-family:var(--font-brand);font-weight:600;line-height:1.15}
  body[data-shell="site"] #main h1{font-size:32px}
  body[data-shell="site"] #main h2{font-size:24px}
  body[data-shell="site"] #main h3{font-size:18px}
  body[data-shell="site"] #main .rounded-2xl :is(h2,h3){font-size:18px;line-height:28px}
  @media (min-width:768px){body[data-shell="site"] #main h1{font-size:40px}}
  body[data-shell="site"] #main .form-section :is(h2,h3){font-size:16px;line-height:24px}
  /* The site's name in the header where a tenant has no logo, and the drawer's
     head: semibold like the headings (the serif face had one weight only). */
  body[data-shell="site"] .font-brand{font-weight:600}
  body[data-shell="site"] .cms-content :is(h1,h2){color:rgb(var(--c-kop))}
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
.record-frame{container-type:inline-size;container-name:record}
.record-columns{display:grid;grid-template-columns:minmax(0,768px);gap:24px;align-items:start}
.record-form-column{min-width:0}
.form-flow{display:grid;gap:32px;min-width:0}
/* CR-11 pilot B (#1589, §2.6): the public form page — one column of 768 px,
   centred in the site shell (720 on a tablet: the container's own width),
   left-aligned in the admin's. 24 px under the site's header on a phone, 32
   above (the shell's <main> gives 32). The title in the site's heading face,
   32 / 40 px; 24 px to the first card. */
.public-form-page{width:100%;max-width:768px;margin-inline:auto}
.public-form-page-admin{margin-inline:0}
.public-form-head{margin-bottom:24px}
.public-form-title{font-family:var(--font-brand);font-weight:600;font-size:32px;line-height:1.15;color:rgb(var(--c-ink));overflow-wrap:anywhere}
.public-form-title:focus{outline:none}
/* A section's head is Inter 16 px semibold in both shells (§2.6): the site's
   heading face is for the page's title, not for the cards of a form. */
@media (min-width:768px){.public-form-title{font-size:40px}}
@media (max-width:767.98px){body[data-shell="site"] .public-form-page{margin-top:-8px}}
/* #1587: the flow's message line (where a refused or failed save stands) is a
   child of the flow, and an empty one still took the 32 px gap under it — the
   first card then started 32 px below the summary card beside it. Empty, it
   is no part of the flow. `:has`, not `:empty`: the template leaves white
   space in it. */
.form-flow>[data-form-message]:not(:has(*)){display:none}
.record-summary-column{min-width:0;order:-1}
@container (min-width:964px){.record-columns:has(>.record-summary-column){grid-template-columns:minmax(0,768px) 300px}.record-summary-column{order:0}}
/* #1610 (Koen, 5 October 2026; end state §2.2): room for the groups. A record
   that is being EDITED and holds a composite repeating group (components with
   their products) takes the whole reading group — 1 092 px — and its summary
   goes above the form as the strip it is on a narrow frame. The layout reads
   that from what stands in it (`:has`), so a save or a cancel — the form back
   in read mode — gives the 768 px column and the card at the right again
   without anybody saying so. Only where the frame has the 1 092 px: with the
   Assistent's panel open, or on a smaller window, nothing changes.

   #1635 (Koen, 5 October 2026; CR-11 Q74): every field of full width fills
   the wider column, a text box included — the width of a field follows its
   column. #1610 kept `textarea`, `url` and `email` at 768 px here, which left
   Omschrijving and Interne nota with a gap of 290 px at their right. */
@container record (min-width:1092px){
  .record-columns:has([data-form-flow][data-mode="edit"] [data-repeating-group][data-variant="composite"]){grid-template-columns:minmax(0,1092px)}
  .record-columns:has([data-form-flow][data-mode="edit"] [data-repeating-group][data-variant="composite"])>.record-summary-column{order:-1}
}
.summary-card{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:12px;align-items:center}
.summary-card [data-summary-state]{grid-column:1;grid-row:1}
.summary-card [data-summary-action]{grid-column:2;grid-row:1}
.summary-card [data-summary-link]{display:none}
.summary-card [data-summary-figures]{grid-column:1/-1;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
@container (min-width:964px){
  .summary-card{grid-template-columns:minmax(0,1fr);padding:16px}
  .summary-card [data-summary-figures]{grid-column:1;grid-template-columns:repeat(2,minmax(0,1fr))}
  .summary-card [data-summary-figure]:nth-child(3){grid-column:1/-1;display:flex;align-items:baseline;justify-content:space-between;gap:12px}
  .summary-card [data-summary-action]{grid-column:1;grid-row:auto;display:flex;align-items:center;gap:8px;border-top:1px solid rgb(var(--c-line));padding-top:12px}
  .summary-card [data-summary-link]{display:block;flex:1}
}
/* #1610: above a wide form the summary is the strip it is on a narrow frame —
   one shape for "above" — so the card shape just said is taken back there. */
@container record (min-width:1092px){
  .record-columns:has([data-form-flow][data-mode="edit"] [data-repeating-group][data-variant="composite"]) .summary-card{grid-template-columns:minmax(0,1fr) auto;padding:12px}
  .record-columns:has([data-form-flow][data-mode="edit"] [data-repeating-group][data-variant="composite"]) .summary-card [data-summary-figures]{grid-column:1/-1;grid-template-columns:repeat(3,minmax(0,1fr))}
  .record-columns:has([data-form-flow][data-mode="edit"] [data-repeating-group][data-variant="composite"]) .summary-card [data-summary-figure]:nth-child(3){grid-column:auto;display:block}
  .record-columns:has([data-form-flow][data-mode="edit"] [data-repeating-group][data-variant="composite"]) .summary-card [data-summary-action]{grid-column:2;grid-row:1;display:block;border-top:0;padding-top:0}
  .record-columns:has([data-form-flow][data-mode="edit"] [data-repeating-group][data-variant="composite"]) .summary-card [data-summary-link]{display:none}
}
.form-section{container-type:inline-size;min-width:0}
.form-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;align-items:start}
.form-grid>[data-span="full"]{grid-column:1/-1}
.form-grid>[data-span="half"]{grid-column:span 2}
.form-grid>[data-span="quarter"]{grid-column:span 1}
/* #1610: a row of a group with one wide field and three short ones (a product:
   name · price · member price · maximum) stands on five tracks, so the four
   share one line. */
.form-grid--five{grid-template-columns:repeat(5,minmax(0,1fr))}
/* Two grids under each other in one row (a product's two lines) keep the grid's own gap. */
.form-grid+.form-grid{margin-top:12px}
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
.data-table [data-stacked-only]{display:none}
.data-table [data-row-link]::after{content:"";position:absolute;inset:0;z-index:1;cursor:pointer}
.data-table [data-row-toggle]::after{content:"";position:absolute;inset:0;z-index:1;cursor:pointer}
.data-table [data-row-toggle]:focus-visible{outline:none}
.data-table [data-row-toggle]:focus-visible::after{outline:2px solid rgb(var(--c-blue-600));outline-offset:-3px}
.data-table [data-row]:has([data-row-toggle][aria-expanded="true"]){background:rgb(var(--c-blue-50))}
.data-table tbody[data-collapsed="true"] tr:not([data-group-row]){display:none!important}
.row-parts{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:16px 24px}
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
  .data-table [data-stacked-only]{display:block}
  .data-table [data-cell="amount"]{text-align:right}
  .data-table [data-cell="date"]{grid-column:2;grid-row:3;align-self:center}
  .data-table [data-cell="more"]{grid-column:1/-1;grid-row:4}
  .data-table [data-group-row]{align-items:center;padding:0 12px}
  .data-table tr[data-row-detail]{display:block;padding:0}
  .data-table tr[data-row-detail]>td{padding:12px;border-left:3px solid rgb(var(--c-brand-ocean))}
  .row-parts{grid-auto-flow:row}
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
/* #1610: a composite item's handle stands in a gutter of 28 px (it was 44): the
   target stays 44 px high, the handle itself is 24 px wide. */
.group-row--edit.group-row--composite.group-row--handle{display:grid;grid-template-columns:28px minmax(0,1fr);column-gap:8px;align-items:start}
.group-row--composite>.group-handle{width:24px;margin-left:2px}
.group-handle{display:flex;align-items:center;justify-content:center;width:44px;height:44px;color:rgb(var(--c-ink-soft));cursor:grab;touch-action:none}
.group-head{margin-bottom:4px;padding-right:52px}
.group-head--handle{padding-left:52px}
.group-row--edit.group-row--simple [data-field]>label{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.group-child{margin-top:16px;padding-left:12px;border-left:1px solid rgb(var(--c-line))}
/* #1590: a folded composite row — the title line is the summary, the chevron
   turns when it is open, and the row's menu stands at the far right of that
   line, outside the summary so a click on it does not fold the row. One among
   many: the tag of a simple row stands before its menu. */
.group-row--fold>.group-body{position:relative}
.group-fold-summary{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:44px;cursor:pointer;list-style:none;border-radius:6px}
.group-fold-summary::-webkit-details-marker{display:none}
.group-fold-summary:focus-visible{outline:3px solid rgb(var(--c-focus));outline-offset:2px}
.group-fold-chevron{display:flex;align-items:center;justify-content:center;width:44px;height:44px;flex:none;color:rgb(var(--c-ink-soft));transition:transform .15s}
.group-fold[open]>.group-fold-summary .group-fold-chevron{transform:rotate(180deg)}
.group-fold--menu>.group-fold-summary{padding-right:44px}
.group-fold-menu{position:absolute;top:0;right:0}
.group-fold[open]>.group-fold-summary{margin-bottom:8px}
/* An item of a row's menu that does not apply is `hidden` — and `hidden` loses
   from the `flex` the item is drawn with (#1603: "Maak hoofdadres" stood on the
   row that already was the main one). */
[data-row-menu] [hidden]{display:none!important}
.group-row--simple.group-row--one{display:grid;grid-template-columns:minmax(0,1fr) auto;column-gap:8px;align-items:center}
.group-row--edit.group-row--simple.group-row--one{grid-template-columns:minmax(0,1fr) auto 44px;align-items:end}
.group-row--edit.group-row--simple.group-row--one>[data-row-one-tag]{align-self:center}
.group-dragging{opacity:.5;outline:1px dashed rgb(var(--c-control-line));outline-offset:2px}
.group-drop-before{box-shadow:0 -2px 0 rgb(var(--c-brand))}
.group-drop-after{box-shadow:0 2px 0 rgb(var(--c-brand))}
/* CR-11 block 9 (#1561), design-system-end-state §3.6, §3.18: the action bar of
   a record form and the states of a save.
   The bar is the form flow's last child: 64 px, white, a thin top line, 24 px
   under the last section (the flow's gap is 32). Sticky 16 px above the window's
   bottom while the form is longer than the window; at the form's end it stands
   in the flow. Verwijderen left, then Annuleren and Opslaan at the right.
   On a phone: Opslaan full width on the first line, Verwijderen left and
   Annuleren right on the second — 121 px (16 + 44 + 8 + 44 + 8 + the line),
   sticky at the window's bottom and as wide as the window. Sticky and not
   fixed: the record frame is a query container, and that makes it the
   containing block of anything fixed inside it. The flow keeps 24 px free
   under the bar, so the last field is never under it.
   A refused field: the reason under it in red and a red line on its control;
   a refused row: the reason on top of it and a red line at its left. */
/* #1607 (Koen, 5 October 2026; end state §3.6): flush against the window's
   bottom while the form is longer than the window — the 16 px it floated on
   are gone — with a heavier line on top and, while it sticks, the shadow
   upward (`data-stuck`, set by record-form.js); in the flow at the form's end
   it is a plain row again. The same picture on a phone and in both shells. */
.record-bar{position:sticky;bottom:0;z-index:20;display:flex;align-items:center;gap:8px;min-height:64px;margin-top:-8px;padding:0 16px;background:rgb(var(--c-surface));border-top:2px solid rgb(var(--c-line))}
.record-bar[data-stuck]{box-shadow:0 -8px 24px -4px rgb(var(--c-ink)/.14)}
.record-bar-delete{margin-right:auto}
.record-bar-cancel{margin-left:auto}
.record-bar-delete+.record-bar-cancel{margin-left:0}
.record-bar[data-saving] .record-bar-cancel,.record-bar[data-saving] .record-bar-delete{opacity:.5}
/* `hidden` loses from a display utility on the same element: say it here. */
.record-bar [hidden]{display:none!important}
.record-spinner{width:14px;height:14px;border:2px solid currentColor;border-right-color:transparent;border-radius:9999px;animation:record-spin .7s linear infinite}
@keyframes record-spin{to{transform:rotate(360deg)}}
[data-refused-message]{margin-top:4px;font-size:13px;line-height:19.5px;color:rgb(var(--c-red-700));overflow-wrap:anywhere}
[data-refused-control]{border-color:rgb(var(--c-red-700))!important}
[data-group-row][data-refused]{box-shadow:inset 3px 0 0 rgb(var(--c-red-600))}
[data-group-row][data-refused]>[data-refused-message],[data-group-row][data-refused] [data-row-body]>[data-refused-message]{margin:0 0 4px;padding-left:8px}
@media (max-width:767.98px){
  .record-bar{display:grid;grid-template-columns:1fr 1fr;gap:8px;min-height:121px;margin:-8px -16px 0;padding:11px 16px 12px}
  .record-bar-save{grid-column:1/-1;grid-row:1}
  .record-bar-delete{grid-column:1;grid-row:2;justify-self:start;margin:0}
  .record-bar-cancel{grid-column:2;grid-row:2;justify-self:end;margin:0}
  .form-flow:has(>.record-bar){padding-bottom:24px}
}
/* CR-11 block 10 (#1562), §3.15: a field the Assistent proposes a value for —
   a blue line and the brand tint on its control, the note under it. The same
   look once applied; the note's words say which of the two it is. */
[data-field][data-proposed] :is(input:not([type=hidden]),select,textarea,trix-editor),[data-field][data-proposal-applied] :is(input:not([type=hidden]),select,textarea,trix-editor){border-left:3px solid rgb(var(--c-blue-600));background-color:rgb(var(--c-blue-50))}
[data-form-proposal] [hidden]{display:none!important}
[data-proposal-note]{margin-top:4px;font-size:13px;line-height:19.5px;color:rgb(var(--c-blue-700));overflow-wrap:anywhere}
/* The toast in the admin (§3.18): under the top bar at the right on a desktop,
   at the bottom on a phone; "saved" is white on ink. */
body[data-shell="admin"] #toasts{top:96px}
body[data-shell="admin"] #toasts [data-toast="success"]{background:rgb(var(--c-ink));border-color:rgb(var(--c-ink));color:#fff}
@media (max-width:767.98px){body[data-shell="admin"] #toasts{top:auto;bottom:16px;left:16px;right:16px;width:auto}}
@container (max-width:531.98px){
  .group-head{display:none}
  .group-row--edit.group-row--simple,.group-row--edit.group-row--simple.group-row--handle{grid-template-columns:44px minmax(0,1fr) 44px;row-gap:4px;align-items:center}
  .group-row--edit.group-row--simple>.group-body{grid-column:1/-1;grid-row:2}
  .group-row--edit.group-row--simple:not(.group-row--handle)>.relative{grid-column:3}
  .group-row--edit.group-row--simple.group-row--one{grid-template-columns:minmax(0,1fr) 44px;align-items:center;min-height:44px}
  .group-row--edit.group-row--simple.group-row--one>[data-row-one-tag]{grid-column:1;grid-row:1;justify-self:start}
  .group-row--edit.group-row--simple.group-row--one>.relative{grid-column:2;grid-row:1}
  .group-row--edit.group-row--simple [data-field]>label{position:static;width:auto;height:auto;margin:0 0 4px;overflow:visible;clip:auto;white-space:normal}
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
/* ── The public shell (CR-11 pilot B, P1 — #1588; end state §2.5) ───────────────
   Block 11 (Koen, 4 October 2026). One container for the header, the content
   and the footer: 16 px gutters on a phone, 24 from 768 px, 32 from 1 200 px,
   at most 1 248 px — so the footer no longer sticks out of the content.

   The header is the band in the tenant's colour (`--c-site-header`, or the
   tenant's own through a style attribute), sticky at y 0: 64 px on a phone
   (brand and menu button), 112 px from 768 px (brand and account on a row of
   64, the pages on a row of 48), 80 px from 1 200 px (one row: brand, pages,
   account). The environment banner stands above it in the document flow and
   scrolls away.

   The LOGO is as high as its row allows — the row minus 2 × 8 px of air, the
   trade of #1156 (#1621, CR-11 Q69, end state §2.5): 48 px in the rows of 64
   (a phone, and the first row from 768 px), 64 px in the band of 80 from
   1 200 px. #1588 had set it to 48 px at every width, 16 px lower than
   v2.12.0 showed on a desktop. The width follows the image; a very wide logo
   is drawn smaller inside its box and never pushes the menu button away.

   The drawer (below 768 px): 360 px, white, OVER the page — nothing moves —
   with the backdrop under it; the page behind it is inert.

   The footer: white, one row of three columns from 1 200 px (newsletter ·
   social links · sponsors), two from 768 px, stacked on a phone; under it the
   legal line. 88 px stay free under the legal line for the bell. On a short
   page the footer stands at the bottom of the window. */
.site-container{width:calc(100% - 32px);max-width:1248px;margin-inline:auto}
/* A short page keeps its footer at the bottom of the window (measured: the
   company's home at 390 px ended at y 458 with the ground under the footer). */
body[data-shell="site"]{display:flex;flex-direction:column;min-height:100vh}
body[data-shell="site"]>main{flex:1 0 auto}
.site-header{position:sticky;top:0;z-index:40;background:rgb(var(--c-site-header));color:#fff}
.site-header-grid{display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"brand menu";align-items:center;gap:0 16px;height:64px}
.site-brand{grid-area:brand;display:flex;align-items:center;min-height:44px;min-width:0;color:inherit}
.site-brand img{height:48px;width:auto;max-width:100%;object-fit:contain}
.site-menu-button{grid-area:menu}
.site-pages,.site-account{display:none}
.site-header a:focus-visible,.site-header button:focus-visible{outline:2px solid #fff;outline-offset:2px}
.site-drawer{position:fixed;inset:0 0 0 auto;z-index:50;display:flex;flex-direction:column;width:360px;max-width:calc(100vw - 24px);height:100dvh;padding:0 16px 24px;overflow-y:auto;background:rgb(var(--c-surface));color:rgb(var(--c-ink));box-shadow:0 12px 40px rgb(var(--c-ink)/.16)}
.site-drawer-backdrop{position:fixed;inset:0;z-index:45;background:rgb(var(--c-ink)/.32)}
.site-drawer-row{display:flex;align-items:center;gap:12px;width:100%;min-height:48px;padding:12px;border-radius:6px;font-size:16px;color:rgb(var(--c-ink));text-align:left}
.site-drawer-row:hover{background:rgb(var(--c-surface-2));text-decoration:none}
.site-drawer-row[aria-current="page"]{background:rgb(var(--c-blue-50));color:rgb(var(--c-brand));font-weight:600;text-decoration:underline;text-underline-offset:4px;text-decoration-thickness:2px}
.site-footer{margin-top:48px;background:rgb(var(--c-surface))}
.site-footer-core{border-top:1px solid rgb(var(--c-line));padding-block:48px 24px}
.site-footer-core[data-bell]{padding-bottom:88px}
.site-footer-row{display:grid;grid-template-columns:minmax(0,1fr);gap:32px}
.site-footer-row h2{font-size:18px;line-height:1.2;margin-bottom:12px;color:rgb(var(--c-ink))}
.site-legal{margin-top:32px;padding-top:16px;border-top:1px solid rgb(var(--c-line));font-size:14px;line-height:24px;color:rgb(var(--c-ink-soft));overflow-wrap:anywhere}
.site-legal a{text-decoration:underline;text-underline-offset:4px}
.site-sponsor{display:flex;align-items:center;justify-content:center;width:144px;height:64px;padding:8px;border:1px solid rgb(var(--c-line));border-radius:6px;background:rgb(var(--c-surface))}
.site-sponsor img{max-width:100%;max-height:100%;object-fit:contain}
@media (min-width:768px){
  .site-container{width:calc(100% - 48px)}
  .site-header-grid{grid-template-columns:minmax(0,1fr) auto;grid-template-rows:64px 48px;grid-template-areas:"brand account" "pages pages";height:112px}
  .site-menu-button{display:none}
  .site-pages{grid-area:pages;display:flex;align-items:center;gap:4px;height:48px;min-width:0}
  .site-account{grid-area:account;display:flex;align-items:center;gap:8px}
  .site-footer{margin-top:64px}
  .site-footer-core{padding-top:64px}
  .site-footer-row{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media (min-width:1200px){
  .site-container{width:calc(100% - 64px)}
  .site-header-grid{grid-template-columns:minmax(0,1fr) auto auto;grid-template-rows:80px;grid-template-areas:"brand pages account";gap:24px;height:80px}
  .site-brand img{height:64px}
  .site-pages{height:auto}
  .site-footer-row{grid-template-columns:1.3fr .8fr 1fr;gap:48px}
}
/* ── The Assistent panel (CR-11 pilot A, K8 — #1562; end state §3.15) ──────────
   One component, `_raakje_panel.html`, in two modes.

   Docked (the back office): from 1 440 px a column of 400 px at the right, under
   the top bar (64 px, 88 with the environment band) to the window's bottom, and
   THE CONTENT MOVES ASIDE — `assistant-open` on <html> gives `#main` the same
   400 px of margin, so nothing is covered and the top bar keeps its width. At 1 920 the reading group fits
   beside it; at 1 440 exactly 768 px remain and the record's summary becomes its
   strip (its own container query). Below 1 440 a centred dialog of at most
   560 × 720 px over a blocked background; below 768 a sheet of 560 px from the
   bottom with a handle.

   Bell (the public site): a button of 56 px at the bottom right; from 768 px a
   window of 400 × 640 px above it, below that the same sheet.

   The panel is a flex column: head, the conversation with its own scroll, the
   suggestions, the field. */
.raakje-panel{position:fixed;z-index:45;display:flex;flex-direction:column;min-height:0;background:rgb(var(--c-surface));border:1px solid rgb(var(--c-line));
  left:0;right:0;bottom:0;height:560px;max-height:calc(100vh - 64px);border-radius:16px 16px 0 0;border-bottom:0;box-shadow:0 -8px 32px rgb(var(--c-ink)/.16)}
.raakje-panel-handle{flex:none;width:36px;height:4px;margin:8px auto 0;border-radius:2px;background:rgb(var(--c-line))}
.raakje-backdrop{position:fixed;inset:0;z-index:44;background:rgb(var(--c-ink)/.32)}
.raakje-bell{position:fixed;right:16px;bottom:var(--bell-bottom,16px);z-index:43;display:grid;place-items:center;width:56px;height:56px;border-radius:9999px}
@media (min-width:768px){
  .raakje-panel-handle{display:none}
  [data-mode="docked"] .raakje-panel{left:50%;right:auto;top:50%;bottom:auto;transform:translate(-50%,-50%);width:min(560px,calc(100vw - 32px));height:min(720px,calc(100vh - 32px));max-height:none;border-radius:16px;border-bottom:1px solid rgb(var(--c-line));box-shadow:0 16px 48px rgb(var(--c-ink)/.24)}
  [data-mode="bell"] .raakje-panel{left:auto;right:16px;bottom:calc(var(--bell-bottom,16px) + 72px);width:400px;height:min(640px,calc(100vh - 104px));max-height:none;border-radius:16px;border-bottom:1px solid rgb(var(--c-line));box-shadow:0 16px 48px rgb(var(--c-ink)/.24)}
  [data-mode="bell"] .raakje-backdrop{display:none}
}
@media (min-width:1440px){
  [data-mode="docked"] .raakje-panel{left:auto;right:0;top:64px;bottom:0;transform:none;width:400px;height:auto;border-width:0 0 0 1px;border-radius:0;box-shadow:none;z-index:15}
  [data-mode="docked"] .raakje-panel.raakje-panel--env{top:88px}
  [data-mode="docked"] .raakje-backdrop{display:none}
  html.assistant-open #main{margin-right:400px}
}
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
