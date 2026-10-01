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

### 1.1 Kit tokens and brand tokens — two files

| Kit (the platform's; a second organisation inherits them) | Brand (the tenant's; a second organisation replaces them) |
|---|---|
| the surface scale, the spacing scale, radii, elevation, the widths | the eight brand colours, the two fonts, the wordmark |
| the icon *vocabulary* (verb → glyph) and the one-meaning-per-glyph rule | the icon *set* and its line style (Lucide, 1.75 px today) |
| control shapes and sizes, the button hierarchy, the layouts | photos, posters, the public site's decoration |

`scripts/build-css.sh` reads both; a template names a token, never a
value. (Phase 2. Rows 9, 16; R12.)

### 1.2 Surfaces — three levels, and nothing else

| Token | What | Text on it | Border |
|---|---|---|---|
| `surface-page` | the page ground, one light grey | `ink` | — |
| `surface-card` | a card, white, radius 18 px, one soft shadow | `ink` / `ink-soft` | `border-card` |
| `surface-inset` | a block inside a card (a summary line, a read-only group), lighter grey, radius 12 px | `ink-soft` | none |

The shell paints `surface-page`; the card macro paints `surface-card`; the
inset is only ever inside a card. The same three on the public site and in
the admin. No `bg-*` class in a domain template. (Phase 2. Row 9.)

### 1.3 Spacing — where each step of the scale goes

The scale stays (4 · 8 · 12 · 16 · 24 · 32 · 48 · 64). What is new is the
binding: each step has one use, applied by a macro, never by a template.

| Step | Use | Applied by |
|---|---|---|
| 4 | label to control; icon to its text | `field`, `btn_*` |
| 8 | button padding; gap between chips | `btn_*`, `chips` |
| 12 | field to field inside a section | `form_grid` |
| 16 | card padding; gap between toolbar controls | `card`, `toolbar` |
| 24 | card to card; summary card to content | layouts |
| 32 | section to section inside a form | `section` |
| 48 | header to content on a record page | `record_page` |
| 64 | page margin on a desktop | shells |

(Phase 2. Rows 2, 23.)

### 1.4 Widths — three, set by the layout

| Layout | Desktop | Phone (< 768 px) |
|---|---|---|
| list page | wide: `max-w-7xl`, 1280 px | one column, 16 px gutters |
| record page | wide frame `max-w-7xl`; the form column `max-w-3xl`, 768 px, centred in the frame | one column, 16 px gutters; the summary as a strip above |
| document page | reading width `max-w-3xl`, centred | one column, 16 px gutters |

**Breakpoints follow the content, not two device classes.** Between the
phone and a wide desktop lies the small laptop (1024 px) where the
navigation (220 px), the summary column (300 px), the margins and a
two-column form cannot all fit: the summary card moves above the content
when the content column would drop under 640 px, the navigation collapses
to icons under 1100 px, and the form grid goes to one column when a half
field would be narrower than 260 px. Concepts and screenshots are judged at
390, 768, 1024 and 1440 px. A screen never sets `max-w-*` on its root.
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
| more / ⋯ | `ellipsis` | Raakje | `sparkles` |

(Phase 2. Rows 16, 20, 34.)

### 1.6 Type

