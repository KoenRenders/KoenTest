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

**Two priorities, one kit** (Koen, 2 October 2026): the public site is
designed phone-first — 390 px is where a public page is drawn first and
judged first; the back office is designed desktop-first — 1 440 px is where
an admin screen is drawn first (1 920 is common and must be used), 1 440 px
is the lower bound where everything still fits, and 390 px
is the floor: never broken, the few simple actions (look up, confirm,
check, read) reachable, but not a day's workplace. The rules below hold on
both faces; the priority says which width a block is designed at first.

**Breakpoints follow the content, not two device classes.** In the back
office everything fits down to 1 440 px — the navigation (220 px), the
summary column (300 px), the margins and a two-column form; **below 1 440
the sidebar collapses to an icon rail** and the frame collapses
by content, not by device: the summary card moves above the content when
the content column would drop under 640 px, and the form grid goes to one
column when a half field would be narrower than 260 px, down to the 390 px
floor (Koen, 2 October 2026).
At any width the user may collapse the navigation to an icon rail to gain
room, and the choice is remembered (Koen, 2 October 2026). Board desktops are commonly 1 920 px wide (Koen, 2 October 2026): a list
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

- **The way back** on the first line, to the list it came from **as it was
  left** — the same filter, search, sort and page: the list's state is its
  URL, a row's link carries it, and the layout returns to it (a local path
  only; the list's default when the record was opened from elsewhere). A
  screen never writes this link itself. [28, 57]
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
`segmented`, `checkbox_group`, `radio_group`, `upload`, `url`. **The kind
decides the width:** `url`, `email`, `textarea` and rich text are always
full; `number`, `date`, `time`, a code, a short `select` and `switch` are
half or quarter; `text` is half unless `long=True`; a template may widen a
short field and never narrow a long one — a long field with `span="half"`
is red. No raw `<label>`, `<input>`, `<select>` or `<textarea>` in a domain
template. [23, 24, 54]

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

- **`switch`** for a boolean setting; label at the left, "aan"/"uit" for
  the screen reader; disabled in read mode, showing its state. [8]
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
"Verstuur naar 312 abonnees"). `sm`. Sticky at the bottom on a phone,
primary full width. Never in a card header, never inside a repeating-group
row. [22, 46, 50]

### 3.7 `pager(page, size, total)`

Two renderings from one macro: in the toolbar row the count "x–y van n"
with the page-size select; at the bottom "‹ vorige · volgende ›". Always a
total (an approximate "van meer dan 10 000" where counting is heavy);
"Pagina n" does not exist. Hidden when everything fits. [6]

### 3.8 `tiles(items)` — one figure per tile

Inline in the title row: **one figure** per tile (`text-2xl
font-extrabold`; the macro takes a single value and refuses a pair or a
stacked amount — two things to do are two tiles, "Nog te ontvangen" and
"Nog terug te betalen"), label (`text-xs`), optional second line of
context that is not a second figure); the label is always one
line — the macro cuts it with "…" and never wraps it, the full text in
the `title` — and the figure sits directly under it at a fixed distance,
so the figures of one row are on one line by themselves and a tile is no
higher than label plus figure; tile labels are short by rule ("Open
inschrijving", not "Activiteiten met open inschrijving"): a label fits
on one line in the narrowest tile of its row at 390 px or it is
rewritten — the ellipsis is a safety net, a real label that gets cut is
red, and what does not fit goes into the tile's one line of context or a
hint that works on touch [55, 58, 60]; each a link that sets the list's
filter;
the active tile marked. A tile colours only when its figure asks for
attention (an open balance, an overdue count). [10, 36, 52]

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
| P3 · The way back | on every record page, first line, to the list as it was left: a list's state (filter, search, sort, page, page size) is its URL, pushed by the list layout; the record layout returns to the address the row carried. [28, 57] |
| P6 · Import in steps | **widened:** every import that creates, updates or deletes; the report in three lines; the commit names the consequence. [18] |
| P8 · List, detail, edit | **revised:** the row opens the record; on a top-level list the record page, inside a record's related list an in-place unfold with a jump link. [26] |
| P13 · Opens shows | a control that opens something shows that it opens — chevron, "…", disclosure triangle. [48] |
| P14 · The member nudge | on every public registration and on "Word lid", unconditional, above the contact fields, with the sign-in link that returns. [21] |
| P15 · One fact once | a status in its badge, a count in a tile, a setting behind Instellingen; never twice on one screen. [38, 10] |
| P16 · The screen owns the selection | a selector belongs to the screen; Raakje and the manual inserts read it. [41] |

---

## 5. Classification — every screen, its kind and its shape

Measured on `master` after v2.11.0 (2 October 2026, HEAD 5e52292e) and
written as the end state: the **kind** and the **shape** are fixed here;
what is marked *proposed* is the author's draft of the per-screen columns,
confirmed with Koen at that screen's phase (pilot A for Activiteiten and
Betalingen, the roll-out for the rest). Today's state stands beside it so
the distance is visible. The rules behind the columns: a tile is one
figure, a filter, a one-line label (rows 36, 52, 58, 60); a row shows the
same three or four things for every record, omitted when they do not apply
(row 36); the toolbar is one row — chips, search, filters, the count with
the page size, `⋯` (rows 6, 45); every list pages (P1); no list scrolls
sideways (row 11); the row is the way in (row 26); the list's state is its
URL (row 57).

