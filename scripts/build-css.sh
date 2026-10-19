#!/usr/bin/env bash
# Genereert backend/app/static/app.css uit de Jinja-templates (#396, §21).
# Nul Node (React-exit #405): gebruikt de Tailwind standalone-CLI. De binary
# wordt eenmalig gedownload naar .cache/ (staat in .gitignore).
# Draai dit na elke template-wijziging en commit de gegenereerde CSS mee.
# Een merge stopt nooit op app.css (#2037): .gitattributes houdt van beide kanten de
# regels (merge=union); de CI-job `css` blijft rood tot dit script na de merge draait.
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
     phone and 18 px from 768, both on 28 px.

     #1642 (Koen, 5 October 2026; CR-11 Q78, end state §5.3): 40 px (32 on a
     phone) is the size of a page title ON THE PAGE'S GROUND. A heading inside
     a card is the card's: an `h1` there is 24 px (the sign-in page, the
     expired link, the contact form), an `h2` or `h3` 18 px. ONE mechanism for
     the three levels — "inside a card" — where #1621 had a rule for two of
     them and left the `h1` a page title. The kit's own title role
     (`.public-form-title`, the title slot of `public_form_page` and of a
     flow card) says itself that it is a page title and keeps that size. */
  body[data-shell="site"] :is(h1,h2,h3){font-family:var(--font-brand);font-weight:600;line-height:1.15}
  body[data-shell="site"] #main h1{font-size:32px}
  body[data-shell="site"] #main h2{font-size:24px}
  body[data-shell="site"] #main h3{font-size:18px}
  body[data-shell="site"] #main .rounded-2xl h1:not(.public-form-title){font-size:24px}
  body[data-shell="site"] #main .rounded-2xl :is(h2,h3){font-size:18px;line-height:28px}
  @media (min-width:768px){body[data-shell="site"] #main h1{font-size:40px}}
  body[data-shell="site"] #main .form-section :is(h2,h3){font-size:16px;line-height:24px}
  /* The site's name in the header where a tenant has no logo, and the drawer's
     head: semibold like the headings (the serif face had one weight only). */
  body[data-shell="site"] .font-brand{font-weight:600}
  body[data-shell="site"] .home-intro :is(h1,h2){color:rgb(var(--c-kop))}
  /* #1656 (Koen, 6 October 2026; CR-11 Q87, design-system.md §7): the headings
     of a public page's BODY (`.cms-page`, under the page's own title). The
     renderer shows them one level down, so the editor's Kop, Subkop and Kleine
     kop arrive as h2, h3 and h4: 24, 18 and 16 px, semibold, in the site's
     heading colour, 24 px of air above and 8 px under. Measured on master: the
     page-title rule above (`#main h1`, an id) won from `.cms-content h1`
     (1.5rem, a class), so a heading in the text stood 40 px tall beside the
     page's title. The h1 is named here too, so the title role can never reach
     into a page body. */
  body[data-shell="site"] #main .cms-page :is(h1,h2){font-size:24px}
  body[data-shell="site"] #main .cms-page h3{font-size:18px}
  body[data-shell="site"] #main .cms-page h4{font-size:16px}
  body[data-shell="site"] #main .cms-page :is(h1,h2,h3,h4){font-family:var(--font-brand);font-weight:600;line-height:1.15;color:rgb(var(--c-kop));margin:24px 0 8px}
  body[data-shell="site"] #main .cms-page>:is(h1,h2,h3,h4):first-child{margin-top:0}
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
/* CR-11 block 6 (#1558), design-system-end-state §1.4, §3.2 — widened by CR-17
   slice 4 (Koen, 9 October 2026: "links houden, maar het scherm benutten").
   A record page (it carries the record head) takes the frame like a list
   page; inside it the reading group is LEFT-aligned and never centred.
   The PAGE screen's form column grows with the screen up to a readable
   cap of 1 056 px (his words: the screen may be used; the cap keeps her
   lines readable) — hers alone, carried by `[data-wide]`; every other
   record keeps her 768 px. Narrower, the form column simply takes what
   the frame gives. The summary
   stands beside the form while the form keeps 640 px (964 px of frame),
   else above it. The form grid has four tracks, 12 px apart; it goes to
   one column when the section is narrower than 532 px inside (two half fields
   of 260 px and their gap) — a container query, which a utility cannot say.
   16 px between the cards of a form column (#1899, CR-11 B10 of 10 October
   2026; 32 px until then). */
.admin-content:has([data-record-head]){max-width:none}
.record-frame{container-type:inline-size;container-name:record}
.record-columns{display:grid;grid-template-columns:minmax(0,768px);gap:24px;align-items:start}
/* CR-17 slice 4, scoped after the CI run of 9 October (#1770): the wide
   reading group is the PAGE screen's own (Koen's words were about her
   form), carried by her own attribute — an existing record keeps her width.

   The ONE named exception to #1929's "one width of 768 px for every record"
   (below). Koen, 13 October 2026, asked through the master CLI whether the
   page screen keeps using the screen up to 1 056 px, as he said on 9 October
   ("links houden, maar het scherm benutten"), with 768 px for the other
   records (option a), or becomes 768 px without exception (option b): "4a". */
.record-columns[data-wide]{grid-template-columns:minmax(0,1056px)}
.record-form-column{min-width:0}
.form-flow{display:grid;gap:16px;min-width:0}
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
   child of the flow, and an empty one still took the flow's gap under it — the
   first card then started that far below the summary card beside it. Empty, it
   is no part of the flow. `:has`, not `:empty`: the template leaves white
   space in it. */
.form-flow>[data-form-message]:not(:has(*)){display:none}
.record-summary-column{min-width:0;order:-1}
@container (min-width:964px){.record-columns:has(>.record-summary-column){grid-template-columns:minmax(0,768px) 300px}.record-summary-column{order:0}}
@container (min-width:964px){.record-columns[data-wide]:has(>.record-summary-column){grid-template-columns:minmax(0,1056px) 300px}}
/* #1929 (Koen, 12 October 2026, to "Kies je c, één breedte van 768 px voor elk
   record in beide modi?": "Ja"; CR-11 Q96): one width for every record, in read
   and in edit mode. The 1 092 px editor of #1610 is gone; a full-width field
   fills its column (#1635), and the column is 768 px. */
.summary-card{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:12px;align-items:center}
.summary-card [data-summary-state]{grid-column:1;grid-row:1}
.summary-card [data-summary-action]{grid-column:2;grid-row:1}
.summary-card [data-summary-link]{display:none}
/* Every figure a row — label left, value right — in the card, in the strip and
   in the band alike (Koen, 11 October 2026: "B voor elke kaart").

   #1912 (Koen, 12 October 2026; end state §3.10): one card, two places. Beside
   the content it is the card of 300 px. Above it — the frame does not hold
   both — it is the band: it fills the content's column, the badge at the left,
   the figures as the same rows side by side, each as wide as its label and its
   value, 32 px between the pairs, the action at the right; what does not fit
   one line runs on to a second. Under 640 px of frame, the strip. The band
   has one reason: a frame under 964 px (#1929). */
.summary-card [data-summary-figures]{grid-column:1/-1;display:grid;grid-template-columns:minmax(0,1fr);gap:8px}
.summary-card [data-summary-figure]{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
@container (min-width:964px){
  .summary-card{grid-template-columns:minmax(0,1fr);padding:16px}
  .summary-card [data-summary-figures]{grid-column:1}
  .summary-card [data-summary-action]{grid-column:1;grid-row:auto;display:flex;align-items:center;gap:8px;border-top:1px solid rgb(var(--c-line));padding-top:12px}
  .summary-card [data-summary-link]{display:block;flex:1}
}
@container (min-width:640px) and (max-width:963.98px){
  .summary-card{grid-template-columns:auto minmax(0,1fr) auto;column-gap:24px;padding:12px 16px}
  .summary-card [data-summary-figures]{grid-column:2;grid-row:1;display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 32px}
  .summary-card [data-summary-action]{grid-column:3;grid-row:1;display:flex;align-items:center;gap:8px;max-width:360px;border-top:0;padding-top:0}
  .summary-card [data-summary-link]{display:block;flex:1}
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
/* #1928 (Koen, 12 October 2026: "het bewerkscherm is leidend" and "gelieve de
   lijnafstand tussen de velden gelijk te zetten aan gezin en aan de personen"):
   read mode keeps the edit grid, with the person card's 4 px between its rows. */
.form-flow[data-mode="read"] .form-grid{row-gap:4px}
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
.data-table tbody[data-collapsed="true"] tr:not([data-group-row]){display:none!important}
.data-table [data-row-link]:focus-visible{outline:none}
.data-table [data-row-link]:focus-visible::after{outline:2px solid rgb(var(--c-blue-600));outline-offset:-3px}
.data-table [data-above-row]{position:relative;z-index:2}
.data-table[data-p1="hide"] [data-p="1"],.data-table[data-p2="hide"] [data-p="2"]{display:none}
@container datatable (max-width:1099px){.data-table[data-p1="auto"] [data-p="1"]{display:none}}
@container datatable (max-width:979px){.data-table[data-p2="auto"] [data-p="2"]{display:none}}
/* #1927: the name stands at its own width, or at what the other columns leave
   of the frame; an optional column that left gives its room back. The sums are
   the macro's (`ui.data_table`). */
.data-table{--dt-o1:var(--dt-p1,0px);--dt-o2:var(--dt-p2,0px)}
.data-table[data-p1="hide"]{--dt-o1:0px}
.data-table[data-p2="hide"]{--dt-o2:0px}
@container datatable (max-width:1099px){.data-table[data-p1="auto"]{--dt-o1:0px}}
@container datatable (max-width:979px){.data-table[data-p2="auto"]{--dt-o2:0px}}
.data-table thead th[data-cell="name"]{width:min(var(--dt-name,100cqw),calc(100cqw - var(--dt-rest,0px) - var(--dt-o1) - var(--dt-o2)))}
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
  .data-table [data-cell="more"]{display:block!important;grid-column:1/-1;grid-row:4}
  /* #1636: a row with an amount AND a date (a registration): the amount keeps
     its place beside the status, the date goes under them, the products last. */
  .data-table tr:has(>[data-cell="amount"])>[data-cell="date"]{grid-column:1/-1;grid-row:4}
  .data-table tr:has(>[data-cell="amount"])>[data-cell="more"]{grid-row:5}
  /* #1915: a moment stands where a date stands. Free text is a line of its
     own after everything else — the place of `more`, which it never shares a
     row with — and an empty one leaves nothing, not even the grid's gap. */
  .data-table [data-cell="moment"]{grid-column:2;grid-row:3;align-self:center}
  .data-table tr:has(>[data-cell="amount"])>[data-cell="moment"]{grid-column:1/-1;grid-row:4}
  .data-table [data-cell="text"]{display:block!important;grid-column:1/-1;grid-row:4}
  .data-table tr:has(>[data-cell="amount"]):has(>[data-cell="date"],>[data-cell="moment"])>[data-cell="text"]{grid-row:5}
  .data-table [data-cell="text"]:empty{display:none!important}
  .data-table [data-group-row]{align-items:center;padding:0 12px}
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
/* #1899: a group of CARDS — every item a card of the form flow, 16 px apart
   like the flow's own cards, no line between them (a card has its border). */
.group-cards,.group-rows--cards{display:grid;gap:16px;min-width:0}
.group-rows--cards:not(:has(*)){display:none}
.group-rows--cards>[data-group-row]+[data-group-row]{margin-top:0;padding-top:16px;border-top:1px solid rgb(var(--c-line))}
.group-row--card>.group-body>[data-row-title-line]{margin-bottom:4px}
/* #1899: the plain child list (a person's e-mail addresses) — no rule at its
   left, no line between its rows, and the tag in a slot of one width so the
   fields are equally wide whatever a row carries. */
.group-child.group-child--plain{margin-top:0;padding-left:0;border-left:0}
.group-rows.group-rows--plain>[data-group-row]+[data-group-row]{margin-top:8px;padding-top:0;border-top:0}
@container (min-width:532px){
  .group-child--plain .group-row--simple.group-row--one{grid-template-columns:minmax(0,1fr) 9.5rem}
  .group-child--plain .group-row--edit.group-row--simple.group-row--one{grid-template-columns:minmax(0,1fr) 9.5rem 44px}
  .group-child--plain .group-row--simple.group-row--one>[data-row-one-tag],.group-child--plain .group-row--simple.group-row--one>[data-row-tag]{grid-column:2}
  .group-child--plain .group-row--edit.group-row--simple.group-row--one>[data-row-menu-holder]{grid-column:3}
}
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
.group-row--edit.group-row--simple.group-row--one>[data-row-one-tag],.group-row--edit.group-row--simple.group-row--one>[data-row-tag]{align-self:center}
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
.record-bar{position:sticky;bottom:0;z-index:20;display:flex;align-items:center;gap:8px;min-height:64px;margin-top:8px;padding:0 16px;background:rgb(var(--c-surface));border-top:2px solid rgb(var(--c-line))}
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
  .record-bar{display:grid;grid-template-columns:1fr 1fr;gap:8px;min-height:121px;margin:8px -16px 0;padding:11px 16px 12px}
  .record-bar-save{grid-column:1/-1;grid-row:1}
  .record-bar-delete{grid-column:1;grid-row:2;justify-self:start;margin:0}
  .record-bar-cancel{grid-column:2;grid-row:2;justify-self:end;margin:0}
  /* #2120: a second save takes a full line under Opslaan; Verwijderen and Annuleren drop one line. */
  .record-bar-extra{grid-column:1/-1;grid-row:2}
  .record-bar:has(.record-bar-extra){min-height:173px}
  .record-bar:has(.record-bar-extra) .record-bar-delete,.record-bar:has(.record-bar-extra) .record-bar-cancel{grid-row:3}
  .form-flow:has(>.record-bar){padding-bottom:24px}
}
/* CR-11 block 10 (#1562), §3.15: a field the Assistent proposes a value for —
   a blue line and the brand tint on its control, the note under it. The same
   look once applied; the note's words say which of the two it is. */
[data-field][data-proposed] :is(input:not([type=hidden]),select,textarea,.de-surface),[data-field][data-proposal-applied] :is(input:not([type=hidden]),select,textarea,.de-surface){border-left:3px solid rgb(var(--c-blue-600));background-color:rgb(var(--c-blue-50))}
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
  /* #1899: a row that is a line of text and no field (a membership year) keeps
     its menu beside it — there is no label to give the first row to. */
  .group-row--edit.group-row--simple[data-row-inline]>.group-body{grid-column:1/3;grid-row:1}
  .group-row--edit.group-row--simple:not(.group-row--handle)>.relative{grid-column:3}
  .group-row--edit.group-row--simple.group-row--one{grid-template-columns:minmax(0,1fr) 44px;align-items:center;min-height:44px}
  .group-row--edit.group-row--simple.group-row--one>[data-row-one-tag],.group-row--edit.group-row--simple.group-row--one>[data-row-tag]{grid-column:1;grid-row:1;justify-self:start}
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

   A long menu (#1917; Koen, 15 and 16 October 2026, "a" and "5a"): from 768 px
   the header is a row that wraps, CSS only. The account stands fixed at the
   top right, and every row keeps its room free (`--site-account-room`: the
   account's widest, a first name of 12rem with its arrow, or "Inloggen"). From
   1 200 px the pages stand beside the logo while they fit; when they do not,
   they move to a row of their own under it, and wrap to a third row if they
   must. The logo never gives up its width for them, and the page never
   scrolls sideways. With a short menu the header is what it was.

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
/* CR-17 phase 6 (#2024): a page under a section, indented under it in the drawer. */
.site-drawer-sub{padding-left:36px;font-size:15px}
.site-drawer-row[aria-current="page"]{background:rgb(var(--c-blue-50));color:rgb(var(--c-brand));font-weight:600;text-decoration:underline;text-underline-offset:4px;text-decoration-thickness:2px}
.site-footer{background:rgb(var(--c-surface))}
/* #1654 (CR-11 Q85): no line above the row — the ground changing from grey to
   white is the transition — and 24 px of air above and under the row on a
   phone, 32 px from 768 px; three columns of one width from 768 px. The air
   from the last content to the footer's ground is the same as the air inside
   it: the content's own padding under it (24 / 32 px), and no margin on the
   footer (it was 48 / 64 px on top of that padding). */
body[data-shell="site"]>main{padding-bottom:24px}
.site-footer-core{padding-block:24px}
.site-footer-core[data-bell]{padding-bottom:88px}
.site-footer-row{display:grid;grid-template-columns:minmax(0,1fr);gap:32px}
.site-footer-row h2{font-size:18px;line-height:1.2;margin-bottom:12px;color:rgb(var(--c-ink))}
.site-legal{margin-top:24px;padding-top:16px;border-top:1px solid rgb(var(--c-line));font-size:14px;line-height:24px;color:rgb(var(--c-ink-soft));overflow-wrap:anywhere}
.site-legal a{text-decoration:underline;text-underline-offset:4px}
.site-sponsor{display:flex;align-items:center;max-width:144px;height:64px}
.site-sponsor img{max-width:144px;max-height:64px;width:auto;height:auto;object-fit:contain}
.site-sponsor:focus-visible{outline:2px solid rgb(var(--c-focus));outline-offset:2px;border-radius:6px}
@media (min-width:768px){
  .site-container{width:calc(100% - 48px)}
  .site-header-grid{--site-account-room:15rem;position:relative;display:flex;flex-wrap:wrap;align-items:center;column-gap:16px;height:auto;min-height:112px;padding-right:var(--site-account-room)}
  .site-header-grid:has([data-sign-in]){--site-account-room:6.5rem}
  .site-brand{flex:0 1 auto;min-height:64px}
  .site-menu-button{display:none}
  .site-pages{display:flex;flex-wrap:wrap;align-items:center;gap:4px;flex:1 0 100%;min-height:48px;min-width:0}
  .site-account{position:absolute;top:10px;right:0;max-width:var(--site-account-room);display:flex;align-items:center;justify-content:flex-end;gap:8px}
  body[data-shell="site"]>main{padding-bottom:32px}
  .site-footer-core{padding-top:32px}
  .site-legal{margin-top:32px}
  .site-footer-row{grid-template-columns:repeat(3,minmax(0,1fr))}
  /* #1664 (Z1): the sponsors end on the container's right edge. Their column is
     the LAST of the row, whichever columns are there, and as wide as the
     others (#1654); the block in it — the heading over the logos — is as
     wide as its logos and stands at the column's right end. */
  .site-footer-sponsors{grid-column-end:-1}
  .site-footer-sponsors>div{width:fit-content;max-width:100%;margin-left:auto}
}
@media (min-width:1200px){
  .site-container{width:calc(100% - 64px)}
  .site-header-grid{column-gap:24px;min-height:80px}
  .site-brand{flex:0 0 auto;min-height:80px}
  .site-brand img{height:64px}
  .site-pages{flex:0 1 auto;margin-left:auto}
  .site-account{top:18px}
  .site-footer-row{gap:48px}
}
/* ── CR-17 (#1671, slice 4): the prose rules — `.prose-raak`, one class ───────
   Both shells lost their hand-written `.cms-content` blocks (site_base and
   admin_base carried near-identical sets — two places for one fact): every
   wrapper that styles rendered content now carries `.prose-raak`, and the
   rules live HERE. The link colour is the shell's own token (`--link`) —
   ONE set, both shells the brighter tint (Koen, 10 October 2026,
   "Akkoord"; the ocean stays the headings' colour). The table rules
   are new (measured in phase 0: nothing styled a table); on a phone a
   table's block scrolls inside itself while the page does not (CR-11 Q14's
   declared exception) — `width:max-content` keeps her natural width, the
   `max-width` brings the scrollbar the moment she is wider than her
   column. The figure rules (radius, shadow, placements, the <640 px
   stack) live in `prose-figures.css` — ONE source with the editor. */
.prose-raak h1{font-size:1.5rem;font-weight:700;color:var(--brand-ocean);margin:1rem 0 .5rem}
.prose-raak h2{font-size:1.25rem;font-weight:700;color:var(--brand-ocean);margin:1rem 0 .5rem}
.prose-raak .prose-large{font-size:1.25rem;font-weight:700;line-height:1.3}
.prose-raak h3{font-size:1.1rem;font-weight:600;margin:.75rem 0 .25rem}
.prose-raak h4{font-weight:600;margin:.5rem 0 .25rem}
/* The editor's surface shows the three heading levels at the sizes it showed
   when they were stored as h1–h3 (CR-32 R21: Kop, Subkop and Kleine kop are
   h2–h4 now), so what the author sees does not shrink a step. */
.prose-raak.de-surface h2{font-size:1.5rem;font-weight:700;margin:1rem 0 .5rem}
.prose-raak.de-surface h3{font-size:1.25rem;font-weight:700;color:var(--brand-ocean);margin:1rem 0 .5rem}
.prose-raak.de-surface h4{font-size:1.1rem;font-weight:600;margin:.75rem 0 .25rem}
.prose-raak p{margin:.5rem 0;line-height:1.6}
.prose-raak ul{list-style:disc;padding-left:1.5rem;margin:.5rem 0}
.prose-raak ol{list-style:decimal;padding-left:1.5rem;margin:.5rem 0}
.prose-raak li{margin:.25rem 0}
.prose-raak a{color:var(--link);text-decoration:underline}
/* #1567: a form button placed by the form placeholder is the kit button, not a text link. */
.prose-raak [data-form-button] a{color:var(--ink);text-decoration:none}
.prose-raak strong,.prose-raak b{font-weight:700}
.prose-raak em,.prose-raak i{font-style:italic}
.prose-raak del,.prose-raak s{text-decoration:line-through}
.prose-raak blockquote{border-left:3px solid var(--line);padding-left:1rem;color:var(--ink-soft);margin:.5rem 0}
.prose-raak pre{background:var(--surface-2);border:1px solid var(--line);border-radius:.375rem;padding:.5rem .75rem;margin:.5rem 0;font-family:ui-monospace,monospace;font-size:.875em;white-space:pre-wrap}
.prose-raak code{font-family:ui-monospace,monospace;font-size:.875em}
.prose-raak img{max-width:100%;height:auto;border-radius:.5rem;margin:.5rem 0}
/* Drie maten voor een pagina-afbeelding (#1207), relatief aan de kolom. */
.prose-raak img.cms-beeld-klein{max-width:33%}
.prose-raak img.cms-beeld-half{max-width:50%}
@media (max-width:640px){
  .prose-raak img.cms-beeld-klein,.prose-raak img.cms-beeld-half{max-width:100%}
}
.prose-raak hr{border-top:1px solid var(--line);margin:1rem 0}
/* CR-17 phase 2 (#1679, C4.13 — beslissing 14): the table's look. One 1 px
   line between rows, no vertical lines, no bands; the header row the
   author's own on surface-2, semibold; cells 12/16 px, text 14 px. Decided
   with the look (Koen, 11 October 2026): NO line under a wide table — no
   script on the public site — and NO right-aligned numbers; everything
   stays left.
   A table stays a table at every width, and what holds her scrolls (the
   design review's choice, the master CLI's comment of 11 October 2026):
   she fills her holder and her lines run to her holder's edge; the moment
   her content is wider, the HOLDER scrolls — one rule on `.prose-raak`
   covers the page's container, the home intro and the newsletter archive
   alike. The `table>tr` rule of the first cut is gone: measured, every
   parsed table carries her rows in a tbody (a bare `<table><tr>` is
   parsed with section "body"), so nothing ever matched her.
   And the holder gives her focus ring room (review S1 of 11 October
   2026): overflow clips, so a link on the holder's left edge lost her
   ring's left side. The room is INSIDE the holder — 2 px padding, won
   back with a 2 px negative margin, so every visible position stays
   where she was. The page editor's surface keeps her own box (review A1 of
   12 October 2026): her class sits on the element herself (`de-surface`), and
   the negative margin pushed her 2 px out of line with the toolbar above
   her. */
.prose-raak{overflow-x:auto}
.prose-raak:not(.de-surface){margin-inline:-2px;padding-inline:2px}
.prose-raak table{border-collapse:collapse;width:100%;margin:.5rem 0;font-size:.875rem;line-height:1.5}
.prose-raak :is(th,td){border-bottom:1px solid rgb(var(--c-line));padding:.75rem 1rem;text-align:left;vertical-align:top}
.prose-raak tbody tr:last-child :is(th,td){border-bottom:none}
.prose-raak th{font-weight:600;background:rgb(var(--c-surface-2))}
/* CR-17 phase 2 (#1679, C4.13): the columns, the button and the callout.
   Columns: two sub-documents of equal width, 32 px between, top-aligned
   (middle — `prose-columns--middle`, the adapter's derived case — when
   one column holds only a figure); under 640 px ONE column, the text
   before the image. The button: the kit's button, left under its text,
   on her label above 40 px, full width 44 px on a phone. The callout:
   text only, a neutral surface with the line and radius 14, 16 px
   inside — no title, icon or colour stripe. */
.prose-columns{display:grid;grid-template-columns:1fr 1fr;gap:32px;align-items:start;margin:.5rem 0}
.prose-columns--middle{align-items:center}
.prose-raak .prose-column>*:first-child,.prose-column>.prose-raak>*:first-child{margin-top:0}
/* CR-32 #2101: a columns block that holds a data block is drawn by the page template
   (outside the prose, with this same grid); a column's data block starts on its top. */
.prose-column>.page-data:first-child{margin-top:0}
/* The ratio of the two columns: a fixed choice, `equal` being the absent attribute. Under
   640 px the columns stack in source order whatever the ratio. */
.prose-columns--wide-narrow{grid-template-columns:minmax(0,3fr) minmax(0,2fr)}
.prose-columns--narrow-wide{grid-template-columns:minmax(0,2fr) minmax(0,3fr)}
@media (max-width:639.98px){
  /* stretch, not the grid's align-items:start: in a column flex that
     start means "shrink to content", and a stacked column must take
     her full width (a button inside her follows). */
  .prose-columns{display:flex;flex-direction:column;gap:24px;align-items:stretch}
  .prose-columns .prose-column:has(figure){order:2}
}
.prose-raak a.prose-button{display:inline-flex;align-items:center;justify-content:center;border-radius:.5rem;padding:.625rem 1rem;margin:.5rem 0;font-weight:600;font-size:.875rem;line-height:1.25rem;text-decoration:none}
.prose-raak a.prose-button--primary{background:var(--primary);color:#fff}
/* Review S2 of 12 October 2026: her border made the secondary 2 px taller
   beside a primary one (42 against 40) — her padding gives back what her
   border takes, so the two stand one height. Two buttons after each other
   touched: 8 px between them, on a wide screen only (on a phone each is a
   full row of her own, and a left margin there would push her out). */
.prose-raak a.prose-button--secondary{border:1px solid rgb(var(--c-control-line));padding:calc(.625rem - 1px) 1rem;color:var(--ink)}
@media (min-width:640px){
  .prose-raak a.prose-button + a.prose-button{margin-left:.5rem}
}
.prose-callout{border:1px solid rgb(var(--c-line));border-radius:14px;background:var(--surface-2);padding:16px;margin:.5rem 0}
/* CR-17 phase 2, the cards (C4.9, C4.13): a block of link cards, 16 px
   between them. Two per row for one or two cards — so a lone card is as wide
   as a card in a row of two — and three per row from the third card on; the
   last row starts at the left and is never stretched (a grid, not a flex
   row). One per row on a phone and inside a column. The count is read from
   the block itself (`:has`), so the site and the editor cannot disagree.
   A card: the public card's line and radius 14, 16 px inside; an icon in a
   44 px tile on the soft brand tint (radius 6) or a picture of 16:9 from edge
   to edge; the title 18 px, the line 16 px and the labels 12 px in the soft
   ink. The whole card is the link: the title's link is stretched over it, so
   there is one link, and its focus ring (3 px) stands around the card. No
   hover reveal — a phone has no hover. */
/* A page's gallery (CR-32 R20): the photos of one album, two across on a phone and
   as many as fit from 160 px on a wide screen; the pictures carry the prose
   rules' radius and shadow like every picture of a page. */
.prose-gallery{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:.5rem 0}
@media (min-width:768px){.prose-gallery{grid-template-columns:repeat(auto-fill,minmax(180px,1fr))}}
.prose-raak .prose-gallery img{display:block;width:100%;aspect-ratio:4/3;object-fit:cover;margin:0}
.prose-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:.5rem 0}
.prose-cards:has(>:nth-child(3)){grid-template-columns:repeat(3,minmax(0,1fr))}
.prose-column .prose-cards,.prose-column .prose-cards:has(>:nth-child(3)){grid-template-columns:minmax(0,1fr)}
@media (max-width:639.98px){
  .prose-cards,.prose-cards:has(>:nth-child(3)){grid-template-columns:minmax(0,1fr)}
}
.prose-card{position:relative;display:flex;flex-direction:column;align-items:flex-start;gap:4px;border:1px solid rgb(var(--c-line));border-radius:14px;background:#fff;padding:24px;overflow:hidden}
.prose-card:has(a.prose-card-title:focus-visible){outline:3px solid rgb(var(--c-blue-600));outline-offset:2px}
.prose-card-icon{display:grid;place-items:center;width:44px;height:44px;border-radius:6px;background:rgb(var(--c-blue-50));color:rgb(var(--c-brand));margin-bottom:8px}
.prose-raak img.prose-card-picture{display:block;width:calc(100% + 48px);max-width:none;margin:-24px -24px 8px;aspect-ratio:16/9;object-fit:cover;border-radius:0;box-shadow:none}
.prose-raak .prose-card-title{font-size:20px;line-height:1.35;font-weight:600;color:var(--ink);text-decoration:none}
.prose-raak a.prose-card-title::after{content:"";position:absolute;inset:0}
.prose-raak a.prose-card-title:focus-visible{outline:none}
.de-gallery{margin:.5rem 0;padding:.75rem 1rem;border:1px dashed rgb(var(--c-line));border-radius:8px;background:rgb(var(--c-surface-2));font-size:.875rem}
.prose-card-number{font-size:12px;font-weight:400;letter-spacing:.06em;color:rgb(var(--c-ink-soft))}
.prose-card-text{margin:0;font-size:16px;line-height:1.5;color:rgb(var(--c-ink-soft))}
.prose-card-line{font-size:16px;line-height:1.5;color:rgb(var(--c-ink-soft))}
/* A value in the page editor (CR-32 R19): a chip with the value it has now; on the
   site the value is plain text, so there is no public rule. */
.de-surface .prose-value{display:inline-block;max-width:100%;padding:0 .4rem;border:1px solid rgb(var(--c-blue-200));border-radius:6px;background:rgb(var(--c-blue-50));color:rgb(var(--c-blue-700));vertical-align:bottom;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.prose-card-labels{font-size:12px;line-height:1.5;color:rgb(var(--c-ink-soft))}
@media (max-width:639.98px){
  .prose-raak a.prose-button{display:flex;width:100%;min-height:44px}
}
/* ── CR-17 (#1671 slice 4; phase 2 #1679, C4.13 "Where the width lives"):
   ONE container of 1 024 px, CENTRED (the master CLI's comment of
   11 October 2026 is the source until the paragraph stands on `master`),
   with one left line INSIDE her: the text blocks run to at most 768 px,
   the blocks C4.13 names wide (the table, a figure on "volledig", the
   columns and the cards) fill the container. The
   cap names no element types: every direct child is narrow unless the
   wide list says otherwise, so a new text block is narrow without anyone
   remembering her. On a phone the viewport minus her gutters (the shell's
   <main> gives them). */
.doc-page{width:100%;max-width:1024px;margin-left:auto;margin-right:auto}
.doc-page>:not(.prose-raak):not(.prose-hero):not(.page-data):not(.prose-columns){max-width:768px}
/* A data block of a module (the activity list) stands beside the prose, in the
   container's full width, outside the prose rules (CR-32 phase 5). */
.page-data{margin:1rem 0}
.page-data:last-child{margin-bottom:0}
/* The album card is ONE card of the photo page, not a banner: as wide as one there
   (CR-32 R14), left on the container's line. */
.page-data>[data-photo-card],.page-data>[data-photo-moving]{max-width:24rem}
.doc-page .prose-raak>*:not(table):not(.prose-figure--full):not(.prose-columns):not(.prose-cards):not(.prose-section):not(.prose-gallery){max-width:768px}
/* ── CR-32 (F1–F3, F5): a band that spans the page, with the container put back
   inside it. The band breaks out of `.doc-page` by the width the container
   leaves on each side (margin) and takes the same width back as padding, so
   its content stands exactly where the text above it stands — one left line,
   at every width — and no wrapper is needed. `.prose-section` is a section of
   the document, `.prose-hero` the opening of a page (the template's); the
   tone is a name, the pixels come from the tenant's brand tokens (#1622). The
   body clips sideways: 100vw counts a scrollbar the page does not have. */
body[data-shell="site"]{overflow-x:clip}
.prose-section,.prose-hero{margin-inline:calc(50% - 50vw);padding-inline:calc(50vw - 50%)}
/* `.prose-raak` is the holder a wide table scrolls in (`overflow-x:auto`), and a
   holder clips whatever stands beyond her edge — a band that breaks out of the
   container is cut back to it (seen on a print, not in a measurement: the boxes
   are the right size, the paint is not). A page body that holds a section is
   therefore no holder; her tables become their own (CR-32 F2). A page without a
   section keeps the holder exactly as it was (R11). */
/* ...and what the holder held besides a table — a pasted address with no place to
   break, a long compound word — is held by the text itself: it breaks anywhere
   (inherited), so the document keeps the viewport's width. */
.cms-page:has(>.prose-section){overflow-x:visible;overflow-wrap:anywhere}
.cms-page:has(>.prose-section) table{display:block;max-width:100%;overflow-x:auto}
.prose-section{padding-block:2.5rem}
.prose-section>:first-child{margin-top:0}
.prose-section>:last-child{margin-bottom:0}
.doc-page .prose-section>*:not(table):not(.prose-figure--full):not(.prose-columns):not(.prose-cards):not(.prose-gallery){max-width:768px}
.prose-section--tint,.prose-hero--tint{background:rgb(var(--c-blue-50))}
/* The accent tokens belong to the public shell; the page editor (admin shell)
   shows the band in the platform's own accent, so the fallback is the same one. */
.prose-section--accent,.prose-hero--accent{background:rgb(var(--c-accent,238 193 94));color:rgb(var(--c-on-accent,37 44 53))}
.prose-raak .prose-section--accent :is(h2,h3,h4){color:inherit}
.prose-section-eyebrow,.prose-hero-eyebrow{margin:0 0 .5rem;font-size:.8125rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:rgb(var(--c-brand))}
.prose-section--accent .prose-section-eyebrow,.prose-hero--accent .prose-hero-eyebrow{color:inherit}
.prose-hero{padding-block:3rem;margin-bottom:2rem}
/* In the editor a section is a framed band, not a full-bleed one: the surface
   is already the page's width, and her bar (tone, eyebrow) sits above her blocks. */
.de-surface .prose-section{margin-inline:0;padding:1rem;border:1px dashed rgb(var(--c-line))}
.de-section-bar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:.75rem;font-size:.875rem}
.de-section-bar select,.de-section-bar input{min-height:36px;padding:0 .5rem;border:1px solid rgb(var(--c-line));border-radius:6px;background:rgb(var(--c-surface));color:rgb(var(--c-ink))}
.de-section-eyebrow{flex:1 1 12rem;min-width:0}
.de-section-remove{min-height:36px;padding:0 .75rem;border:1px solid rgb(var(--c-line));border-radius:6px;background:rgb(var(--c-surface));color:rgb(var(--c-ink));cursor:pointer}
.de-section-remove:hover{background:rgb(var(--c-surface-2))}
.de-section-remove:focus-visible{outline:2px solid rgb(var(--c-blue-600));outline-offset:2px}
.prose-hero-lead{margin:1rem 0 0;max-width:768px;font-size:1.25rem;line-height:1.5}
.prose-hero-actions{display:flex;flex-wrap:wrap;gap:12px;margin-top:1.5rem}
/* The buttons are the button block's own (`.prose-raak a.prose-button`), so the
   actions carry that class too; the row's gap is the spacing, not the margins. */
.prose-hero-actions.prose-raak{margin-inline:0;padding-inline:0;overflow:visible}
.prose-hero-actions.prose-raak a.prose-button,.prose-hero-actions.prose-raak a.prose-button+a.prose-button{margin:0}
body[data-shell="site"] #main .prose-hero-title{margin:0;font-size:2.25rem;line-height:1.1}
@media (min-width:768px){body[data-shell="site"] #main .prose-hero-title{font-size:3.5rem}}
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