Unchanged from `design-system.md` §1.2 and §1.2a (Inter body, Radio
Canada Big display, the mobile-first scale), with one correction, measured
against the app and not the concepts (30 Sep 2026): a field label stays
14 px, what `ui.label` renders today (the concepts drew 13 and the review
read 11 — both wrong); a tile's label is 13 px, replacing the 11 px of
today's Betalingen tiles, and comes with the tiles macro; small text
(11–12 px) is for supplementary information only. Radius: the concepts
test 12 px for admin cards (calmer, denser) against the current 18 px,
which the public site keeps — decided at phase 0 (CR-11 Q18). The record header's title is
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
│ (chips: alle · open · …)  [search…] [filter ▾] [filter ▾]  1–50 van 312 · 50 ▾  [⋯] │  toolbar row
│ ┌ table or cards ─────────────────────────────────────────────┐ │
│ │ row (the whole row is the link)                        [⋯] │ │
│ │ …                                                           │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                        ‹ vorige   volgende ›      │  bottom navigation
└───────────────────────────────────────────────────────────────────┘
```

- **Title row:** the title (`h1`); at its right the KPI **tiles** inline
  (figure and label, no card around them; each a filter: it says what it
  counts and which rows open — a count opens the rows counted, a sum opens
  the rows summed, "activiteiten met een volzet onderdeel" counts
  activities and not components; a figure that can do neither is not a
  tile); then "+ Nieuw <item>" and, when the module has configuration,
  "Instellingen" with the gear. Nothing else: no link to another module, no
  explanation line, no breadcrumb (the menu shows the place). [31, 34, 35,
  36, 45]
- **Toolbar row:** status chips at the left; search; the filters; the
  count "x–y van n" with the page size (25 · 50 · 100); `⋯` with export and
  the rest. One row; it wraps only on a phone. [6, 45]
- **The list:** in the admin always a **table** (a picture is a thumbnail
  column); cards only on the public site and in the media library. Sortable
  columns as the norm, a column chooser under `⋯`; no horizontal scrolling
  ever — columns fit, secondary ones hide as the width shrinks, rows stack
  on a phone. A card or row shows only what applies to that record —
  omitted, not zeroed. [5, 11, 36, P6]
- **The row is the way in:** click it and the record page opens; the whole
  row is the target, with hover and a focus ring; on a phone the whole card,
  44 px high at least. "Bewerken" is not a row action; `⋯` keeps delete,
  duplicate and quick state changes. [26]
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

- **The way back** on the first line, to the list it came from, filter
  state preserved. [28]
- **The record header:** the title with its badges on the title line,
  status first; the facts line under it, every reference a jump link; at
  the right the screen's one primary and one "Acties ▾" menu holding the
  rest (photos, Design Studio, print, delete…). Never a button named after
  the fields it edits. [39, 29, 20]
- **The summary card** at the right of the content column, `max-w-xs`:
  the state, two or three figures, the main action; on a phone a compact
  strip above the tabs. [25]
- **The tabs:** "Gegevens" first, then the related lists in the same order
  on every entity (Inschrijvingen · Betalingen · …), each with its count.
  A related-list tab is the list layout in its **embedded rendering**: no
  page header, no tiles (the summary carries the figures), one toolbar row,
  the table; a row there unfolds in place with a jump link to its page.
  The header, tabs and summary do not move between tabs; only the content
  column is narrow or wide. [19, 27, 29, 26]
- **Read mode** shows data and navigation, nothing that edits: every
  field the editor has, in the same sections and order, empty ones as "—",
  a yes/no in plain words ("Enkel leden: ja") — not as a disabled control;
  no add buttons, no drag handles, no row menus until "Bewerken". [7]
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
check) in pilot B — a public activity page and "Mijn gezin" are more than
a form page and get their own composition there. Today the site shell
(`site_base.html`) hosts two shapes: a **card list** (the
activities with their posters, the photo albums) and a **form page**
(register for an activity, become a member, a public form, the family
portal) — the form page is the record layout's form column at reading
width, centred, with the same surfaces, grid and action bar as the admin,
and the member nudge above the contact fields. The public activity list
keeps its cards: the poster is the content. [9, 12, 21; CR-14 B4.1]

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
`segmented`, `checkbox_group`, `radio_group`, `upload`. No raw `<label>`,
`<input>`, `<select>` or `<textarea>` in a domain template. [23, 24]

### 3.2 `form_grid` and `section(title)`

A section is a heading (`text-base font-semibold`) over a two-column grid
at reading width; a field spans half by default, `span="full"` for long
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
("hoofdadres") as a chip on the row; "nog geen …" and the add button when
empty; the rows are committed with the screen's save, never on their own.
Instances: contact details, addresses, activity dates, components,
products, form options, order lines. [1, 50]

### 3.4 `rare_settings(title, summary)`

A collapsed section at the bottom of a form, closed by default, a
disclosure triangle, a one-line summary when something inside is set
("2 externe links"), a short note when the content is discouraged ("de
eigen inschrijving heeft de voorkeur"). Instances: the component's
external links, the activity's poster URL. [3]

### 3.5 Controls

- **`switch`** for a boolean setting; label at the left, "aan"/"uit" for
  the screen reader; disabled in read mode, showing its state. [8]
- **`segmented`** for two or three exclusive options (table · cards;
  nu · later). [2]
- **`checkbox_group`** for several out of a list, and a single checkbox for
  a consent; nowhere else. [8]
- **`select`** above five options; `radio_group` only where the options
  need a line of help each.

### 3.6 `action_bar(form, …)`

One per screen (or per sub-record with its own lifecycle). Right-aligned:
"Annuleren" as a text button, "Opslaan" as the primary; "Verwijderen" as a
red text action at the far left. Labels are the macro's defaults; a custom
primary label only for a named consequence ("Definitief importeren",
"Verstuur naar 312 abonnees"). `sm`. Sticky at the bottom on a phone,
primary full width. Never in a card header, never inside a repeating-group
row. [22, 46, 50]

### 3.7 `pager(page, size, total)`

Two renderings from one macro: in the toolbar row the count "x–y van n"
with the page-size select; at the bottom "‹ vorige · volgende ›". Always a
total (an approximate "van meer dan 10 000" where counting is heavy);
"Pagina n" does not exist. Hidden when everything fits. [6]

### 3.8 `tiles(items)`

Inline in the title row: figure (`text-2xl font-extrabold`), label
(`text-xs`), optional second line; each a link that sets the list's filter;
the active tile marked. A tile colours only when its figure asks for
attention (an open balance, an overdue count). [10, 36]

### 3.9 `record_header(title, badges, facts, primary, actions=[…])` — actions as data

Title line with badges (status first); facts line with reference links;
at the right **one primary button and one "Acties ▾" menu, never more**.
The screen hands its actions as a list, each with a kind — *record action*
(duplicate, print, export, send, reopen, delete) or *tool* (photos, Design
Studio) — and the macro places them: record actions first in a fixed
order, tools under a divider, delete last after a divider; Raakje is never
among them (it is the shell's trigger). A screen cannot draw a button of
its own in the head: a `btn_*` call there outside the macro is red. On a
phone there is nothing to overflow — the title truncates, the two controls
stay on the title line. Where each kind sits on the other layouts is the
table in CR-11 B4.3 (list: create and "Instellingen" in the title row;
document: the same menu; public: one primary in the sticky card, no
menu). First applied to the activity's head (#1387) and the "Kopiëren" of
#1397, whose place was decided four times before this rule existed. [39,
51]

### 3.10 `summary_card(state, figures, action)`

Right column on a desktop (`max-w-xs`, `surface-card`), a strip above the
tabs on a phone: the state badge, up to three figures with labels, one
action. [25]

### 3.11 `reference(record)` — the jump link

The record's name as a link to its detail, `arrow-up-right` after it,
`text-blue-500` underlined, the way back preserved. The only way a field
that *is* another record is rendered; a name in blue always goes to the
record it names. [20, 30]

### 3.12 `related_tabs(tabs)`

The tab bar of the record page: "Gegevens" first, then the related lists
with counts, the same order per entity across the portal (defined once per
entity in Part 5). [19]

### 3.13 `toolbar(…)`

The list's second row: chips, search, filters, pager count, `⋯`. The
embedded rendering drops the chips' page-level variants and keeps one
status filter. [45, 29]

### 3.14 `account_menu`

A round badge with the initials, a chevron, hover, focus ring,
`aria-haspopup`; opens a menu whose first line is "Aangemeld als …", then
"Mijn profiel", "Werkruimte wisselen", "Uitloggen". One source, rendered in
the desktop bar and at the bottom of the phone's navigation sheet. [47, 48]

### 3.15 `raakje_panel`

One trigger (`sparkles`) in the shell chrome on both sides; opens a side
panel docked right (a bottom sheet on a phone) with the screen's context;
enabled per module by rule (the module's objects are in the reporting
universe, or its facade exposes commands), otherwise greyed with "Raakje
kent deze gegevens nog niet". The screen owns its selections; the panel
reads them. The assistant page and the per-screen `AI ·` buttons do not
exist. [32, 33, 41]

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

Every layout has these states drawn in the design-system page: a
**validation error** on save (the bar stays, the banner at the top of the
form, the first refused field scrolled into view and marked, every typed
value kept); **saving** (the primary shows a spinner and is disabled, the
form stays editable-looking but locked); **save failed** (the error banner
with the reason, P7, nothing lost); **empty** (one sentence and the create
action, §2.8); **no access** (the page says so and offers the way back);
**autosave** on a document ("opgeslagen om 21:14", "opslaan…",
"niet opgeslagen — opnieuw proberen" in the facts line).

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
| P3 · The way back | on every record page, first line, filter state preserved. [28] |
| P6 · Import in steps | **widened:** every import that creates, updates or deletes; the report in three lines; the commit names the consequence. [18] |
| P8 · List, detail, edit | **revised:** the row opens the record; on a top-level list the record page, inside a record's related list an in-place unfold with a jump link. [26] |
| P13 · Opens shows | a control that opens something shows that it opens — chevron, "…", disclosure triangle. [48] |
| P14 · The member nudge | on every public registration and on "Word lid", unconditional, above the contact fields, with the sign-in link that returns. [21] |
| P15 · One fact once | a status in its badge, a count in a tile, a setting behind Instellingen; never twice on one screen. [38, 10] |
| P16 · The screen owns the selection | a selector belongs to the screen; Raakje and the manual inserts read it. [41] |

---

## 5. Classification — every screen, its kind and its shape

Measured on `master` on 30 September 2026. The **kind** is fixed here; the
per-list columns (tiles, card fields) are drafted and confirmed at that
screen's phase. "Save" is the save model of Part 2.

### 5.1 Admin list pages

| Screen | Shape | Tiles (draft) | Pages | Settings button |
|---|---|---|---|---|
| Activiteiten | table | toekomstig · volzette onderdelen | yes | — |
| Leden | table | leden · te hernieuwen · nieuw dit jaar | yes | — |
| Betalingen | table | netto te betalen · ontvangen · openstaand (two sides) | yes | — |
| Formulieren | table | open · inzendingen deze maand | yes | — |
| Vergaderingen | table | volgende · verslag open | yes | Instellingen (the circle) |
| Nieuwsbrieven · Abonnees | table | verstuurd dit jaar · abonnees | yes | Instellingen |
| Pagina's | table | gepubliceerd · concept | yes | — |
| Media | **cards (grid)** | — | yes | — |
| Design Studio | table with thumbnail column | — | yes | — |
| Gebruikers | table | actief | yes — small today, but no screen is the exception for being small (CR-11 row 44) | — |
| Organisaties · Tenants | table | — | no (small) | — |
| Rapporten | table | — | no | — |
| Wijzigingen | table | — | yes | — |
| Werkbank | table | open · vandaag | yes | — |
| AI-kosten | table | deze maand | yes | — |

### 5.2 Admin record pages

| Screen | Save | Related tabs (in this order) |
|---|---|---|
| Activiteit | record, one save | Gegevens · Inschrijvingen · Betalingen |
| Inschrijving | record, one save | Gegevens · Betalingen |
| Gezin (household) | record, one save | Gegevens · Personen · Inschrijvingen · Betalingen |
| Persoon | record, one save | Gegevens · Inschrijvingen |
| Formulier | record (builder), one save | Opbouw · Inzendingen · Resultaten |
| Nieuwsbrief | **document** (autosave body) | Inhoud · Versturen |
| Vergadering | **document** (autosave body) | Document · Versturen |
| Pagina (CMS) | **document** (autosave body) | Inhoud · Publicatie |
| Ontwerp (Design Studio) | record, one save | Ontwerp · Varianten |
| Gebruiker | record, one save | Gegevens |
| Organisatie · Tenant | record, one save | Gegevens |
| Werkbank-taak | record, one save | Taak |

### 5.3 Public pages

| Page | Shape |
|---|---|
| Home, Activiteiten, Foto's | card list |
| Activiteit, Inschrijven, Word lid, Formulier, Mijn gezin, Contacteer ons | form page (reading width, centred, the nudge where a member could sign in) |
| Bedankt, Betaling ontvangen, Inloglink verlopen | form page, one card |

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
row · no `code_label` twice on a row · no `btn_*` in a record head outside
`record_header(actions=…)`, and a list header's call slot holds only the
create button and "Instellingen" · the declared save model matches the
macros used · the Raakje trigger by rule · one toolbar per rich text ·
screenshot baselines diffed (with the stability protocol of CR-11 B7).

**The eye** — the merge gate and the classification of Part 5, where a
test can list candidates from word lists but a person decides: whether a
custom button label names a consequence · whether a tile filters what it
counts · whether a control is a one-off or a legitimate new component ·
whether a link's text names its target · whether a screen is a record or a
document · which columns a list needs · what a card shows. This document
does not claim hardness there.