### 5.1 Admin list pages

Shell width for every list: the wide frame (row 11); today three lists set
`max-w-none` themselves and the rest take the shell's reading width.
"Today" names the shape, the tiles and the toolbar as measured.

| Screen | Today | End state: a row shows | Tiles (*proposed*) | Toolbar: chips · search on · filters · sort | Header |
|---|---|---|---|---|---|
| Activiteiten | cards; tiles Open inschrijving · Volzette onderdelen; search, chips Komende/Archief/Alles; no pager | name with status badges · first date and time · location · registrations count (omitted without a component) | Open inschrijving · Volzet onderdeel (activities with one) | Komende · Archief · Alles; name, location; year; date | + Nieuwe activiteit |
| Leden | cards; three tiles; search, chips Alle/Actief/Opgezegd, year select; pager 25 | household name · municipality · persons · membership state badge | Actieve gezinnen · Actieve personen · Te vernieuwen (year) | Alle · Actief · Opgezegd; name, street, e-mail; membership year; name | Leden importeren · + Nieuw lid |
| Betalingen | table grouped per registration; four tiles; status tabs with counts, search, context filter, status select; pager 50; export in the filter bar; `max-w-none` | name/reference · context · status badge · amount · received · balance (W1's two tiles carry the totals) | Netto te betalen · Ontvangen · Nog te ontvangen · Nog terug te betalen | Alle · Openstaand · Betaald · Terugbetaald; name, OGM, description; context, status; date · export under `⋯` | none (the breadcrumb goes; row 35) |
| Formulieren | cards; search, status select; no pager | title · status badge · submissions count · last submission | Open · Inzendingen deze maand | Alle · Open · Gesloten; name; —; updated | Instellingen (holds "Formaat (voor AI)", row 34) · + Nieuw formulier |
| Vergaderingen | cards; search; no pager | date · status badge · location · points count | Volgende · Verslag open | Komende · Voorbije; date, location; year; date | Instellingen · + Nieuwe vergadering |
| Nieuwsbrieven | cards; search; no pager | subject · status badge · audience · sent or updated moment · while sending: progress | Verstuurd dit jaar · Abonnees | Concept · Verstuurd; subject; audience; updated | Instellingen · Abonnees · + Nieuwe nieuwsbrief |
| Abonnees | table; search, status select; inline Uitschrijven/Verwijderen; add-form card under the table | address · first name · source · status badge · since | Bevestigd · Wachten · Uitgeschreven | Alle · Bevestigd · Wachten · Uitgeschreven; address, first name; —; since | Lijst importeren · + Adres (replaces the form card) |
| Pagina's | cards; search, chips; manual order with ↑↓; no pager | title · /slug · gepubliceerd/concept badge · in navigatie badge | Gepubliceerd · Concept | Alles · Gepubliceerd · Concept · In navigatie; title, slug; —; manual order (the handle of the repeating-group row) | + Nieuwe pagina |
| Media | inline-edit cards in a 2-column grid; search, kind select, activity select; no pager | **cards (grid)** — the one admin exception: thumbnail · title · kind · origin (activity) · clearance badge (CR-15) | — | Alle · per kind; title; activity, year, in gebruik (CR-15); newest | + Uploaden |
| Design Studio | cards without thumbnail; search; no pager | **thumbnail column** (the latest render) · activity · status badge · versions · updated | — | Alle · Gepubliceerd · Verouderd; activity; —; updated | + Nieuw ontwerp |
| Gebruikers | inline-edit list, one form per row; search, role select, active chip | e-mail · active badge · roles as chips (row 44: the row opens the record) | Actief | Actief · Alle; e-mail; role; e-mail | + Nieuwe gebruiker |
| Organisaties | cards; search, type select; empty header | name · type badge · code · legal form · inactive badge | — | Alle · per type; name, code; —; type, name | none (created elsewhere, by design) |
| Tenants | cards; search, status select | name · /code · active badge · platform badge | — | Actief · Inactief; name, code; —; id | + Nieuwe tenant |
| Rapporten | cards with description and chips; search, owner and shared selects; AI buttons in the header | name · shape icon · privé/meegeleverd badge · owner · last opened | — | Mijn · Meegeleverd · Alle; name, description; owner; name | + Nieuw rapport (the AI buttons go: Raakje is the shell's trigger, row 32) |
| Wijzigingen | table, sortable, page size, pager; `max-w-none` | when · change badge · group badge · person · details · object (jump link) · actor | — | per group; actor; from date; sortable columns | Ledenexport (.ods) under `⋯` |
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
| Activiteit | hand-built head with six buttons; per-card edit toggles (activity, each date, component, product, organiser); right rail Publicatie / Deel / Bezetting; tabs Overzicht · Inschrijvingen · Betalingen; `<details>` external links | status first, then access badge; facts: dates · time · location · organiser (jump link) · poster from the Design Studio; summary: state, registrations, children or participants, open balance, the share link; tabs Gegevens · Inschrijvingen · Betalingen; primary Bewerken, menu Acties (Kopiëren, Publiceren, Design Studio, Foto's, Verwijderen) | one save (pilot A) | dates (simple), components (composite, with products), organisers (simple); Externe koppelingen last |
| Inschrijving | page_header with facts; one panel; edit toggle; two action bars (main, answers); tabs Overzicht · Betalingen | contact name; facts: activity (jump link) · component · registered on; summary: state, total, paid, balance; tabs Gegevens · Betalingen | one save (the answers form folds into it) | product lines, answers; none rare |
| Gezin (household) | head with Verwijderen; person cards with toggles; address card; bestuurslid; lidmaatschappen; tabs Overzicht · Inschrijvingen · Betalingen | household name; facts: address · persons · membership year (badge); summary: membership state, persons, open balance; tabs Gegevens · Personen · Inschrijvingen · Betalingen | one save (pilot B, the admin side) | persons (composite, each with e-mail addresses as a simple group), memberships; none rare |
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
| Home | blue intro band with CMS text, price, Word lid / Mijn gezin, then the activity cards | own composition: the intro as a CMS document block, the coming activities as cards, one featured activity if the board asks (P4) |
| Activiteiten (agenda) and Archief | cards per year with per-component actions | cards by poster, grouped per month or year; one action per activity ("Inschrijven" leads to the activity page or straight to the form when there is one component) |
| Activiteit | h1 with badges, facts, description, one block per component, poster aside | own composition (concept 09): poster, key facts, what to expect, who is coming, the sticky price-and-button card, the nudge |
| Inschrijven | page with component choice, nudge, contact, products, questions, pay | the form page at reading width (CR-14 §B4.1, P1–P15 parity); the nudge above the contact fields (W17) |
| Word lid | nudge, person rows, address, payment | the form page; the person rows a repeating group (pilot B) |
| Formulier | name/e-mail card, section cards paged ‹ › | the form page; sections as steps where long |
| Mijn gezin | membership card, person cards with edit toggles and e-mail rows, add card; **no registrations or payments** | the family portal as overview and details: Gezin · Onze inschrijvingen (with the payment state) · Betalingen; one save per the household record rule (pilot B) |
| Foto's and an album | album cards per year; thumbnail grid | cards (the picture is the content); the album grid with the lightbox; clearance honoured (CR-15) |
| Bedankt, Betaling ontvangen, Inloglink verlopen | one-card pages | one-card pages, the same card |

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
screenshot baselines diffed (with the stability protocol of CR-11 B7).

**The eye** — the merge gate and the classification of Part 5, where a
test can list candidates from word lists but a person decides: whether a
custom button label names a consequence · whether a tile filters what it
counts · whether a control is a one-off or a legitimate new component ·
whether a link's text names its target · whether a screen is a record or a
document · which columns a list needs · what a card shows. This document
does not claim hardness there.
