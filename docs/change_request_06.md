# Change Request 06 — Reporting: a universe, a query panel, a pivot table

**Project:** Web Portal "Raak Millegem"
**Status:** Proposal / discussion — not scheduled. Phased, each phase independently
shippable. Written 9 September 2026, reworked 10 September after Koen asked for
self-service in the BusinessObjects sense rather than reports written by the
CLI. The ten questions in §3 are a proposal for him to strike and extend.
**Apply to:** a new `reporting` Postgres schema, a new `reporting` domain under
`backend/app/domains/`, a new screen type in `docs/design-system.md`.

---

## Goal

Managers ask for reporting first. Today the application answers with six KPI
tiles and four export buttons. This change request gives the back office
**self-service reporting**: a **universe** of facts and dimensions over the data
that already exists — members, registrations, payments, memberships, forms —
from which a board member **composes a report or a pivot table in the
browser**, with filters, saves it under a name, and exports it to LibreOffice
Calc. Charts follow from the pivot, because they are the same result drawn
differently.

The model is the BusinessObjects universe: the solution defines the objects
(dimensions, measures, details) and how they join; the user picks objects and
never sees SQL. Reports are not written by the CLI per question; the ten
questions in §3 are the *test set* the universe has to answer, and the first
saved reports that ship with it.

Three constraints, stated up front:

- **No paid tool, no data platform.** Hundreds of members and a few hundred
  payments a year: Postgres answers every question here in milliseconds. The
  value of BusinessObjects was never the tool but the universe underneath it.
  A universe costs no licence.
- **Self-service, within a fence.** The user combines objects; the engine
  writes the SQL, adds the tenant filter, enforces roles per object. No free SQL,
  ever, and no object the user's role could not see on the screens.
- **Export to LibreOffice Calc**, always, of exactly what is on screen — table
  or pivot, with the active filters in the header.

## 1. Current state (measured, 9 September 2026)

