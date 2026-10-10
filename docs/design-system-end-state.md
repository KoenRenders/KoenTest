# Design system — the end state (CR-11)

**Status:** end state, not yet built. Written on 30 September 2026 as the
target of CR-11 (`docs/change_request_11_gui_redesign_2.md`). The norm
that binds today's code is still `docs/design-system.md`; each section
here names the phase of CR-11 that makes it the norm, and phase 0 of CR-11
folds this document into `design-system.md` section by section as the
phases land. Row numbers in brackets point at the as-is table of CR-11 A2.

**How to read it.** Part 1 is what every screen is made of (tokens). Part 2
is the three layouts every screen is one of. Part 3 is the components those
layouts are composed from, each with its behaviour. Part 4 is the
interaction patterns. Part 5 classifies every existing screen. Part 6 says
what refuses a deviation. A builder reads 2 and 5 to know what a screen is,
3 to build it, 6 to know what will go red.

---

## 1. Tokens

**Folded into `design-system.md`**: §1 on 2 October 2026 (block 1, #1482);
§2.1, §3.7, §3.8, §3.13 (K1, #1555) and §3.9, §3.11, §3.12 (K3, #1557) on
4 October 2026 — into `design-system.md` §2.3, §3.2, §3.4 and P3; §2.2,
§3.1–§3.6, §3.10 (K2, K4–K7), §3.15 (K8), §6 (K9) and §2.5 (P1) on 5 October
2026 — into `design-system.md` §0, §1.2, §1.6, §2.2, §2.3, §2.4, §2.7, §2.11,
§3.4, §5, §7 and §13; §2.6 (P2, P3 and their corrections) on 6 October 2026,
when v2.13.0 reached PROD — into `design-system.md` §7, §2.11 and P12; §2.7
(pilot C) on 7 October 2026, when v2.14.0 reached PROD — into
`design-system.md` §7 and §13. Nothing left to fold. For
block 1: §1.1 → §1.1a there, §1.2 and §1.6 →
§1.2–§1.3, §1.5 → §1.4, §1.4 → §1.6 (the admin frame). This section stays as
the design intent; where the two differ, `design-system.md` says what runs.

### 1.1 Kit tokens and brand tokens — two files

| Kit (the platform's; a second organisation inherits them) | Brand (the tenant's; a second organisation replaces them) |
|---|---|
| the surface scale, the spacing scale, radii, elevation, the widths | the eight brand colours, the two fonts, the wordmark |
| the icon *vocabulary* (verb → glyph) and the one-meaning-per-glyph rule | the icon *set* and its line style (Lucide, 1.75 px today) |
| control shapes and sizes, the button hierarchy, the layouts | photos, posters, the public site's decoration |

`scripts/build-css.sh` reads both; a template names a token, never a
value. (Phase 2. Rows 9, 16; R12.)

**The brand file is tenant settings, not a file** (Koen, 5 October 2026,
after P1 on HDEV): the logo, the header colour (`site_header_color`, built)
and **two colours — the brand colour (headings, links, the primary, the
active navigation; hover, soft tint and focus derived from it) and the
accent colour (the one call to action)** — set per tenant in the tenant
editor with the same contrast guard as the header colour, applied as CSS
variables on the public `<body>` the way the header colour is. **The default
without a setting is the Atelier palette** below, the platform's neutral
house style; Raak Millegem sets its own house-style blue and yellow in its
settings (Koen found PROD's colours nicer "because they belong to Raak",
and chose to keep Atelier as the default rather than make Raak's colours
every tenant's). The back office stays Atelier for every tenant. [Q68;
issue b2 of pilot B, v2.13.0]

**The first brand file is decided** (block 1, Koen, 2 October 2026, choosing
between ChatGPT's two directions on the same frame): palette *Atelier* — a
muted brand blue `37 78 115` (hover `25 57 88`), ink `33 45 58` and soft ink
`83 99 115`, a cool grey ground `244 246 248` with a second surface
`240 243 246`, lines `216 224 230` and control lines `126 143 158`, a soft brand
tint `230 239 247` for the active navigation row and the inset, focus
`25 95 157`, and one warm accent `238 193 94` (yellow, text `37 44 53`) that
the public site uses for its one call to action and the back office does not
use at all; danger `166 37 37`, warning **`194 65 12`** (a real orange — ChatGPT's muted `116 77 9` did not read as "something to do" on an open amount; Koen, 2 October 2026, block 3; contrast on white about 4.6 : 1, measured again at the build), success `24 103 72`, each
with a soft tint. Every value is an RGB triplet, as the tokens are today, and
the eight official brand colours of the house style are no longer the
palette: Koen let the house style go overboard for a calmer, professional
workplace (CR-11 B10, 2 October 2026). The sidebar is **light** (white, ink
`50 66 81`, active row on the brand tint with a brand-blue text) — not a dark
band; the dark green sidebar of direction B was rejected. The reference
files are ChatGPT's A files in Koen's project folder (`brief-01-kader/`,
`tokens-a-backoffice.css` and `tokens-a-publiek.css`); the build takes its
values from there and this document is the norm when they differ.

### 1.2 Surfaces — three levels, and nothing else

| Token | What | Text on it | Border |
|---|---|---|---|
| `surface-page` | the page ground, one light grey | `ink` | — |
| `surface-card` | a card, white, radius 10 px in the admin and 14 px on the public site, one soft shadow (`0 1px 2px`, ink at 3.5 %) | `ink` / `ink-soft` | `border-card` |
| `surface-inset` | a block inside a card (a summary line, a read-only group), the brand tint or the second surface, the control radius (6 px) | `ink-soft` | none |

The shell paints `surface-page`; the card macro paints `surface-card`; the
inset is only ever inside a card. The same three on the public site and in
the admin. No `bg-*` class in a domain template. (Phase 2. Row 9.)

**Radius, decided** (block 1, Koen, 2 October 2026): cards 10 px in the back
office, 14 px on the public site; every control (button, field, segment, tab,
navigation row) 6 px; badges and small blocks 4 px; a round badge 999 px. This
replaces the 18 px cards of today and the 12 px the concepts tested (CR-11
Q18 is closed by it).

### 1.3 Spacing — where each step of the scale goes

The scale stays (4 · 8 · 12 · 16 · 24 · 32 · 48 · 64). What is new is the
binding: each step has one use, applied by a macro, never by a template.

| Step | Use | Applied by |
|---|---|---|
| 4 | label to control; icon to its text | `field`, `btn_*` |
| 8 | button padding; gap between toolbar controls' segments | `btn_*`, `status_filter` |
| 12 | field to field inside a section | `form_grid` |
| 16 | card padding; gap between toolbar controls | `card`, `toolbar` |
| 24 | card to card; summary card to content | layouts |
| 32 | section to section inside a form | `section` |
| 48 | header to content on a record page | `record_page` |
| 24 / 32 | page margin on a desktop: 24 px at 1 440 px, 32 px from 1 680 px (block 1, 2 Oct 2026; replaces the 64 px here before) | shells |
| 64 | no use in the frame; kept in the scale for a poster area on the public site | — |

(Phase 2. Rows 2, 23.)

### 1.4 Widths — three, set by the layout

| Layout | Desktop | Phone (< 768 px) |
|---|---|---|
| list page | the full content width beside the sidebar, no `max-w`: a list grows with the screen (block 1 replaces the 1 280 px box here before) | one column, 16 px gutters |
| record page | the full frame; inside it one **reading group** of 768 px form column + 24 px gap + 300 px summary column (1 092 px), **left-aligned against the page margin** — never centred — so a form starts on the same x as a list, the title and the tabs; the space beyond the summary stays empty on a wide screen (Koen, 4 Oct 2026, correcting block 1's "centred when the frame is wider") | one column, 16 px gutters; the summary as a strip under the tabs |
| document page | reading width 768 px, left-aligned like the record page | one column, 16 px gutters |

**These three are the whole scale** (Koen, 8 October 2026, CR-11 Q89, after the sign-in card went 1 248 → 448 → 768 px in two days). A screen that stands alone — the sign-in card, a page with one message and one button, a short admin form — is a document page at 768 px; there is no narrow-card and no short-form width. The public site adds one: its container of 1 024 px with text at 768 px (CR-17 Q20). A modal and the 300 px summary column are the kit's own and not page widths. A domain template sets no `max-w-*` of its own: the width is the layout's. The 448, 576 and 672 px boxes that exist today move to 768 px in CR-11 phase 5, behind a count that may only fall to zero.

**Two priorities, one kit** (Koen, 2 October 2026): the public site is
designed phone-first — 390 px is where a public page is drawn first and
judged first; the back office is designed desktop-first — 1 440 px is where
an admin screen is drawn first (1 920 is common and must be used), 1 440 px
is the lower bound where everything still fits, and 390 px
is the floor: never broken, the few simple actions (look up, confirm,
check, read) reachable, but not a day's workplace. The rules below hold on
both faces; the priority says which width a block is designed at first.

**Breakpoints follow the content, not two device classes.** In the back
office everything fits down to 1 440 px — the navigation (224 px), the
summary column (300 px), the margins (24 px) and a two-column form; **below 1 440
the sidebar collapses to an icon rail of 64 px** (labels as tooltips, the
same items in the same order) and **below 768 px into a drawer behind a
menu button**; the frame collapses
by content, not by device: the summary card moves above the content when
the content column would drop under 640 px, and the form grid goes to one
column when a half field would be narrower than 260 px, down to the 390 px
floor (Koen, 2 October 2026).
At any width the user may collapse the navigation to an icon rail to gain
room, and the choice is remembered in the browser (`localStorage`; the
default follows the width) (Koen, 2 October 2026). The top bar is 64 px
high and carries, in order: the menu button (phone only), the page title
with room kept for it, the search, the assistant button (§3.15) and the
account button (§3.14); the sidebar carries the wordmark, the workspace
name and the one navigation source in groups (block 1, 2 October 2026). Board desktops are commonly 1 920 px wide (Koen, 2 October 2026): a list
page uses that width, a record page keeps its reading column and summary
with comfortable margins, and no page is a 1 440 px box in a sea of margin.
Concepts and screenshots of the admin are judged at 1 920, 1 440 and 390 px; of the public site at 390, 768 and 1 440 px (Koen, 2 October 2026). A screen never sets `max-w-*` on its root.
Reading width is a property of a form, not of a page: inside the record frame the form column is narrow
and a related-list tab is wide, and the frame does not move. (Phase 2.
Rows 11, 12, 27.)

### 1.5 The icon vocabulary — verb → glyph

A text button carries the lead glyph its verb has here, and never a typed
"+" or arrow; a verb not in the table has no glyph; an icon-only button
exists in row actions and toolbars only, with its `aria-label`.

| Verb | Glyph | Verb | Glyph |
|---|---|---|---|
| add / nieuw | `plus` | download / export | `download` |
| upload / importeren | `upload` | delete / verwijderen | `trash-2` (always red) |
| edit / bewerken | `pencil` | copy / kopiëren | `copy` |
| print / afdrukken | `printer` | send / versturen | `send` |
| filter | `filter` | settings / instellingen | `settings` (the gear, settings and nothing else) |
| open elsewhere (a reference) | `arrow-up-right` | close | `x` (a toast, a modal, a panel — never delete) |
| more / ⋯ | `ellipsis` | the assistant | `sparkles` (with the word "Assistent" beside it in the admin; never the gear) |
| a group that opens or closes (navigation, details) | `chevron-down` / `chevron-right` — never the gear, which is settings only | | |

(Phase 2. Rows 16, 20, 34.)

### 1.6 Type

**Decided with block 1** (Koen, 2 October 2026) and **corrected on 5
October 2026 after seeing P1 on HDEV**: **Inter on both shells, headings
included** — the public headings and the activity titles in Fraunces were
"no improvement"; the public site aligns with the back office and keeps
only a somewhat larger scale: a page title 40 px on a desktop and 32 on a
phone, a section heading 24 px, a card title 18 px, all Inter 600 at line
height 1.15. Fraunces (built in P1, #1588) goes again, file and face. Radio
Canada Big leaves with the house style; the logo is the brand image. The scale is the concepts': 13 ·
14 · 16 · 18 · 24 · 30 px (a page title 30 px on a desktop, 28 on a phone;
body 14 px in the admin, 16 px in public reading text; a public hero title
64 px, 44 on a phone). The density is the concepts' too: navigation rows
32 px, buttons 36 px, fields 40 px, a table row about 57 px, a touch target
44 px on a phone, icons 18 px at a 1.75 px stroke; the spacing between a
label and its control, between fields and between cards follows §1.3
unchanged. Before that decision this section read: unchanged from
`design-system.md` §1.2 and §1.2a (Inter body, Radio
Canada Big display, the mobile-first scale), with one correction, measured
against the app and not the concepts (30 Sep 2026): a field label stays
14 px, what `ui.label` renders today (the concepts drew 13 and the review
read 11 — both wrong); a tile's label is 13 px, replacing the 11 px of
today's Betalingen tiles, and comes with the tiles macro; small text
(11–12 px) is for supplementary information only; the kit's smallest step
is 13 px. Radius: see §1.2 — 10 px admin cards, 14 px public cards, 6 px
controls (block 1 closed CR-11 Q18). The record header's title is
`text-3xl`; a section heading inside a form is `text-base font-semibold`;
a repeating group's heading the same, never larger than the section it is
in. (Row 1.)

---

## 2. The three layouts

Every admin screen and every public page extends exactly one. A template
that renders a list, a record or a document without extending its layout is
red. (Phase 2; every screen moves onto its layout in phases 3–5.)

### 2.1 `list_page` — a toolbar over a table

```
┌ shell ────────────────────────────────────────────────────────────┐
│ Title                     [tile] [tile] [tile]   [+ Nieuw] [⚙ Instellingen] │  title row
│ [alle|open|…]  [search…] [filter ▾] [filter ▾]  1–50 van 312 · 50 ▾  [⋯] │  toolbar row
│ ┌ table or cards ─────────────────────────────────────────────┐ │
│ │ row (the whole row is the link)                        [⋯] │ │
│ │ …                                                           │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                        ‹ vorige   volgende ›      │  bottom navigation
└───────────────────────────────────────────────────────────────────┘
```

- **Title row:** the title (`h1`); at its right the **key figures** inline
  (figure and label as plain text, thin dividers between them, no card,
  **not clickable** — the figures are read, the toolbar's status filter filters;
  block 2, Koen, 2 October 2026, replacing "each a filter"); then **one
  primary button, "+ Nieuw <item>"**, or none (Betalingen). Nothing else:
  every secondary action of the screen — export, import, "Instellingen" —
  lives under the toolbar's `⋯`, on a desktop as on a phone (block 3, Koen,
  2 October 2026: consistency over one click — "afhankelijk van hoe je het
  gebruikt werken dingen wel of niet, ik word daar gek van"); no link to
  another module, no explanation line, no breadcrumb (the menu shows the
  place). [31, 34, 35, 36, 45]
- **Toolbar row:** the same five things in the same order at every width
  — the status filter at the left (§3.13); the search, growing; one
  **Filters** button; the count "x–y van n" with the page size (25 · 50 ·
  100); `⋯` with the screen's secondary actions. One row on a desktop; three
  on a phone (status · search · count with `⋯`). [6, 45]
- **The list:** in the admin always a **table** (a picture is a thumbnail
  column); cards only on the public site and in the media library. Sortable
  columns as the norm, a column chooser under `⋯`; no horizontal scrolling
  ever — columns fit, secondary ones hide as the width shrinks, rows stack
  on a phone. A card or row shows only what applies to that record —
  omitted, not zeroed. [5, 11, 36, P6] **Decided with block 4** (Koen, 2
  October 2026, on ChatGPT's brief-04 answer): the head 36 px, `ink-soft`
  on `surface-2`, a sortable column a link with a double arrow, the active
  one a single arrow in its direction, `aria-sort` on it only, numbers and
  amounts right-aligned with tabular digits, "Sorteren" under `⋯` on a
  phone; a sort keeps search, filters and page size and goes to page 1;
  **columns hide by list width** in a fixed order per list (Betalingen:
  Ontvangen first, then Context; Leden: Lidjaar; Wijzigingen: Details,
  then Uitgevoerd door), and **the column chooser** under `⋯` → Kolommen
  gives each optional column Automatisch / Tonen / Verbergen, the choice
  carried in the URL like search and filters, Automatisch the default;
  **on a phone one continuous table** with dividers, no separate cards —
  a payment row: name + reference, context, badge + amount on one line,
  `⋯` top right (about 153 px); **status is a coloured badge** (Openstaand
  on `warning`, Betaald / Vereffend on `success`), the row itself never
  coloured; **a refund is a negative amount** and nothing else marks it;
  **inside a registration group the first booking is the parent row and
  every following booking is indented with "↳"** and carries its kind and
  method in `ink-soft` under the context ("Terugbetaling · Overschrijving"
  — today's coupling, kept on Koen's word), the quiet "Totaal inschrijving"
  row under a group of more than one booking, no `tfoot`, no list total;
  **Bedrag is never coloured, a Saldo that is not zero is `warning`,
  positive and negative, on the row and in the sum row**, zero in ink —
  red is for delete and errors and nothing else; **the empty state** says
  "0–0 van 0" and one sentence naming the filter or search that caused it,
  with the create button where one exists.
- **The row is the way in:** click it and the record page opens; the whole
  row is the target (a link in the first cell with its click area over the
  row — no nested anchors; a reference inside the row is its own link),
  with hover on `surface-2` and a focus ring; on a phone the whole stacked
  row, 44 px high at least. "Bewerken" is not a row action. **One row
  action may be visible** — the positive action of the row's state
  ("Bevestig" on an open booking), a secondary 32 px button in the actions
  column beside `⋯`, the cell left empty where the row has none so the `⋯`
  of every row aligns; the page keeps one primary — and `⋯` holds the rest:
  quick state changes, "open the registration", duplicate, delete last
  after a divider in red (block 4, Koen, 2 October 2026; this replaces
  "two or three inline plus ⋯"). [26]
- **Bottom:** the page navigation from the same pager macro; hidden when
  everything fits. [6]
- **Totals** live in the tiles and nowhere else. [10]
- **Empty state:** one sentence and, when a create exists, the create
  button repeated. [§2.8 of the current norm]
- **Target:** on a 1080 px screen the first row sits in the top third. [45]

### 2.2 `record_page` — one frame, the form in a column

```
┌ shell ────────────────────────────────────────────────────────────┐
│ ‹ Alle activiteiten                                                │  the way back
│ Title  [status] [badge]                          [Primary] [Acties ▾] │  record header
│ date · time · place · household ↗                                  │  facts line
│ ┌ Gegevens │ Inschrijvingen (23) │ Betalingen (23) ─────────────┐ ┌ summary ─┐ │
│ │        ┌ form column, reading width ┐                          │ │ state    │ │
│ │        │ Section heading            │                          │ │ 3 figures│ │
│ │        │ [field    ] [field    ]    │                          │ │ action   │ │
│ │        │ [field full             ]  │                          │ └──────────┘ │
│ │        │ Repeating group     [+]    │                          │              │
│ │        │  ≡ row …              [⋯]  │                          │              │
│ │        │ ▸ Externe koppelingen (2)  │                          │              │
│ │        └────────────────────────────┘                          │              │
│ └─────────────────────────────────────────────────────────────────┘              │
│                                     [Verwijderen]      Annuleren  [Opslaan]      │  action bar (edit mode)
└───────────────────────────────────────────────────────────────────┘
```

- **The way back** on the first line, to the list it came from **as it was
  left** — the same filter, search, sort and page: the list's state is its
  URL, a row's link carries it, and the layout returns to it (a local path
  only). **It names its origin** (block 5, Koen, 3 October 2026): "‹
  Activiteiten" from the list, "‹ Betaling van Emma Vermeulen" from a jump
  link on a booking, "‹ Zoekresultaten" from the search, the entity's list
  name when opened from nowhere; the navigation layer hands `return_to` and
  its label to the record macro, never the browser's back. 14 px, brand
  tint, `chevron-left`, a 28 px target on a desktop and 44 on a phone. A
  screen never writes this link itself. [28, 57]
- **The record header:** the title with its badges on the title line,
  status first; the facts line under it, every reference a jump link; at
  the right the screen's one primary and one "Acties ▾" menu holding the
  rest (photos, Design Studio, print, delete…). Never a button named after
  the fields it edits. [39, 29, 20]
- **In edit mode a record with a composite repeating group takes the whole
  reading group** — 1 092 px on a desktop, the summary card as the strip
  above the form, the way K8 does it beside the Assistent panel; **every
  full-width field, the text areas included (Omschrijving, interne nota),
  fills the wider column** — the 768 px cap on long text fields that K5c
  built left a gap beside the Omschrijving and went (Koen, 5 October 2026);
  only rich text keeps the reading width, when it comes; read
  mode, Opslaan and Annuleren return to 768 px with the card at the right
  (Koen, 5 October 2026, after K5 on HDEV: "zeer veel ruimte verloren",
  "smaller dan vroeger"). [Q67]
- **The summary card** at the right of the content column, `max-w-xs`:
  the state, two or three figures, the main action; on a phone a compact
  strip under the tabs, above the content. **Only on the Gegevens tab**
  (block 8, Koen, 4 October 2026): a list tab — Personen, Inschrijvingen,
  Betalingen — has no card and no strip, so the list starts directly under
  the tabs at the full width; the record's figures are read on Gegevens.
  [25]
- **The tabs:** "Gegevens" first, then the related lists in the same order
  on every entity (Inschrijvingen · Betalingen · …), each with its count.
  A related-list tab is the list layout in its **embedded rendering**: no
  page header, no figures, no summary card, one toolbar row, the table;
  **the row is the way in**, as on every kit table (K2): a click opens the
  record page, where one reads and edits — **no unfold in place** (block 8
  had a read-only unfold with "Inschrijving openen ↗"; Koen, 5 October
  2026, after K6 on HDEV: the row, the unfold and the page showed the same
  data three times and only the third could edit; the same for the payments
  rows on a record's tab, which open the booking page of #1574). A registration row
  carries name · contact (e-mail and mobile stacked) · date · products ·
  **Bedrag** · **Saldo** (warning tone when ≠ 0) · status · one row action
  plus `⋯` with **"Inschrijving openen"** and **"Betaling openen"** (jumps to the registration page and to the booking page of #1574) among its items (Koen, 5 October 2026); the answers live on the record page (in the list at most a count
  that jumps there). Registrations are **one table with a collapsible group row per
  component** (chevron, name, count, `⋯` with Exporteren and Antwoorden),
  per activity on the household with a jump link in the group row (Q41).
  The header, tabs and summary do not move between tabs; only the content
  column is narrow or wide. [19, 27, 29, 26]
- **Read mode** shows data and navigation, nothing that edits: every
  field the editor has, in the same sections and order, empty ones as "—",
  a yes/no in plain words ("Enkel leden: ja") — not as a disabled control;
  no add buttons, no drag handles, no row menus until "Bewerken". [7]
  **Read mode shows facts, not a labelled form** (Koen, 10 October 2026, on
  the household record, Q&A 03: "a, maar ook niet ingevulde velden toch
  tonen — ik wil dit ook zo in de publieke website"): a field of a
  conventional kind — e-mail, mobile, phone, address, date of birth — shows
  its icon instead of its label, on one wrapping line per person, an empty
  one as the icon with "—"; a field without a convention (a date that needs
  its meaning, a free text) keeps its label. Edit mode keeps the labelled
  grid. Which fields of a screen are conventional is settled per roll-out
  slice, on the concept (Q&A 03, point 6). The household read page went from
  1 503 px to 924 px at 1 440 px with it.
  **Nothing folds on a record** (same answer, point 2): a composite group
  row stands open in read and in edit mode; the `fold` of `group_row` is not
  used on a record page. The same on Mijn gezin.
  **A child list of one field is lines under a label, not a framed group**
  (point 3, shaped by Koen on the concept the same day): a label like the
  fields' ("E-mailadressen") with the small secondary "+ E-mailadres" at its
  right end; under it one row per address — the field, the *hoofdadres* tag
  on the primary one, and the kit's ⋯ with *Verwijderen* and *Maak
  hoofdadres* — the simple `group_row` without the group's frame and title;
  no icon in edit mode. The framed repeating group stays for what is a group
  (the components of an activity).
- **A new record** is the same page in edit mode, empty: "+ Nieuwe
  activiteit" opens it, Opslaan creates, Annuleren leaves nothing behind; no
  start screen with a few fields (Koen, 6 October 2026; the Assistent proposes
  there as on an existing record).
- **"Bewerken"** (the primary, or the first action) turns the whole form
  into the editor: the same sections, the same order, every datum in its
  recognisable place — edit mode may take more room for inputs, help and
  validation, but nothing changes section or order; one save at the
  bottom; leaving with changes warns. Separate saves only for sub-records with their own
  lifecycle (a payment, a registration line, a membership). [14, 22]
- **The action bar:** at the bottom of the form column; "Verwijderen" at
  the far left as a red text action (or in "Acties ▾"), "Annuleren" as a
  text button, "Opslaan" as the one filled primary; `sm`; sticky at the
  bottom on a phone. [22, 46]

### 2.3 `document_page` — for a long text no rule can refuse

The meeting, the CMS page. Reading width; the same way back and record
header (title, status badge, "Bewerken" for the header's fields, "Acties
▾"); the body autosaves — declared per screen, allowed only where the body
is one long text that validation cannot refuse; the rich-text toolbar sticky
at the top of the viewport; "Versturen…" and its send page where the
document is sent. [4, 15, 39, 42]

### 2.4 Public pages — the kit, not the layouts

The three layouts are the admin's. The public site shares the tokens,
the fields, the buttons, the surfaces and the messages, and keeps its own
page shapes, designed around the visitor's tasks (discover, judge, register,
check) in pilot B — **narrowed by Koen on 4 October 2026 (CR-11 Q57) to
the public header and footer and the consistent embedding of the public
forms** (register, a public form, become a member, renew, update details);
the activity page, the photos and the home's body keep their composition. Today the site shell
(`site_base.html`) hosts two shapes: a **card list** (the
activities with their posters, the photo albums) and a **form page**
(register for an activity, become a member, a public form, the family
portal) — the form page is the record layout's form column at reading
width, centred, with the same surfaces, grid and action bar as the admin,
and the member nudge above the contact fields. The public activity list
keeps its cards: the poster is the content. [9, 12, 21; CR-14 B4.1]

### 2.5 The public shell — header and footer (pilot B, decided 4 October 2026)

Decided by Koen on ChatGPT's brief-11 answer, against its recommendation:
the **coloured band stays, in the colour the tenant configures**
(`site_header_color` in the tenant settings, as today; no new brand token)
and **the logo stays** — top left, one
image from the tenant's brand file at every width, **as tall as the band
allows** — the band's height minus 2 × 8 px, the exchange of #1156 (Koen, 5
October 2026: PROD's logo is much larger than P1's; restored in P1b); no typed wordmark, no
separate town name, no tagline that appears from 1 200 px. "Playing with
letters and things that drop out is no gain."

- **Menu**: the links inline at 768 and 1 440 px, the active page with a
  2 px underline; at 390 px a menu button and a **drawer** over the page —
  360 px, white, a real close button where the menu button was, 48 px rows,
  Escape and the backdrop close it, focus trapped, the page inert. A
  section with pages under it gets a chevron and a small list later (CR-17
  phase 4). One navigation source (modules plus CMS pages), as today.
- **Account**: the member's first name with a chevron opens one menu —
  *Mijn gezin · Admin (board member) · Uitloggen*; no separate Admin link
  beside it; *Inloggen* in that place without a session; in the drawer under
  a divider on a phone. The admin's `account_menu` (§3.14) keeps its
  initials; the public one shows the name.
- **Footer**: one row of three columns on a desktop — **left the newsletter**
  (the heading **"Nieuwsbrief"** — just that, no site name; Koen, 6 October 2026,
  replacing "Nieuws van …" — and the button
  *Aanmelden* as the one yellow call to action — **in the kit's small size**:
  40 px high on a desktop, 14 px medium text, less horizontal padding, 44 px
  on a phone, so the page's own primary (Inschrijven) weighs more than the
  footer's call (Koen, 6 October 2026) — **no sentence between them** — the sentence "Af en toe een mail …" moves to
  the sign-up page, after the link),
  then *Volg ons* with the social links (24 px icons in 44 px targets,
  **without a border or box around them**), then *Met steun van* (logos in at
  most 144 × 64 px, never yellow, **without a border**) — the three columns
  on one line, heading over content (Koen, 6 October 2026: "rustiger");
  **no line above the row** (the ground changing from grey to white is the
  transition), the **three columns spread evenly** now that the newsletter
  column is short, the **first social icon's glyph on the left line of
  "Volg ons"** — its 44 px hit area reaches left of that line — and **32 px
  of air above and below the row on a desktop, 24 px on a phone**, and **the
  same 32 / 24 px between the last content and the footer surface** — one
  rule, the air outside the surface equals the air inside it (dev2 measured
  the grey strip still at 64 / 48 px; Koen confirmed the same day) (Koen, the
  same day, on the built footer); stacked in that
  order on a phone (Koen, 4 October 2026: the newsletter beside the social
  icons, not a row of its own); under it **the legal line carrying the
  organisation's details**: *© 2026 Raak Millegem ·
  street, postal code and town · e-mail · phone · account number ·
  Privacyverklaring*, wrapping where it must. No separate contact block.
  One source: the organisation the site shows (#1550, the party of CR-20);
  the free-text CMS block `site-footer` goes; the legal line reads the
  pages flagged "in de voettekst" (#1569). Left-aligned on a phone on the
  16 px margin; the same 1 248 px container as the header at 1 440 px, so
  the footer no longer sticks out 16 px.
- **Not contested, as drawn**: the header sticky at 64 px on a phone (to be
  confirmed), 112 px at 768 and 80 px at 1 440; the environment banner in
  the document flow above the header, scrolling away; the bell 56 px with
  88 px kept free under the legal line; the language switch at the bottom
  of the drawer and right of the account, only when a second language has
  published content; the air from content to footer was 48 / 64 px as drawn
  and is 24 / 32 px since 6 October 2026 (the footer bullet above).

[CR-11 B10 and Q58, 4 October 2026; beslissing 11 in Koen's project folder]

### 2.6 The public form page (pilot B, decided 4 October 2026)

Decided by Koen on ChatGPT's brief-12 answer, as drawn, for the five
public forms — register, a public form, Word lid, renew, Mijn gezin:

- **One frame**: a 768 px column, **centred** on a desktop (the admin
  records stay left-aligned, §2.2), 720 px on a tablet, 358 px on a phone;
  the title in Inter 600 (32 / 40 px, the public scale of §1.6), everything
  else Inter; one card per
  section (radius 14, 16 px padding), 32 px between cards, 12 px between
  fields; the kit's `field` macro, no public variant. **No "* Verplicht
  veld" legend**: the red asterisk on the label is enough.
- **Register** (CR-14 B4.1 kept): Contact with the member nudge as a quiet
  brand block, only here → Je deelname (products as rows with a 44 px
  stepper, on a desktop too; no "Wie doet er mee?" on the form — the participants' line is the
  activity card's and page's, where it was (Koen, 5 October 2026, "zo was
  het"; it reverses the inline link CR-14 B4.1 kept on the page)) →
  the questions, with radios *Nu invullen / Later* → Betalen → the button.
- **Payment method required** on register, Word lid and renew: two vertical
  radios, *Online betalen* and *Overschrijving*, each with its explanation
  under it. The primary names the next step: *Inschrijven en betalen /
  Inschrijven*, *Word lid en betaal / Word lid*, *Vernieuwen en betalen /
  Lidmaatschap vernieuwen*. The screen never reports a successful online
  payment before the provider confirms it.
- **A public form**: a name card with the form's name and intro, then
  Contact and the questions in section cards, labels 14 px medium (one
  label style), *Verzenden* in the action bar, then its own thank-you page.
  **One long page, no steps**, however many sections.
- **Word lid** (and Mijn gezin), **in this order** (Koen, 5 October 2026,
  after P3 on HDEV: the address belongs to the main member and the
  household): the **Hoofdlid** as a fixed section with the person's fields
  and e-mail addresses; then **Adres**; then **Gezinsleden** — partner and
  children as the composite repeating group (§3.3: collapsed, no handle,
  **"+ Gezinslid toevoegen" under the last person**, so filling in → adding
  or going on → paying reads top to bottom; every person shows **one e-mail
  field from the start**, required for the main member, optional for the
  others); then the price and the
  payment. The main member is no row of the group; in a person's fields **Geslacht is a
  select, half width, beside Geboortedatum** on one row — not a vertical
  radio group (Koen, 5 October 2026, after P3 on HDEV; §3.5: radios only
  where each option needs a line of help); the e-mail addresses as a simple group with
  the *hoofdadres* tag — **no label on the rows, in either mode, at any
  width: the group title "E-mailadressen" says it** (Koen, 5 October 2026,
  after P3 on HDEV: the label stood three times; the §3.3 rule "a label per
  field on a phone" does not apply to a one-field row whose group names it); the address grid; the price line and the payment
  choice in the last card; no nudge; no wizard — the sticky bar carries
  the one action down a 2 100 px page on a phone.
- **Renew**: the status line, the membership card with price, validity and
  the payment radios, the button, then the household summary; renewing is
  its own act. **Mijn gezin**: the **Lidmaatschap** card first in read mode, with its
  three states on one place (Koen, 5 October 2026, choosing the kit's form
  over PROD's bar): valid — "geldig tot en met …" in the success tone;
  to renew — the sentence and the button *Lidmaatschap vernieuwen*; a
  renewal awaiting a transfer — "Je vernieuwing loopt nog." **with the
  transfer instructions in the card **as an inset sub-card** (the kit's soft
  brand tint, radius, 16 px padding) headed "Vernieuwing geregistreerd —
  betaal via overschrijving:" with amount, IBAN, beneficiary and OGM under it,
  as v2.12 drew it (Koen, 5 October 2026: "veelzeggender") — and no link to
  a second screen; the
  running-renewal view of the renew page goes with it (Koen, 5 October 2026,
  Q79); then edit
  mode with one *Bewerken* badge and one
  *Opslaan*; then read mode with the same sections ("—" for empty) and one
  *Bewerken* in the head; the toast "Opgeslagen ✓" for four seconds.
- **The primary is brand blue** in both shells; yellow stays with the
  newsletter's *Aanmelden* only. The action bar of §3.6: 64 px on a desktop
  (primary right, *Annuleren* as text), the 121 px kit bar on a phone with a
  358 × 44 px button. **The bell sits 16 px above the visible action bar**
  on a phone and a tablet and returns to the bottom edge when the bar is out
  of view.
- **States** as §3.18 — the banner "Verzenden kan nog niet: controleer n
  velden." with a link per field, red border and message under each refused
  field, focus on the first, labels stay ink; busy, failed, the leave
  dialog with *Blijven* safe; the browser's own validation bubbles off so
  the message is always the kit's.
- Measured: the first field at y 399–408 on a phone before the legend went;
  controls 44 / 40 px; the footer 820 px on a phone, 480 on a desktop.

[CR-11 B10 and Q59, 4 October 2026; beslissing 12]

### 2.7 The public activity and photo pages (pilot C, decided 6 October 2026; built in v2.14.0, on PROD since 7 October 2026)

Decided by Koen on ChatGPT's brief-13 answer, which was as conservative as
asked ("subtiele, 100 % zekere verbeteringen … in het kader brengen is al
een meerwaarde"): **no redesign**. The composition of the activity list,
the activity page, the photos overview and the album stays; the poster
keeps its place and size; every date of a series stays visible; the album
title and the button sizes stay.

- **Components, with the same rendered picture** (Z8): `date_tile(date,
  size)` — card 48 px and 56 from 640 px, page 56 / 64 px; `year_heading(year)`;
  `activity_facts(dates, location, deadline)`; `component_actions(components,
  context)` with a grid instead of the negative margin on a phone;
  `photo_card(album, href)` on `ui.card(href=…)`; `public_back_link(origin,
  href)`; `photo_grid` and `lightbox`; the public title role without local
  size overrides. The poster stays a style role of the activity page.
  **As built (#1663, C1)**: the public macros live in their own file,
  `_public_macros.html`, not in `_macros.html` — they use the app's date
  filters, which the kit's own test environment does not load; the way back
  is `public_back_link`, because `back_link(label, href)` is the back office's;
  `component_actions` is a partial, not a macro (it reads the page context);
  from 640 px the date tile spans both rows of the card's grid. The
  measurement baseline of #1605 stayed at 0 px on all 45 screen-widths.
- **Five visible corrections** (Z1–Z5): the sponsor block of the shared
  footer ends on the container's right edge (Koen's own addition; the three
  even columns of §2.5 stay, the third aligns its block right); the photos
  overview takes the activity list's year heading (**18 px at every width**,
  semibold, a 1 px line in the line token — Koen, 7 October 2026: the 20 px on
  a phone written here gave way to what the public title scale of #1642
  renders); the album card already had the public card's radius 14 (the
  "16" came from the reconstruction); one way back — the kit's chevron and the origin's
  name, "‹ Activiteiten", "‹ Archief", "‹ Foto's"; the lightbox's close,
  previous and next as 24 px kit icons in 44 × 44 px buttons.
- **Operation** (Z6, Z7): the lightbox traps the focus and returns it to the
  photo that opened it; the thumbs-up keeps its 20 px pill and gets a 44 px
  hit area; the browser title is "<page> · <site name>", never a literal
  tenant name. No swipe, counter or zoom. **As built (#1665, C3)**: the
  lightbox stands beside `ui.modal`, not on it (the modal traps no focus and
  is a white card with a title bar); shown through a class binding, not
  `x-show`; the thumbnails keep radius 10 px; a photo is bounded, never
  enlarged; the page behind still scrolls with the wheel. One screen added to
  the baseline (`public-fotos-lichtbak`); the kit page shows the lightbox.
- **Named as taste and not built**: the poster under the text on a phone;
  folding long date series; dropping "Foto's —" from the album title;
  larger desktop buttons; card effects.
- **Guard**: the DOM baseline (#1605) carries these pages at 390 and 1 440;
  only Z1–Z5 may move it; the invariants are 1 / 3 / 12 dates, a long title,
  several components, full / closed / members only, no poster, an empty
  list and a second tenant. A fourth ratchet rule since C1: no hand-written
  date tile, year heading or way back in a public template.

[CR-11 B10, Q86 and Q88, 6 October 2026; beslissing 13; built as in CR-11 B9, 7 October 2026; v2.14.0]

---

## 3. Components

Each macro is listed with what it renders and what it decides; the
signature is indicative, the behaviour is the norm. All in
`ui/templates/_macros.html`, rendered live on `/admin/design-system`.

### 3.1 `field(name, label, kind, …)` — the only way to a form control

Renders label, control, help text and error in one block on the grid;
`required` marks the label; the error sits under the control in
`brand-danger`, the field's border coloured. `kind` is one of `text`,
`textarea`, `number`, `email`, `phone`, `date`, `select`, `switch`,
`segmented`, `checkbox_group`, `radio_group`, `upload`, `url`, and `slug`
(a URL name such as `herfstwandeling-met-soep`: half width, no
auto-capitalisation — distinct from `url`, which is a full address and
always full width; block 6, 4 Oct 2026). **The kind
decides the width:** `url`, `email`, `textarea` and rich text are always
full; `number`, `date`, `time`, a code, a short `select` and `switch` are
half or quarter; `text` is half unless `long=True`; a template may widen a
short field and never narrow a long one — a long field with `span="half"`
is red. No raw `<label>`, `<input>`, `<select>` or `<textarea>` in a domain
template. [23, 24, 54]

### 3.2 `form_grid` and `section(title)`

A section is a heading (`text-base font-semibold`) over a two-column grid
at reading width — **one card per section, never a nested card**, 16 px
from the heading to the first field (block 6); a field spans half by default, `span="full"` for long
content, `span="quarter"` for a number or code; one column on a phone.
Fields that describe one thing share a section; fields share a row only
when read together (street · number · bus; price · member price; from ·
to). Sections are separated by 32; a section is a card or a heading in a
card, never a nested box. [2, 23]

### 3.3 `repeating_group(title, rows, add_url, …)` — two variants

Heading with "+ <item>" at its right (in edit mode); `⋯` at the far right
of each row (delete, duplicate); a drag handle at the far left **only when
the order means something** (dates, components, products, form options —
not e-mail addresses). **Simple** variant: one compact row per item, the
fields inline (an e-mail address, a date). **Composite** variant: a titled
block per item with its own fields underneath and, when it has them, its
own child group (a component with its settings and its products) — so it
is visible which product belongs to which component and which settings are
whose; the one-among-many marker
("hoofdadres") as a tag on the row; "nog geen …" and the add button when
empty; the rows are committed with the screen's save, never on their own.
Instances: contact details, addresses, activity dates, components,
products, form options, order lines. [1, 50]

**Decided with block 7** (Koen, 4 October 2026, on ChatGPT's brief-07
answer): a **simple row** has the drag handle (`grip-vertical`, 44 px)
at the left where the order matters, the fields inline at 768 px (a date:
**Datum · Van · Einddatum · Tot**, four quarter fields — the end date is
optional and empty means the same day; ChatGPT's draft forgot it, the
model has `end_date`; Koen, 4 Oct 2026; an e-mail: the address and its
tag; an organiser: the name as a jump link). **The labels of a simple row
stand once**, as a column head above the first row, never repeated per row
(row 1, the e-mail addresses; Koen again on 4 Oct 2026 when ChatGPT
repeated Datum · Van · Tot on every date row); on a phone, where the fields
stack and no head is possible, each field carries its label, `⋯` at the right, 12 px between rows with a thin
line in that space; on a phone the fields stack under a first line with
handle and `⋯`. A **composite item** (a component, a product) has **its drag handle in a
fixed gutter at the left of the whole block — 28 px wide, not 44 (Koen, 5
October 2026) — and its title line, its fields
and the separator line to the next item share one left edge to the right of
that gutter** — never fields that start left of the handle (ChatGPT's draft
did; Koen, 4 Oct 2026, Q50); the title line (name, `⋯`), its fields in the
grid under it, and its child group
(**Producten**, with its own "+ Product") indented 12 px behind a vertical
line at every width (was 16 on a desktop; Koen, 5 October 2026) — no card,
no background, no nested box; **a product row is one line: naam · prijs ·
ledenprijs · maximum** (the name wide, the three numbers quarter-width; as
it was before K5), and a second line with **one segmented choice —
Betalend · Gratis · Ter plaatse** — and *Publiek zichtbaar*, its help text
only while the product is not public; **a component's head is one line too:
naam · maximum · inschrijven tot**, then *Ploegnaam vereist* and
*Formulier* on the next, without an explanation line under the select (its
help text says it, Q66) (Koen, 5
October 2026, after K5 on HDEV: the two switches of ChatGPT's draft, with a
refusal when both were on, were one choice out of three in disguise — §3.5's
own rule; until K5 it was a select with the same three); the price fields
active only for Betalend; in read mode a product is two short lines
("Soep · € 5,00 · leden € 4,00" / "Betalend" — or "Gratis" / "Ter
plaatse"), and the item's name is its heading, not repeated
as a field; the item's rare settings go to the form's one collapsed slot.
**Adding** inserts an empty row in place with the focus on its first
field, edit mode only; **the add button of a simple group stands at the
heading's right** ("+ Datum", "+ Product", "+ Organisator"), **the add
button of a composite group under its last item** ("+ Onderdeel",
"+ Gezinslid toevoegen") — where the hands are when the last block is
filled in, not a block higher (Koen, 5 October 2026, on Word lid: scrolling
back up to add a child means fewer children entered); **a simple group
whose first value is wanted shows one empty row from the start** instead of
asking for "+ E-mailadres" (a person's e-mail address; Koen, the same day:
"we gaan minder mailadressen krijgen"); an organiser is added through a **member search
inside the group** (type a name, pick a member), never a dialog, never
free text. **The empty group** says "Nog geen datums." and in edit mode
keeps only its add button (in the head for a simple group, in place of the
first item for a composite one). **The row's `⋯`**: Omhoog · Omlaag ·
Dupliceren | Verwijderen (red, last); Dupliceren not for members and
e-mail addresses; a duplicated component takes its products; Omhoog is
disabled on the first row, Omlaag on the last; while dragging, the origin
stays as a dotted space, the row gets a brand border and shadow, a brand
line marks the drop. **Removing a row inside an unsaved form asks no
confirmation** — Annuleren undoes it; the kit's "definitief verwijderen"
dialog is for deleting a record, and whether a component with
registrations may go is the service's answer at Opslaan, shown on the
row (Koen's correction). **The one-among-many tag** ("hoofdadres", 4 px)
shows in both modes; another row takes it over through "Maak hoofdadres"
in its `⋯`; the main row's `⋯` has no Verwijderen. Measured at 1 440 px:
Onderdelen with two components (one with two products) 719 px read /
1 380 px edit; a date row 46 / 65 px; an organiser row 44 px.

### 3.4 `rare_settings(title, summary)` — placed by the layout, last

A collapsed section in the **last slot of the form layout** — after every
ordinary section and the attachments, just above the action bar, never
between fields; the layout renders it there from the screen's declaration,
so a template cannot put it elsewhere (a `rare_settings` followed by a
`section` is red). Closed by default, a
disclosure triangle, a one-line summary when something inside is set
("2 externe links"), a short note when the content is discouraged ("de
eigen inschrijving heeft de voorkeur"). Instances: the component's
external links, the activity's poster URL. [3, 53]

### 3.5 Controls

- **`switch`** for a boolean setting — also inside an edit form that applies
  only on Opslaan (Q13, Koen, 3 Oct 2026); **the knob at the left, the label
  at its right**, 8 px apart, as a checkbox reads, so two half-width switches
  on one row never put a knob beside the wrong label (block 6, Koen, 4 Oct
  2026, reversing "label at the left"); "aan"/"uit" for the screen reader;
  in read mode it is words ("Enkel leden: ja"), never a disabled control. [8]
- **`segmented`** for two or three exclusive options (table · cards;
  nu · later). [2]
- **`checkbox_group`** for several out of a list, and a single checkbox for
  a consent; nowhere else. [8]
- **`select`** above five options; `radio_group` only where the options
  need a line of help each.
- **`multiselect`** for several out of a list in a filter or a toolbar:
  collapsed by default to one line that shows the chosen values or their
  count; opens to tick, closes again. A control that holds a choice never
  stays open; a `checkbox_group` is a form field, never a filter. [61]

### 3.6 `action_bar(form, …)`

One per screen (or per sub-record with its own lifecycle). Right-aligned:
"Annuleren" as a text button, "Opslaan" as the primary; "Verwijderen" as a
red text action at the far left. Labels are the macro's defaults; a custom
primary label only for a named consequence ("Definitief importeren",
"Verstuur naar 312 abonnees"). `sm`. Never in a card header, never inside
a repeating-group row. [22, 46, 50]

**Decided with block 9** (Koen, 4 October 2026, on ChatGPT's brief-09
answer): the bar is 64 px high, as wide as the form column, white with a
thin top line, under the last section (the collapsed rare settings), 24 px
below it; **sticky on a desktop too** — **flush against the window's
bottom** while the form is longer than the window, with the kit's shadow
upward and a heavier separator line, so nothing runs under it and it reads
as a bar (Koen, 5 October 2026, after K7 on HDEV: the white bar floating
16 px up on a white card with the poster showing under it was "not well
visible" — the 16 px gap of the prototype goes); in the flow at the form's
end;
only in edit mode; in edit mode Verwijderen lives in the bar and not also in
Acties (in read mode in Acties). On a phone: 121 px at the bottom, Opslaan
full width on the first line (44 px), Verwijderen left and Annuleren right
on the second, the content padded by bar height + 24 px. **One save**
writes the record with its groups (dates, components, products,
organisers) in one transaction — a card is not a transaction boundary; a
sub-record with its own lifecycle (a payment, a registration line, a
membership) saves on its own screen; the household's board-member select
no longer saves at once but with the household. **Keyboard**: Ctrl/⌘+S
saves while in edit mode (the browser's save-page is suppressed), Enter in
a one-line field submits as the browser does, Esc closes the top-most
dialog or menu only — never the form, so no change is lost by one key.

### 3.7 `pager(page, size, total)`

Two renderings from one macro: in the toolbar row the count "x–y van n"
with the page-size select (on a phone the page size moves under `⋯`); at
the bottom "‹ Vorige · Volgende ›" only, right-aligned on a desktop, at
the two edges on a phone, the first and last disabled. Always a total (an
approximate "van meer dan 10 000" where counting is heavy); an empty list
says "0–0 van 0"; a new search, status, filter or page size goes to page
1; "Pagina n" does not exist. Hidden when everything fits. (Block 3, 2
October 2026.) [6]

### 3.8 `figures(items)` — the key figures, one figure each ("tiles" in the rows of CR-11)

Inline in the title row, as plain text: **one figure** per item (`text-2xl`,
tabular digits; the macro takes a single value and refuses a pair or a
stacked amount — two things to do are two figures, "Nog te ontvangen" and
"Nog terug te betalen") with one short label under it (13 px, two or
three words: "Open activiteiten", "Te vernieuwen 2027", "Netto ontvangen")
and the full definition in the `title`; a qualifier belongs in the label,
a count beside an amount is a second figure, so there is no second line.
Thin dividers between the figures, **no card, no border, no hover, not a
link**: a figure is read, and the rows it counts are found with the
toolbar's status filter — the fix for row 36 is that the segment with the same name
exists, not that the figure is a button (Koen, 2 October 2026, choosing
the subtle figures of ChatGPT's brief-01 frame over the card tiles of
brief 02). The figures of one row share one baseline; a label fits on one
line at 390 px or it is rewritten — the ellipsis is a safety net, a real
label that gets cut is red [55, 58, 60]. At most four or five figures per
head, or the title row is a dashboard. A figure colours only when it asks
for attention: the `warning` token on an open amount above zero, nothing
else coloured. On a phone the figures sit on one line under the title and
wrap to a second when they must. Which lists have figures and which: §5
(Betalingen three — Netto te betalen · Nog te ontvangen · Nog terug te
betalen; Leden three; Activiteiten two; Werkbank and Abonnees two each when
built; the rest none). [10, 36, 52]

### 3.9 `record_header(title, badges, facts, primary, actions=[…])` — actions as data

Title line with badges (status first); facts line with reference links;
at the right **one primary button and one "Acties ▾" menu, never more**.
The screen hands its actions as a list, each with a kind — *record action*
(duplicate, print, export, send, reopen, delete) or *tool* (photos, Design
Studio) — and the macro places them: record actions first in a fixed
order, tools under a divider, delete last after a divider; Raakje is never
among them (it is the shell's trigger). A screen cannot draw a button of
its own in the head: a `btn_*` call there outside the macro is red. On a
phone there is nothing to overflow, and **the title goes first**: the two
controls stay beside the title while it fits, and drop to a line of their
own under it before the title wraps into a narrow column or truncates to
a few letters; a title truncates only at its end when it alone does not
fit one line [56]. Where each kind sits on the other layouts is the
table in CR-11 B4.3 (list: create and "Instellingen" in the title row;
document: the same menu; public: one primary in the sticky card, no
menu). First applied to the activity's head (#1387) and the "Kopiëren" of
#1397, whose place was decided four times before this rule existed. [39,
51]

**Decided with block 6** (Koen, 4 October 2026): a state of the record is
never a form field — "Geannuleerd" leaves the activity's form and becomes
the record action **"Annuleren"** in Acties, next to "Terug naar concept";
the status badge then says Geannuleerd.

**Decided with block 5** (Koen, 3 October 2026, on ChatGPT's brief-05
answer): the title line is 36 px on a desktop (title 30 px, badges beside
it, status first, the others in `ink-soft` on `surface-2`, 4 px radius), the
facts line 24 px, 8 px between them; a long title stays on one line and
the badges move to a second line inside the title group (68 px), the two
controls stay top right; the facts line reads date · time · place ·
reference, the reference with `arrow-up-right`, an e-mail a real
`mailto:`; **on a phone the facts keep their full words** — "zondag 1
november 2026 · 14:00 · Miloheem · Publieke pagina" wraps to a second
line rather than becoming "1 nov · 14u · Publiek" (Koen refused the
abbreviations) — and the reference's target is 44 px; on a phone the
title takes the full width, the badges under it, then Bewerken and Acties
on a line of their own at the right, unless a short title fits beside
them ("Quiz"). **"Acties ▾"**: 272 px, anchored right, 8 px under the
button; the activity's menu is Kopiëren · Terug naar concept | Foto's
uploaden · Design Studio | Verwijderen (red); the general order of record
actions is kopiëren, afdrukken, exporteren, versturen, heropenen / terug
naar concept, only the available ones shown; Escape returns the focus to
Acties. **Edit mode**: a badge "Bewerken" in the title group after the
status, the primary button gone, Acties stays; Opslaan and Annuleren live
in the action bar (block 9), never a second time in the head. **A record
without tabs** (a page, a user) has no empty tab line: the content follows
the facts. Measured: the first content line at y = 286 on 1 920 × 1 080
(318 with a long title and three badges), visible on 390 × 844 with the
summary strip above it.

### 3.10 `summary_card(state, figures, action)`

Right column on a desktop (300 px in the reading group, `surface-card`,
16 px padding, 12 px between parts), a strip under the tabs on a phone
(358 px, 12 px padding, badge and action icon on the first line, the
figures on the second, about 130 px): the state badge first, up to three
figures (24 px semibold, labels 13 px, tabular amounts, an open balance in
`warning`), one action (the activity: the public link with its copy
button, which confirms "Gekopieerd" beside itself). The activity: Gepubliceerd ·
Inschrijvingen · Deelnemers · Openstaand · the link; the household:
Lidmaatschap <year> · Personen · Openstaand. Toegang is the head's badge and
a form field, Inschrijven tot and Bezetting belong to the component. **Only
on Gegevens**; a list tab has none (block 8, Koen, 4 October 2026). [25]

### 3.11 `reference(record)` — the jump link

The record's name as a link to its detail, `arrow-up-right` after it,
`text-blue-500` underlined, the way back preserved. The only way a field
that *is* another record is rendered; a name in blue always goes to the
record it names. **Everywhere** (Koen, 4 Oct 2026, Q56): in a record's
facts line and form (block 5), in an unfolded row (block 8) and **inside a
list row** — a row's first cell opens the row's own record without an
arrow, every other record named in the row (the activity under Context,
the household behind a booking) is its own jump link beside the row link,
as block 4 drew the Context cell. A person has no page (Q28): a person's
name goes to the household page with that person's row opened. A name of
another record rendered as plain text is red (C6). [20, 30]

### 3.12 `related_tabs(tabs)`

The tab bar of the record page: "Gegevens" first, then the related lists
with counts, the same order per entity across the portal (defined once per
entity in Part 5). Labels 14 px, counts 13 px tabular, the active tab a
2 px underline in the brand colour, the bar 45 px with its bottom line; no
border around the group, no filled active tab, no rounded corners (block 5,
3 October 2026). **Tabs — an underline under the active item — are
navigation inside a record and nothing else**: they lead from a record to
its linked objects, the content below switches, the place stays. A tab bar
never appears in a list's toolbar, and a list's status filter never looks
like one (Koen, 2 October 2026: today Betalingen's status filter is drawn
as tabs and the activity's tabs look the same, so the eye cannot tell a
filter from a place). [19]

### 3.13 `toolbar(…)` — five things, same order at every width

The list's second row — **status filter · search · Filters · count with
page size · `⋯`** — identical on a desktop and on a phone, where it
wraps to three lines (block 3, Koen, 2 October 2026: consistency over one
click; nothing sits on two places at once, nothing changes place by
device).

**The status filter is a segmented control** (`status_filter`): one
bordered group of segments, one segment chosen, on the brand tint, 36 px
high like a button (44 on a phone); `fieldset` with radio inputs, Tab
enters, the arrows choose; it reads as a control, never as navigation;
no loose pills, and the word "chip" is not used (it replaces the three
shapes of today — Leden's pills, Activiteiten's pills, Betalingen's tabs
with counts). **Which segments is a choice per list**, written in §5, not
a formula: a segment is a state the board acts on; a done state gets no
segment; "Alle" is not mandatory. **A segment carries its count** where
the state is acted on — **"Openstaand (3)", the count in brackets, the
one way a count follows a name anywhere: a segment, a record's tab
("Inschrijvingen (23)"), a group row ("Wandeling (18)")** (Koen, 4 Oct
2026) — computed with the search and
the other filters of that moment, so the count is what the click yields;
"Alle" carries none (the toolbar's count says n); a zero stays ("nothing
to do" is information). Decided: Betalingen *Alle | Openstaand n*; Leden
*Actief n | Te vernieuwen n | Opgezegd*; Activiteiten *Komende | Archief |
Alles* (periods, no counts). Six or more segments become one select below
1 080 px of list width; never two lines, never a scroll strip.

**The search** grows with the row (180–480 px, full width on a phone),
the magnifier is its submit, `type="search"` gives the clear; it stands
second, after the status filter: scope before query, and a fixed block at
the left keeps the right-hand group in place while the search grows
(Koen, 2 October 2026, keeps the order). The `/` key stays the top bar's.

**Filters is always one button** (`filter` glyph), also with a single
select, also at 1 920 px: it opens a panel with the list's selects
(context, year, a multi-select) and one Toepassen; a multi-select is
collapsed to one line ("Te controleren +1") and opens to a tick list,
never a checkbox group in the row (row 61). The selects never stand in
the row and never move by device.

**`⋯` holds the screen's secondary actions** — export, import,
Instellingen — in a fixed order, and on a phone the page size; it never
repeats a button that is visible elsewhere. The count and the page size
come from `pager` (§3.7).

The embedded rendering inside a record keeps the status filter, the
search, the count and `⋯`; no title row, no figures, no context select
(the record is the context). [45, 29]

### 3.14 `account_menu`

A round badge with the initials, a chevron, hover, focus ring,
`aria-haspopup`; opens a menu whose first line is "Aangemeld als …", then
"Mijn profiel", "Werkruimte wisselen", "Uitloggen". One source, rendered in
the top bar at every width — on a phone too, initials and chevron, not at
the bottom of the navigation drawer (block 1, 2 October 2026, following the
concepts: the drawer is for navigation, the account stays where the eye
looks for it). [47, 48]

### 3.15 `raakje_panel`

One trigger in the shell chrome on both sides: in the admin a bordered
button in the top bar with the `sparkles` glyph and the word **"Assistent"**
(icon-only with that `aria-label` on a phone), never a bare icon and never
the gear; on the public site the tenant's own name for it ("Raakje" here)
(block 1, Koen, 2 October 2026). It opens a side
panel docked right from 1 440 px (a modal below, a bottom sheet on a phone) with the screen's context;
enabled per module by rule (the module's objects are in the reporting
universe, or its facade exposes commands), otherwise greyed with "Raakje
kent deze gegevens nog niet". The screen owns its selections; the panel
reads them. The assistant page and the per-screen `AI ·` buttons do not
exist. [32, 33, 41]

**Decided with block 10** (Koen, 4 October 2026, on ChatGPT's brief-10
answer, as drawn): the panel is **400 px, docked at the right under the
top bar to the window's bottom**, on `surface-card` with a thin line; the
head "Assistent" with the read-aloud toggle and close, the context under
it in full ("over Herfstwandeling met soep", "over 8 openstaande
betalingen (filter Openstaand)", "over Raak Millegem" without a record);
the conversation in the kit's balloons with its own scroll; **three
suggestions of the screen** as text lines above the question field; the
field from 44 to 120 px with the microphone and the send button, Enter
sends, Shift+Enter breaks. **The content moves aside, it is not covered**:
at 1 920 px the whole reading group fits beside the panel; at 1 440 px
exactly 768 px remain, the summary becomes the strip above the form and
the form keeps its width; a list beside the panel at 1 440 px falls back
to its stacked rows (list width under 900) — accepted, the panel is
occasional and closing restores the room. **Below 1 440 px** a centred
dialog of at most 560 × 720 px (the background blocked); **at 390 px** a
sheet of 560 px from y = 284 with a handle, the title and badges visible
above it; X or Escape closes and returns the focus; a click beside the
panel does not close it. **No selectors in the panel**: the screen owns
them (the newsletter's activities and reports stand on the newsletter
page). **The newsletter's choices are three, not two** (Koen, 4 October
2026): *Voorbije activiteiten* (the look back), *Uitgelicht* (the coming
activities told in detail, at most three, each an activity block with
poster, description and registration link) and *In de kalender* (the
coming activities, the next nine by default, **the highlighted ones
included** — the calendar lists everything once more in a row; one
calendar block that stands in every letter). The assistant writes a look-back, a piece per
highlighted activity and adds the calendar as one block — never a detail
block per calendar activity, which is what today's proposal does and what
makes the organiser delete six of them. "Activiteit invoegen" and
"Kalender invoegen" by hand read the same three choices. On the page
(decided without a drawing, Koen, 4 October 2026): three chip groups with
their counts in brackets — *Voorbije activiteiten (4)* all ticked by
default with "+ Toevoegen" for an older one; *Uitgelicht (2 van 3)* where
"+ Toevoegen" picks from the coming activities and is dimmed at three, ×
removes the highlight only; *In de kalender (9)* where × removes one and
"+ Toevoegen" adds a further one; under them the line on the meeting
reports; the panel's context line says "over Nieuwsbrief oktober · 2
uitgelicht, 9 in de kalender". On a module the assistant does not know the trigger is dimmed but
focusable and opens only "Raakje kent deze gegevens nog niet". **A
proposal for the form**: the fields it touches get a brand line, the brand
tint and "Voorstel · nog niet toegepast"; the panel says "3 velden
ingevuld als voorstel" with Toepassen and Negeren; Toepassen writes the
values into the fields ("Ingevuld door Assistent · nog niet opgeslagen"),
the one Opslaan of the action bar saves; a proposal carries the field
names, the values and the version it was based on, and never silently
overwrites a change made meanwhile; Negeren removes it and keeps the
user's own changes. **A reviewable proposal** (the newsletter today): a
proposal whose text carries passages the assistant could not ground
shows them in the panel marked, each with "klopt, behouden" unticked —
omitted by default — and Toepassen writes the text with the kept passages
(the rule of "AI-antwoord: dubbelcheck tegen bronnen"). A proposal may
fill **any field the screen declares** — on the newsletter: Onderwerp,
Voorbeeldtekst (a growing field) and Inhoud together — not only the
body. **Answers**: a figure large in the balloon with its range and source;
a small table (two columns, a few rows) with a link to the full list
state ("Bekijk alle 8 betalingen"); loading "Raakje zoekt het voor je
uit…"; failed "Raakje kon geen antwoord geven — probeer het opnieuw. Je
vraag staat er nog.", no invented figures. **The public bell**: 56 px at
the bottom right; at 1 440 px a compact window of 400 × 640 px above it,
on a phone the same sheet; the tenant's name; headings in Inter (§1.6,
corrected 5 Oct 2026); **the
greeting stays as it is today, waving hand included** — "Hallo, ik ben
Raakje! 👋 …" (Koen, 4 October 2026: he wants to keep it); three
public suggestions; one component in the DOM for both shells, the public
toolset only. Measured: the panel 400 × 1 016 px; remaining content
1 232 px at 1 920 and 768 px at 1 440; the question field at y = 992
(desktop) and 760 (phone); no overflow in Firefox and Chromium.

### 3.16 `rich_text(name, inserts=[…])`

One toolbar for every rich-text field: format groups, lists, link,
undo/redo, the HTML-source toggle where allowed; hidden until focus; sticky
at the top of the viewport while the editor scrolls; one "Invoegen ▾" menu
fed by the screen (the newsletter's four items, the page's image from the
library). No toolbar markup in a template. [15, 40]

### 3.17 `import_steps(report, commit_label)`

Every import: a file upload, then the report *nieuw · gewijzigd ·
verwijderd* with counts, names and consequences, then one commit button
whose label names the consequence; leaving before it changes nothing.
[17, 18]

### 3.18 States — designed, not left to chance

Every layout has these states drawn in the design-system page, decided
with block 9 (Koen, 4 October 2026): a **validation error** on save — the
bar stays, a banner at the top of the form ("Opslaan kan nog niet:
controleer 2 velden.", each error a link to its field, "Je andere
wijzigingen zijn behouden."; soft danger tint, 3 px accent left, 16 px
padding), the first refused field scrolled into view and focused with its
message under it and a coloured border, every typed value kept; **saving**
— "Opslaan…" with a spinner on the primary, the whole form inert but
looking the same; **save failed** — "Opslaan is niet gelukt." with the
reason, nothing lost, no toast, the button Opslaan again; **saved** — the
record in read mode, the toast "Opgeslagen" with a check on `ink`, 4 s,
top right under the top bar on a desktop and at the bottom on a phone;
**cancel with changes** — "Wijzigingen weggooien?" with *Verder bewerken*
(focused, **filled**) and *Wijzigingen weggooien* (outline); **leaving
with changes** on a navigation click — "Deze pagina verlaten?" with
*Blijven* (focused, filled) and *Weggooien* (outline) that performs the
original click; never a third "Opslaan en verlaten"; the browser's own
prompt on closing the tab; **delete** — the kit's dialog naming the
record, Annuleren focused, "Definitief verwijderen" filled red, the
consequence sentence true to the service (a C1 premise: what a delete
does with registrations and payments, or whether it is refused); **a state
command** from Acties or a row (Terug naar concept, Activiteit annuleren,
Bevestig) — a lighter dialog naming its consequence with a filled brand
button, then a toast and the changed status badge; **empty** (one sentence
and the create action); **no access** — a quiet page with one sentence
and "Terug naar <lijst>", no record data; **autosave** on a document
("opgeslagen om 21:14", "opslaan…", "niet opgeslagen — opnieuw proberen"
in the facts line, no action bar; "opgeslagen" only after the server
confirmed the latest version).

### 3.19 Buttons — the hierarchy and the words

Three weights: **primary** (filled, one per screen), **secondary** (outline,
for the screen's other actions), **text** (cancel, quiet actions); `danger`
is red text, filled only in a confirm dialog. Words: Opslaan · Annuleren ·
Verwijderen · "+ Nieuw <item>" · Instellingen · Versturen… (a step
follows) · "Verstuur naar N …" (the last step); "Toevoegen" only names an
addition to a set outside the form ("Toevoegen aan kring"). A button that
opens something shows it: a chevron on a menu, "…" on a step, a triangle on
a disclosure. [22, 42, 46, 48]

---

## 4. Interaction patterns

The current P1–P12 stay; four change and four are added.

| # | Pattern | Rule |
|---|---|---|
| P1 · Edit and stay | **revised:** the whole record is the editor; one save at the bottom; the screen stays; a toast; leaving with changes warns. [14] |
| P2 · Create and continue | the record exists after "Opslaan", not after "Toevoegen"; the create button is "+ Nieuw <item>" at the right of the heading it creates into. [31, 46] |
| P3 · The way back | on every record page, first line, to the list as it was left: a list's state (filter, search, sort, page, page size) is its URL, pushed by the list layout; the record layout returns to the address the row carried. [28, 57] |
| P6 · Import in steps | **widened:** every import that creates, updates or deletes; the report in three lines; the commit names the consequence. [18] |
| P8 · List, detail, edit | **revised:** the row opens the record; on a top-level list the record page, inside a record's related list an in-place unfold with a jump link. [26] |
| P13 · Opens shows | a control that opens something shows that it opens — chevron, "…", disclosure triangle. [48] |
| P14 · The member nudge | on every public registration and on "Word lid", unconditional, above the contact fields, with the sign-in link that returns. [21] |
| P15 · One fact once | a status in its badge, a count in a tile, a setting behind Instellingen; never twice on one screen. [38, 10] |
| P16 · The screen owns the selection | a selector belongs to the screen; Raakje and the manual inserts read it. [41] |

---

## 5. Classification — every screen, its kind and its shape

**Standing on 5 October 2026** (K9, #1563, `backend/tests/ui_baseline.py` —
the raw material for the roll-out slices: a screen's entries are what its
slice removes): raw form elements 105 in 29 files · raw checkboxes 24 in 12 ·
spacing on a field 76 in 22 · raw surfaces 95 in 50 · extra head buttons 20
in 12 · hand-drawn tiles 3 in 3 · sideways scroll 9 in 8 · nowrap rows 7 in
3 · admin pages straight on the shell 60 in 60; the pilot screens at zero
everywhere. Against A2's counts of 1 October: raw elements 456 → 236 with
hidden inputs, 105 without; raw surfaces 224 → 95; the 1 215 spacing classes
could not be reconstructed by one definition.

Measured on `master` after v2.11.0 (2 October 2026, HEAD 5e52292e) and
written as the end state: the **kind** and the **shape** are fixed here;
what is marked *proposed* is the author's draft of the per-screen columns,
confirmed with Koen at that screen's phase (pilot A for Activiteiten and
Betalingen, the roll-out for the rest). Today's state stands beside it so
the distance is visible. The rules behind the columns: a tile is one
figure with a one-line label, plain text, not a filter (rows 36, 52, 58, 60; block 2); a row shows the
same three or four things for every record, omitted when they do not apply
(row 36); the toolbar is one row — the status filter, search, filters, the count with
the page size, `⋯` (rows 6, 45); every list pages (P1); no list scrolls
sideways (row 11); the row is the way in (row 26); the list's state is its
URL (row 57).

### 5.1 Admin list pages

Shell width for every list: the wide frame (row 11); today three lists set
`max-w-none` themselves and the rest take the shell's reading width.
"Today" names the shape, the tiles and the toolbar as measured.

| Screen | Today | End state: a row shows | Tiles (*proposed*) | Toolbar: status filter · search on · filters · sort | Header |
|---|---|---|---|---|---|
| Activiteiten | cards; tiles Open inschrijving · Volzette onderdelen (end state: Open activiteiten · Volzet onderdeel — "inschrijving" is too hard a word, Koen, 2 Oct 2026); search, chips Komende/Archief/Alles; no pager | name with status badges · first date and time · location · registrations count (omitted without a component) | Open inschrijving · Volzet onderdeel (activities with one) | Komende · Archief · Alles; name, location; year; date | + Nieuwe activiteit |
| Leden | cards; three tiles; search, chips Alle/Actief/Opgezegd, year select; pager 25 | household name with the address under it (street · number · municipality) · persons · membership state badge — no Gemeente column, and no actions column: no row has an action, a household is deleted on its record (Koen, 10 Oct 2026) | Actieve gezinnen · Actieve personen · Te vernieuwen (year) — all three stay (Koen, 10 Oct 2026) | Actief · Te vernieuwen · Opgezegd, no Alle (block 3; (Koen, 10 Oct 2026)); name, street, e-mail; membership year; name | + Nieuw lid; Leden importeren under ⋯ (Koen, 10 Oct 2026) |
| Betalingen | table grouped per registration; four tiles; status tabs with counts, search, context filter, status select; pager 50; export in the filter bar; `max-w-none` | name/reference · context · status badge · amount · received · balance (W1's two tiles carry the totals) | Netto te betalen · Nog te ontvangen · Nog terug te betalen (Koen, 2 Oct 2026; "Ontvangen" and the booking count go — the toolbar's count shows n) | Alle \| Openstaand n (Koen, 2 Oct 2026; Betaald, Terugbetaald and Terug te betalen get no segment); name, OGM, description; context, status; date · export under `⋯` | none (the breadcrumb goes; row 35) |
| Formulieren | cards; search, status select; no pager | title · status badge · submissions count · last submission | Open · Inzendingen deze maand | Alle · Open · Gesloten; name; —; updated | Instellingen (holds "Formaat (voor AI)", row 34) · + Nieuw formulier |
| Vergaderingen | cards; search; no pager | date · status badge · location · points count | Volgende · Verslag open | Komende · Voorbije; date, location; year; date | Instellingen · + Nieuwe vergadering |
| Nieuwsbrieven | cards; search; no pager | subject · status badge · audience · sent or updated moment · while sending: progress | Verstuurd dit jaar · Abonnees | Concept · Verstuurd; subject; audience; updated | Instellingen · Abonnees · + Nieuwe nieuwsbrief |
| Abonnees | table; search, status select; inline Uitschrijven/Verwijderen; add-form card under the table | address · first name · source · status badge · since | Bevestigd · Wachten · Uitgeschreven | Alle · Bevestigd · Wachten · Uitgeschreven; address, first name; —; since | Lijst importeren · + Adres (replaces the form card) |
| Pagina's | cards; search, chips; manual order with ↑↓; no pager | title · /slug · gepubliceerd/concept badge · in navigatie badge | Gepubliceerd · Concept | Alles · Gepubliceerd · Concept · In navigatie; title, slug; —; manual order (the handle of the repeating-group row) | + Nieuwe pagina |
| Media | inline-edit cards in a 2-column grid; search, kind select, activity select; no pager | **cards (grid)** — the one admin exception: thumbnail · title · kind · origin (activity) · clearance badge (CR-15) | — | Alle · per kind; title; activity, year, in gebruik (CR-15); newest | + Uploaden |
| Design Studio | cards without thumbnail; search; no pager | **thumbnail column** (the latest render) · activity · status badge · versions · updated | — | Alle · Gepubliceerd · Verouderd; activity; —; updated | + Nieuw ontwerp |
| Gebruikers | inline-edit list, one form per row; search, role select, active chip | e-mail · active badge · roles as tags (row 44: the row opens the record) | Actief | Actief · Alle; e-mail; role; e-mail | + Nieuwe gebruiker |
| Organisaties | cards; search, type select; empty header | name · type badge · code · legal form · inactive badge | — | Alle · per type; name, code; —; type, name | none (created elsewhere, by design) |
| Tenants | cards; search, status select | name · /code · active badge · platform badge | — | Actief · Inactief; name, code; —; id | + Nieuwe tenant |
| Rapporten | cards with description and chips; search, owner and shared selects; AI buttons in the header | name · shape icon · privé/meegeleverd badge · owner · last opened | — | Mijn · Meegeleverd · Alle; name, description; owner; name | + Nieuw rapport (the AI buttons go: Raakje is the shell's trigger, row 32) |
| Wijzigingen | table, sortable, page size, pager; `max-w-none` | Tijdstip · Wijziging (badge) · Onderdeel · **Persoon** (the member the change concerns — kept on Koen's word, 2 Oct 2026, after ChatGPT dropped it) · Record (jump link) · Uitgevoerd door · Details; Details hides first, then Uitgevoerd door; no row menu (a log line is not deleted); the segments Alle \| Leden \| Activiteiten \| Betalingen without counts | — | per group; actor; from date; sortable columns | Ledenexport (.ods) under `⋯` |
| Werkbank | cards polled every 30 s; search, kind filter, status chips | title · kind badge · state badge · created · decision when done | Open · Vandaag | status chips (code labels); task, subject; kind; status, created | none |
| AI-kosten | two tables (month totals, calls); month buttons; pager 50 | month totals stay a table; calls: date · module · who · model · status · duration · cost | Deze maand (cost) | month ‹ ›; —; module, provider; date | none (a settings sub-page of Systeeminfo) |
| AI-context | three cards of rows (documents, pages, notes) with an OCR toggle and inline edit | **tabs per kind** (row 37): Documenten · Pagina's · Notities, each a table: label · state badge · read at | — | per tab; label; —; label | + Notitie (on its tab) |
| E-maillog | table, sortable, page size, pager; "Bekijk" opens a modal; `max-w-none` | date · recipient · subject · type · status badge | — | per status; recipient; type, status; sortable | none |

Pages: every list, 50 per page with the count in the toolbar (today only
Leden, Betalingen, Wijzigingen, E-maillog and AI-kosten page). Sort: today
only Wijzigingen, E-maillog and the activity's registrations tab have
sortable columns; in the end state every table column that is sortable
says so, and the default order is the one named above.

### 5.2 Admin record pages

| Screen | Today | End state: header facts · summary card · tabs | Save | Repeating groups · rare section |
|---|---|---|---|---|
| Activiteit | hand-built head with six buttons; per-card edit toggles (activity, each date, component, product, organiser); right rail Publicatie / Deel / Bezetting; tabs Overzicht · Inschrijvingen · Betalingen; `<details>` external links | status first, then access badge; facts: dates · time · location · organiser (jump link) · poster from the Design Studio; summary: state, registrations, children or participants, open balance, the share link; tabs Gegevens · Inschrijvingen · Betalingen; primary Bewerken, menu Acties (Kopiëren, Publiceren, Design Studio, Foto's, Verwijderen) | one save (pilot A) | **sections decided with block 6 (Koen, 4 Oct 2026)**: *Activiteit* (naam, vriendelijke URL as `slug`, locatie, omschrijving, affiche — the poster is public, not internal) · *Publiek* (doelpubliek, enkel leden — one word for the badge and the field) · *Intern* (interne nota only) · the repeating groups: dates (simple), components (composite, **with their products inside**), organisers (simple, a list of members — no roles: they do not exist); Externe koppelingen last; "Geannuleerd" is not a field but the record action "Annuleren"; the component keeps its select "Extra vragen: <formulier>" — "nu / later" is the registrant's choice (CR-14), not a setting |
| Inschrijving | page_header with facts; one panel; edit toggle; two action bars (main, answers); tabs Overzicht · Betalingen | contact name; facts: activity (jump link) · component · registered on; summary: state, total, paid, balance; tabs Gegevens · Betalingen | one save (the answers form folds into it) | product lines, answers; none rare |
| Gezin (household) | head with Verwijderen; person cards with toggles; address card; bestuurslid; lidmaatschappen — a year added or removed in read mode; tabs Overzicht · Inschrijvingen · Betalingen | household name; facts: address · the household's e-mail (jump link) — no household number, it is used nowhere (Koen, 10 Oct 2026); summary on Gegevens: Lidmaatschap <year> badge, Personen, Openstaand — no "Lid sinds", the database does not hold it (Koen, 10 Oct 2026); tabs Gegevens · Inschrijvingen · Betalingen — **no Personen tab** ((Koen, 10 Oct 2026): the persons stand on Gegevens in the shape of Mijn gezin, pilot B; a table beside it would show them twice); a person has no page (Q28); the relation reads **Hoofdlid**, Partner, Kind — never "Contactpersoon" (block 8, Koen, 4 Oct 2026) | one save for the whole household — address, persons, e-mail addresses, bestuurslid ((Koen, 10 Oct 2026); pilot B, the admin side). **The membership years are read-only**: a year is the result of a paid renewal, started with *Lidmaatschap vernieuwen* under Acties — the public flow of `/leden/gezin/vernieuwen` (online or transfer, the same mail), never a typed year; the add-a-year form and the remove-a-year button of today's card go (Koen, 10 Oct 2026) | Gegevens: Hoofdlid (the person's fields, Telefoon included, its e-mail addresses), then **Adres** (straat · nummer · bus · postcode — the address is the household's, shown in the facts line and edited here), Gezinsleden (every person with Telefoon), Lidmaatschap (bestuurslid; the years as a read list); none rare. No sentence about what other domains do with the e-mail addresses — the hint of the e-mail group goes (Koen, 10 Oct 2026). The person block is the compact one of §2.2 (facts with icons, nothing folds, e-mail addresses as lines; Koen, 10 Oct 2026, Q&A 03) and is one macro for Gezin, Mijn gezin and Personen. *Lidmaatschap vernieuwen* under Acties opens the renewal page in the admin shell — the same page as `/leden/gezin/vernieuwen`, as a registration is one page for the member and the board (CR-14 §B4.1): online or transfer, the board may pay online itself (Koen, 10 Oct 2026: "het bestuur kan wel online betalen, raar maar waar"), the same mail. **The relation to the household stands in the title line of the person, not among its fields** (Koen, 10 Oct 2026, both drawn: *"De 'relatie' zo in een dropdown kunnen wijzigen (rechts van de naam, links van verwijderen) vind ik wel prima"*): in read mode a badge right of the name (Hoofdlid · Partner · Kind), in edit mode a small select right of the name with Verwijderen beside it, the main member with the fixed badge; the person's fields are the same for everyone, and Personen shows the block without it |
| Persoon | **no page**: a card on the household page | stays a card on the household page (Koen, 2 Oct 2026, Q28) | — | e-mail addresses |
| Formulier | builder with edit toggle per settings, section, field; option rows with bars; JSON import panel; tabs Formulier · Inzendingen · Resultaten | title with status badge; facts: share link (copy) · submissions · last submission; summary: state, submissions, open since; tabs Opbouw · Inzendingen · Resultaten; menu Acties (Bekijk, Afdruk, Definitie exporteren, Definitie importeren…) | **the builder keeps per-section editing** — a declared exception (Koen, 2 Oct 2026, Q28) | sections (composite, with fields), options (simple); JSON import last |
| Nieuwsbrief | autosave body; audience radios; insert buttons; Raakje panel right; Versturen on its own page; no tabs | **document**: subject as the title, facts: audience · state · last saved; header editor (audience, subject, preview text); body autosaved; primary Versturen…, menu Acties (Voorbeeld, Testmail, Kopiëren, Verwijderen); the Raakje panel docked | autosave + header editor | none; none |
| Vergadering | status badge beside the buttons; attendance; agenda sections with items, notes autosave per item; separate pages for date/place and for sending | **document**: date as the title, status first; facts: time · location · attendance; header editor (date, time, location); the agenda as the body; primary Verslag versturen… / Agenda versturen…; menu Acties (Download PDF, Heropen) | autosave per item + header editor | sections (composite, with items), attendees, attachments; none |
| Pagina (CMS) | one card, sticky head with one save; `<details>` placeholders | **document** (CR-17): title, facts: /slug · gepubliceerd/concept · last published; header editor (title, slug, in navigatie); the body as blocks; primary Publiceren, menu Acties (Voorbeeld, Geschiedenis, Verwijderen) | autosave of the draft, publish as the act (CR-17) | none; none |
| Ontwerp (Design Studio) | four action bars and loose buttons; preview right; `<details>` prompt | activity as the title; facts: template · status · versions; summary: the preview; sections Ontwerp · Beelden (the picker, CR-15) · Varianten · Versies; primary Bewaren en voorbeeld, menu Acties (Definitief maken, Publiceren als affiche, Inkscape, Verwijderen) | one save per section — a declared exception (Koen, 2 Oct 2026, Q28) | images, versions, generations; the prompt text last |
| Gebruiker | inline row, no page (row 44) | record page: e-mail as the title; facts: active · roles; sections Account · Rollen (checkbox group per workspace) | one save | roles per workspace; none |
| Organisatie | sections with one save at the end, `max-w-2xl`; header button to the site settings | name; facts: type · code · legal form; sections as today; menu Acties (Instellingen van de site) | one save (already) | identifications, accounts (CR Organisation: repeatable by standard); none |
| Tenant | key list with a sticky save on top; header button to the organisation | name; facts: code · active; sections Instellingen · Secrets; menu Acties (De organisatie) | one save (already) | none; Secrets as the rare section (collapsed, last) |
| Werkbank-taak | **no header**; `<dl>` rows; one inline form | title as the title; facts: kind · state · created; sections Taak · Besluit; primary Afhandelen | one save | none; none |

### 5.3 Public pages — the kit, not the layouts (§2.4)

| Page | Today | End state (pilot B designs the flows) |
|---|---|---|
| Header and footer | blue band with the logo and inline links; Mijn gezin, Admin, Uitloggen as loose links; a footer with the contact details twice (organisation block and CMS block) and the newsletter line above it | §2.5: the band and the logo stay; the drawer on a phone; one account menu; the footer as newsletter row · socials and sponsors · legal line with the organisation's details from one source |
| Home | blue intro band with CMS text, price, Word lid / Mijn gezin, then the activity cards | own composition: the intro as a CMS document block, the coming activities as cards, one featured activity if the board asks (P4) |
| Activiteiten (agenda) and Archief | cards per year with per-component actions | §2.7 (pilot C): the same cards on kit components — date tile, year heading, facts, component actions; no new composition (the earlier "cards by poster" idea is dropped: Koen wants only sure refinements) |
| Activiteit | h1 with badges, facts, description, one block per component, poster aside | §2.7 (pilot C): the same page on kit components, the way back naming its origin; concept 09's own composition is not built |
| Inschrijven | page with component choice, nudge, contact, products, questions, pay | §2.6: the centred 768 px form page; the nudge above the contact fields; Nu/Later for the questions; the payment radios; "Inschrijven en betalen" |
| Word lid | nudge, person rows, address, payment | §2.6: the composite repeating group, the e-mail group, the address grid, the price card with the payment radios; no nudge, no wizard |
| Formulier | name/e-mail card, section cards paged ‹ › | §2.6: the name card, Contact, the sections as cards on one long page — no steps; its own thank-you page |
| Mijn gezin (the person block follows the household record of §5.2: facts with icons, nothing folds, e-mail addresses as lines — Koen, 10 Oct 2026, Q&A 03: "ik wil dit ook zo in de publieke website") | membership card, person cards with edit toggles and e-mail rows, add card; **no registrations or payments** | the family portal as overview and details: Gezin · Onze inschrijvingen (with the payment state) · Betalingen; one save per the household record rule (pilot B) |
| Foto's and an album | album cards per year; thumbnail grid | §2.7 (pilot C): the album card on the kit's card, the shared year heading, the grid and the lightbox as components with kit icons and a focus trap; clearance honoured (CR-15) |
| Inloggen, Bedankt, Betaling ontvangen, Inloglink verlopen | one-card pages | one-card pages, the same card; **the heading inside the card is the card heading (24 px), never the 40 px page title** — the public page-title size belongs to the title role on the ground, not to every `h1` (Koen, 5 October 2026: "Aanmelden" at 40 px in the sign-in card); the sign-in page says **Inloggen**, the word of the header link since P1 ("Aanmelden" is the newsletter's button) |

**Decided with Koen on 2 October 2026 (CR-11 Q28):** a person stays a card on
the household page — no person page; the form builder and the Design Studio
keep per-section saves as declared exceptions to "one save" (they edit a
composition, not a record); tiles are built only where the figure is acted
on weekly — Werkbank and Abonnees — and elsewhere when asked, so the tiles
column above is the end state for those two and "none until asked" for
Formulieren, Vergaderingen, Nieuwsbrieven, Pagina's and AI-kosten; the
activity's six header buttons become items of its "Acties" menu beside one
primary button (R13).

---

## 6. What refuses a deviation

Two kinds, kept apart (CR-11 B8).

**Mechanical** — `test_ui_conventions_gate.py` and the e2e job, ratchets
from phase 2 on the counts of CR-11 A2, and each one hard on its own the
moment its count reaches zero: layout extended · no raw form element · no
raw spacing class · no raw surface class · no raw checkbox outside a
multi-choice group or consent · no typed "+" in a label · no header button
to another module · no "Bewerken" in row actions · no `overflow-x-auto` on
a list · no `max-w-*` on a screen · no `action_bar` in a repeating-group
row · no `code_label` twice on a row · a long-value field (`url`, `email`,
`textarea`) never half or beside another field · `rare_settings` never
followed by a section · a tile with two figures refused by the macro · tile labels on one line and never cut, figure tops in one tile
row within 1 px, a tile no higher than label plus figure, no row of
controls wider than the page (the document as wide as the viewport at
390 px on every screen) · the first content row on the first screen at
390 × 844 px · no checkbox group in a toolbar, the title's box never squeezed by its actions (the
screenshot set) · no
`btn_*` in a record head outside
`record_header(actions=…)`, and a list header's call slot holds only the
create button and "Instellingen" · the declared save model matches the
macros used · the Raakje trigger by rule · one toolbar per rich text ·
DOM-measurement baselines in JSON diffed — positions, sizes and counts per
kit screen and width, no PNGs in the repository (Koen, 5 October 2026, CR-11
Q60; the stability protocol of CR-11 B7 applies).

**The eye** — the merge gate and the classification of Part 5, where a
test can list candidates from word lists but a person decides: whether a
custom button label names a consequence · whether a figure's label says what it
counts · whether a control is a one-off or a legitimate new component ·
whether a link's text names its target · whether a screen is a record or a
document · which columns a list needs · what a card shows. This document
does not claim hardness there.