| | measured |
|---|---|
| ODS export kernel | `app/kernel/ods.py` (#200), formula-safe, multi-sheet |
| Screens with an export button | 4: payments, activity components, form submissions, member changes — each with its own columns and code |
| Dashboard | 6 KPI tiles (`app/ui/system_ui.py`), no chart, no trend |
| Analysis or report screen | none |
| Chart library | none |
| Tables | 53, of which 13 history tables — trends over time are possible |
| Open issues about reporting | 0 |

## 2. Principles

1. **The universe is the contract.** One semantic layer — objects with Dutch
   names, their SQL expression, their type, their join path — defined once by
   the solution, consumed by everything: the query panel, the pivot, the ODS
   export, charts, and any later self-hosted BI tool. Change the tool, keep the
   universe.
2. **The user composes; the engine writes SQL.** A report is a *selection*:
   which objects, which filters, which layout (table or pivot: rows, columns,
   measures). The engine resolves the joins from the universe's graph,
   aggregates the measures, applies the tenant filter and the role fence, and
   renders. Selections are data, stored per tenant under a name.
3. **One result feeds table, pivot, chart and export.** A number on screen, in
   the crosstab, in the chart and in the spreadsheet is the same number: same
   selection, same query.
4. **Every fact and dimension carries `tenant_id`, and the engine always
   filters on the current tenant.** This is the classic leak in reporting; it is
   a gate, not a habit.
5. **Roles sit on objects, and mirror the screens.** Money measures are
   FINANCE; person-level details are the roles that see the member screens. What
   you cannot see on a screen you cannot put in a report.
6. **One fact per query.** Measures from two facts in one selection is the
   "fan trap" that makes BO universes lie (registrations × payments multiplies
   both). Phase 1 refuses it with a readable message; a later phase may add
   BO-style synchronisation (two queries merged on shared dimensions).
7. **Europe First, no data egress.** Everything renders on our server; nothing
   is sent anywhere. Any later BI tool is self-hosted on our own EU
   infrastructure.

## 3. The ten questions a board member asks (proposal — the test set)

These are not reports the CLI writes; they are the questions the universe must
let a board member answer by composing, and the first saved reports that ship
with it. Each names the fact and the dimensions it needs.

| # | Question | Fact | Dimensions |
|---|---|---|---|
| 1 | How many members do we have, and how does that evolve per year? (households and persons) | memberships | year |
| 2 | How many renew, how many lapse, how many are new — per year? | memberships | year × membership status |
| 3 | Which activities draw the most people, and how does that compare with last year? | registrations | activity × year |
| 4 | What does each activity bring in: charged, received, refunded, balance? | payments | activity |
| 5 | Revenue per month: charged versus received versus refunded | payments | month |
| 6 | What is outstanding, and for how long? | payments | age bucket × payable type |
| 7 | How do people pay — online, transfer, cash — and how fast? | payments | payment method × month |
| 8 | Who are our members: age groups, municipality, household size? | memberships (persons) | age group × municipality × household size |
| 9 | How are the forms used: submissions per form per period? | form submissions | form × month |
| 10 | What needs attention now: open tasks, failed e-mails, payments that need a look? | operations | kind × age |

Questions 1 to 7 are the money and the members; the universe's first three
facts cover them. Questions 8 to 10 follow with the remaining facts.

## 4. Layer 1 — the universe (the durable investment)

### 4.1 Physical layer: a small star in a `reporting` schema

Read-only views, one per fact and one per dimension, in a Postgres schema
`reporting`. Facts hold measures and foreign keys to dimensions; dimensions hold
the attributes a user groups and filters by. Views hide the model's history and
soft-delete mechanics and name things the way a board member does.

| View | Kind | Grain | Content |
|---|---|---|---|
| `f_memberships` | fact | one row per household per membership year | persons, amount charged / paid, status (new / renewed / lapsed) |
| `f_registrations` | fact | one row per registration line | quantity, charged, paid, team present, contact present |
| `f_payments` | fact | one row per payment record | type (charge / refund), amount, amount paid, open balance, days to paid |
| `f_form_submissions` | fact | one row per submission | count, form, period |
| `f_operations` | fact | one row per open item | kind, age |
| `d_date` | dimension | one row per day | year, quarter, month, month label, season |
| `d_activity` | dimension | one row per activity | activity, component, product, season, year |
| `d_household` | dimension | one row per household | household size, municipality, postal code, member since |
| `d_person` | dimension | one row per person | age group, gender code and label, relation type — **no name, no contact data** (§7) |
| `d_payment_method` · `d_payment_status` · `d_membership_status` · `d_form` | dimension | code lists | code and Dutch label, from the code tables (#779) |

Rules for a view:

- `tenant_id` on every fact and dimension; a gate reads `information_schema`
  and fails on any view in the schema without it.
- Soft-deleted rows excluded unless the fact is explicitly about history; the
  view's comment says which.
- Labels come from the code tables (#779): a dimension exposes the code and
  the Dutch label, never a literal.
- Additive changes only; a column is added, never renamed or removed. The
  universe gate (§4.3) catches a broken reference.
- Cross-schema **reads** are allowed here — architecture §8 forbids cross-schema
  foreign keys and writes; a reporting view is the sanctioned read-only consumer,
  created by migrations in the `reporting` domain, depending on every other
  domain and depended on by none.

### 4.2 Semantic layer: the objects

The universe proper is metadata in the `reporting` domain: a list of
**objects**, grouped in **classes** the way a user thinks (Leden, Activiteiten,
Betalingen, Tijd), each with:

| Field | Example |
|---|---|
| name (Dutch, what the user sees) | "Gemeente", "Ontvangen bedrag", "Aantal inschrijvingen" |
| class | Leden · Activiteiten · Betalingen · Tijd · Formulieren |
| type | **dimension** (group / filter by), **measure** (aggregated: sum, count, avg), **detail** (an attribute of a dimension you can show but not group by) |
| source | view and column, or a SQL expression over the view (`sum(amount_paid)`, `count(distinct household_id)`) |
| format | count · money · percentage · days · label |
| role | `admin` (default) · `finance` for money measures · `member_details` for person-level details |
| description | one sentence, shown as a tooltip in the query panel |

Plus the **join graph**: which dimension joins which fact on which key. Facts
never join facts (§2.6). Dimensions shared by several facts (`d_date`,
`d_activity`, `d_household`) are what make "registrations per activity per
year" and "revenue per activity per year" two selections over one universe.

The universe is **declared in code** (the solution's job, like a BO universe
is the designer's job), versioned, and tested (§9). Users compose selections
over it; they do not edit it. Adding an object is a small, reviewed change.

### 4.3 Documentation and gates

- `docs/reporting-universe.md` (English): classes, objects, types, roles, join
  graph — generated from the declaration so it cannot drift.
- Universe gate: every object's source resolves against `information_schema`;
  every fact has `tenant_id`; every measure has a role; every join key exists.
  A view column that disappears makes CI red before a user sees an error.

## 5. Layer 2 — the query panel, the report, the pivot

One screen type, declared in `docs/design-system.md` as type 7 "Rapport", in
the `reporting` domain, built with the existing kit (htmx, the macros). Three
panes, as in the BO query panel:

1. **Objects** — the classes and their objects, with type icons (dimension,
   measure, detail) and a search box; only the objects the user's role allows.
2. **Selection** — the objects chosen for the result, and the **layout**:
   *table* (columns in order) or *pivot* (rows, columns, measures — drop zones,
   Alpine for the drag, the server re-renders the result on every change).
3. **Filters** — a filter per chosen or extra dimension: value list from the
   dimension itself (a `<select>` for code lists, a range for dates and
   amounts), all values travelling together (`ui.filter_bar`). Filters live: the
   result re-renders on change; no "Toon" button.

The **result** is server-rendered from one query:

- **Table**: sortable columns, server-side paging, totals row for measures,
  the one money formatter; every default sort ends in a unique key (#761).
  **Drill-down**: a row whose dimension is an activity, a household or a payment
  links to that record's screen — a report is a way in, not a dead end.
- **Pivot** (crosstab): rows × columns × measures, computed in SQL (`GROUP BY`
  on rows and columns) and laid out in Python — no `crosstab` extension, no
  client-side library. Subtotals per row group, grand total; a column limit
  with a readable message when a column dimension has too many members (a
  pivot with 400 columns is not a report).
- **ODS export** via `kernel/ods.py`: sheet 1 exactly the table or pivot on
  screen with the active filters in the header, sheet 2 the flat detail rows
  behind it for pivoting in Calc, sheet 3 the chart data when a chart is shown.
  Formula-safe, as today.
- **Saved reports**: a selection (objects, filters, layout, sort, chart) gets
  a name, per tenant, in `reporting.saved_reports` (tenant_id, name, owner,
  selection JSON, shared flag, created, updated). Saved reports appear in the
  "Rapporten" menu; a shared one is visible to every role that may see all of
  its objects. The ten questions ship as saved reports, so day one is not an
  empty panel.

The four existing exports migrate onto the panel in a later phase (§8): their
buttons become links to a saved report with the filters preset. Nothing is
removed before its replacement exists.

## 6. Charts — the same result, drawn

Once the pivot exists a chart is not "another story": a bar chart is the
crosstab's rows on the x-axis and its measures as bars; a line chart is the
same with a date dimension on the x-axis; a stacked bar is rows × columns. The
chart reads the pivot result, never a second query, so it can never disagree
with the table.

- Server-rendered SVG (a Jinja macro per chart kind; bar, line, stacked bar in
  the first chart phase), following the dataviz conventions and the tokens; no
  client-side chart library, no data leaving the server. A library, if a chart
  kind ever needs one, is vendored under `/static/vendor`, never a CDN.
- The chart is part of the selection ("show as"), so it is saved with the
  report and exported with it (sheet 3).
- KPI tiles on the dashboard become saved reports rendered as a single number;
  the dashboard stops carrying its own queries.

## 7. Security and privacy invariants (gates, not habits)

1. **Tenant isolation**: `tenant_id` on every fact and dimension (schema gate)
   and injected into every query by the engine, with a test that seeds two
   tenants and proves a selection returns only its own rows — table, pivot,
   export.
2. **Roles on objects**: the objects list shows only what the role allows; the
   engine refuses a selection containing an object outside the role, with the
   reason (#680: assert the reason, not a status).
3. **No person-level data in the universe by default.** `d_person` carries
   age group, gender, relation type — no name, no contact data. Names and
   e-mails are details behind `member_details`, the same role that sees the
   member screens, and never a grouping dimension. A count is a report; a list
   of people is a screen.
4. **One fact per selection** (§2.6), refused with a readable message.
5. **No free SQL, ever.** Selections reference object keys; the engine builds
   SQL from the universe. Object keys, filter values and layout are validated
   against the universe before any query runs.
6. **Exports are logged** (who, which saved report or selection, which filters,
   when) in the audit domain — an export is data leaving the system.
7. **Query limits**: row and column caps, a statement timeout; at this scale
   they never fire, and they are there for the day a selection is wrong.

## 8. Phasing (each phase shippable)

| Phase | Scope | Risk | Schema change |
|---|---|---|---|
| **0** | The ten questions agreed with Koen; the universe designed on paper: classes, objects, join graph, roles (`docs/reporting-universe.md`) | none | none |
| **1** | `reporting` schema: `f_memberships`, `f_registrations`, `f_payments`, `d_date`, `d_activity`, `d_household`, `d_person`, the code-list dimensions; the universe declaration and its gates; the tenant gate; flat dataset ODS export per fact | low | views only |
| **2** | The query panel with **table** layout: objects, selection, filters, sort, paging, totals, drill-down, ODS; saved reports; questions 1–7 shipped as saved reports | medium | `saved_reports` |
| **3** | **Pivot** layout: rows × columns × measures, subtotals, column cap; ODS of the crosstab | medium | none |
| **4** | **Charts** from the pivot result: bar, line, stacked; "show as" saved with the report; dashboard KPI tiles become saved reports | low | none |
| **5** | Remaining facts (`f_form_submissions`, `f_operations`), questions 8–10; the four existing exports migrate onto saved reports | low | views |
| later | Multi-fact synchronisation; Calc directly on the views (read-only role, tunnel); a self-hosted BI tool on the same universe | ops decision | none |

Phase 0 is a conversation, not a sprint. Phases 1 and 2 are the release that
makes the impression Koen is after: a board member opens the panel, drags
"Activiteit" and "Aantal inschrijvingen" and "Jaar" into a table, filters on a
season, and takes it home as a spreadsheet — without anyone having built that
report.

**Build or buy, stated once.** Apache Superset offers a semantic layer, an
explore panel, pivots and charts, self-hosted, with row-level security in the
open-source edition; Metabase offers the same with sandboxing only in its paid
tier. Both are a second application with their own login, their own look and
roughly a gigabyte of memory, next to a stack that today runs in one backend
container. Building the panel on the kit keeps one login, one look, the
tenant fence inside our own code, and no extra container; the universe (§4) is
the same work in either case. At this scale, build. If a tenant ever needs
what Superset has and we do not, the universe is the part that moves over.

## 9. Testing

- **Known-seed numbers per fact**: seed a known situation (two tenants, three
  years, a refund, an open balance, a lapsed membership) and assert the exact
  counts and sums each fact and each of the ten saved reports return. A
  plausible but wrong number is reporting's worst failure; only known seeds
  catch it.
- **Tenant isolation** on table, pivot and export (§7.1).
- **Role fence**: a FINANCE measure in a selection by an admin without FINANCE
  is refused with the reason.
- **Fan-trap guard**: a selection with measures from two facts is refused.
- **Equivalence**: totals row equals the sum of the rows; the pivot's grand
  total equals the table's total for the same selection and filters; the chart
  series equals the pivot; ODS sheet 1 equals the screen.
- **Universe gate** (§4.3), in both directions: remove a view column an object
  references → red with the object's name; restore → green. Note in the
  docstring what was broken.
- **Reproducible screenshots** of the panel, a table and a pivot join the
  design review rounds (#785): a board member's first impression is a report.

## 10. Non-goals

- **No BI tool, no data warehouse, no Snowflake, no ETL.** Views on the live
  database, at this scale.
- **No free SQL for users**, and no user-editable universe. Objects are added
  by a reviewed change; that is an hour, not a project.
- **No multi-fact queries in the first phases** (§2.6).
- **No PDF reports, no scheduled e-mailing.** Later, if asked; the single-query
  design makes both cheap.
- **No client-side chart or pivot library.** Server-rendered, kit-consistent.
- **No person listings from the universe** (§7.3).
- **No reports reading ORM models.** The layer gate extends to the `reporting`
  domain: its UI reads the engine, the engine reads the universe, the universe
  reads views.

## 11. Relationship to existing work

- **CR-04 (placement rule)**: the universe is a reader; it contains no
  business rules. What a status *means* is decided in the domain and exposed
  by the view.
- **#779 (codes and labels)**: code-list dimensions expose code and label from
  the code tables; no label dict anywhere in reporting.
- **`docs/design-system.md`**: screen type 7 "Rapport", the pivot as a
  component, the chart macros; the live component page (#783) shows them.
- **#785 (design direction)**: the panel, a table and a pivot join the review
  rounds.
- **#761 (sort tiebreaker)**: every default sort ends in a unique key.
- **#171 (ML / predictions)**: consumes the same facts; independent otherwise.
- **Umami** is web analytics (visits), not business reporting; it stays
  separate.
- **The four existing exports** (#200, #307, #512) become saved reports in
  phase 5; nothing is removed before its replacement exists.
