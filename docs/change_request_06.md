# Change Request 06 — Reporting

**Project:** Web Portal "Raak Millegem"
**Status:** Proposal / discussion — not scheduled. Phased, each phase independently
shippable. Written 9 September 2026 after a conversation with Koen; the ten
questions in §3 are a proposal for him to strike and extend.
**Apply to:** a new `reporting` Postgres schema, a new `reporting` domain under
`backend/app/domains/`, a new screen type in `docs/design-system.md`.

---

## Goal

Managers ask for reporting first. Today the application answers with six KPI
tiles and four export buttons. This change request gives the back office a
**reporting facility over the datasets that already exist** — members,
registrations, payments, memberships, forms — that a board member can use
without anyone building a screen per question, and that exports to LibreOffice
Calc.

Three constraints, stated up front:

- **No paid tool, no data platform.** Hundreds of members and a few hundred
  payments a year: Postgres answers every question here in milliseconds. The
  value of BusinessObjects or Power BI was never the tool but the semantic layer
  underneath it. That layer costs no licence.
- **Reusable, not rebuilt per question.** A report is a *definition*, not a
  screen. Define the dataset, columns, filters and grouping once; the engine
  renders the filter bar, sorting, paging, drill-down, chart and export. This is
  the lesson Koen took from Logi XML, and it is the core of this CR.
- **Export to LibreOffice Calc**, always, from every report, of exactly what is
  on screen — plus the flat dataset for people who pivot themselves.

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

Every export today is a loose button on a screen with its own column list. That
is the "build it again every time" this CR removes.

## 2. Principles

1. **Datasets are the contract.** Reports read views in a `reporting` schema,
   never ORM models or domain tables. Whatever tool comes later — the in-app
   engine, Calc, a self-hosted BI tool — consumes the same views. Change the
   tool, keep the datasets.
2. **A report is a definition.** Dataset + columns + filters + grouping +
   measures + chart, declared in code. The engine does the rest: filter bar,
   sort, paging, totals, drill-down to the record, chart, ODS. No report has its
   own template.
3. **One query feeds table, chart and export.** A number on screen, in the chart
   and in the spreadsheet is the same number, because it came from the same
   query with the same filters.
4. **Every view carries `tenant_id`, and every report filters on the current
   tenant.** This is the classic leak in reporting; it is a gate, not a habit.
5. **Money reports sit behind FINANCE**, the rest behind the general admin
   roles — the same matrix as the screens (`docs/rollen-en-rechten.md`).
6. **Aggregate, do not list, in demographic reports.** Age and place
   distributions are shown as counts per bucket, never as rows per person; a
   bucket below a threshold (five) is merged. Listing people is what the member
   screens are for.
7. **Europe First, no data egress.** Charts are rendered on our server; nothing
   is sent anywhere. Any later BI tool is self-hosted on our own EU
   infrastructure.

## 3. The ten questions a board member asks (proposal)

The first deliverable is not code: it is this list, agreed. Each question names
the dataset it needs (§4) and the report that answers it (§5).

| # | Question | Dataset | Report |
|---|---|---|---|
| 1 | How many members do we have, and how does that evolve per year? (households and persons) | `v_memberships` | members per year |
| 2 | How many renew, how many lapse, how many are new — per year? | `v_memberships` | renewal funnel |
| 3 | Which activities draw the most people, and how does that compare with last year? | `v_registrations` | registrations per activity, year over year |
| 4 | What does each activity bring in: charged, received, refunded, balance? | `v_payments` × `v_registrations` | revenue per activity |
| 5 | Revenue per month: charged versus received versus refunded | `v_payments` | revenue per month |
| 6 | What is outstanding, and for how long? | `v_payments` | outstanding by age |
| 7 | How do people pay — online, transfer, cash — and how fast? | `v_payments` | payment method and days-to-paid |
| 8 | Who are our members: age groups, municipality, household size? | `v_persons_aggregated` | member demographics (aggregated) |
| 9 | How are the forms used: submissions per form per period? | `v_form_submissions` | form activity |
| 10 | What needs attention now: open tasks, failed e-mails, payments that need a look? | `v_operations` | operations overview |

Questions 1 to 7 are the money and the members; they come first. Questions 8 to
10 follow once the engine exists.

## 4. Layer 1 — the reporting views (the durable investment)

A Postgres schema `reporting` with one read-only view per dataset. Views are
the semantic layer: they name things the way a board member does, join what
needs joining, and hide the model's history and soft-delete mechanics.

Rules for a view:

- **Name** `reporting.v_<dataset>`, English, one grain per view (one row per
  membership-year, one row per registration, one row per payment record).
- **`tenant_id` is a column of every view.** A gate test reads
  `information_schema.columns` and fails on any view in the schema without it.
- **Soft-deleted rows are excluded** unless the dataset is explicitly about
  history; the view says which in its comment.
- **Labels come from the code tables** (#779): a view exposes `status` (the
  code) and `status_label` (the Dutch label), never a literal.
- **Additive changes only.** A column is added, never renamed or removed, in a
  new migration. A report that reads a column that disappeared is a broken
  contract; the gate for §5 catches it.
- **Cross-schema reads are allowed here, cross-schema writes and FKs are not.**
  Architecture §8 forbids cross-schema foreign keys; a reporting view *reads*
  across schemas and is the sanctioned consumer. It lives in the `reporting`
  schema, is created by a migration in the `reporting` domain, and depends on
  every other domain — like a facade consumer, never a dependency of one.
- **Documented in `docs/reporting-datasets.md`** (English): per view its grain,
  columns, source tables and the questions it answers. The data dictionary is
  generated from the view comments where possible, so it cannot drift.

First views, matching §3:

| View | Grain | Key columns |
|---|---|---|
| `v_memberships` | one row per household per membership year | year, household id, status (new / renewed / lapsed), persons, municipality, payment status |
| `v_registrations` | one row per registration | activity, component, date, quantity, team, contact present, charged amount, paid amount |
| `v_payments` | one row per payment record | payable type, activity or membership, type (charge / refund), method, status, amount, amount paid, created, paid at, days to paid, age bucket of the open balance |
| `v_persons_aggregated` | one row per (bucket) | age group × municipality × household size, count — pre-aggregated, threshold applied |
| `v_form_submissions` | one row per submission | form, period, source |
| `v_operations` | one row per open item | kind (task / failed mail / payment needing attention), age, link |

## 5. Layer 2 — the report engine (screen type "Report")

One screen type, declared in `docs/design-system.md` as type 7, and one engine
in the `reporting` domain. A report is a `ReportDefinition` in code:

```python
@dataclass(frozen=True, kw_only=True)
class ReportDefinition:
    key: str                      # "revenue-per-month"
    title: str                    # "Omzet per maand"
    dataset: str                  # "reporting.v_payments"
    role: str                     # "finance" | "admin"
    filters: tuple[Filter, ...]   # year, activity, status, method …
    columns: tuple[Column, ...]   # what the table shows, with format (money, count, %)
    group_by: tuple[str, ...]     # e.g. ("month",)
    measures: tuple[Measure, ...] # sum(amount), count(*), avg(days_to_paid)
    default_sort: tuple[str, ...] # always ends in a unique key (#761)
    chart: Chart | None           # kind (bar / line / stacked), x, series
    drill: Drill | None           # which column links to which record screen
```

From that one declaration the engine renders — with the existing kit, nothing
new — :

- **the filter bar** (`ui.filter_bar`, `ui.grouped_filter`, `ui.chips`), live,
  all values travelling together; the filters are the definition's, so a report
  cannot forget to offer them (Logi's "the filters were already there");
- **the table** (records-list layout C1): sortable columns, server-side paging,
  a totals row for measures, amounts formatted by the one money formatter;
- **drill-down**: a row links to the record it summarises (the activity, the
  payment, the household) — a report is a way in, not a dead end;
- **the chart**, server-rendered SVG from the same result set (bar, line,
  stacked bar; nothing else in phase 1), following the dataviz conventions;
  no client-side chart library and no data leaving the server;
- **the ODS export**, via `kernel/ods.py`: sheet 1 exactly what is on screen
  with the active filters in the header, sheet 2 the flat filtered dataset for
  pivoting, sheet 3 the chart data. Formula-safe, as today;
- **saved reports**: a definition plus a set of filter values gets a name, per
  tenant, and appears in the "Rapporten" menu (`reporting.saved_reports`:
  tenant_id, name, report key, parameters JSON, created by). This is what "not
  rebuilt every time" means for the treasurer.

The existing four exports migrate onto the engine in a later phase (§8) and
their buttons become links to the corresponding report with the filters
preset. Until then they stay as they are.

## 6. Layer 3 — Calc, and later a BI tool

- **Dataset export**: every view is exportable as a flat ODS with one click, so
  a board member pivots in Calc. Cheapest large win; ninety percent of the
  "live in Excel" need.
- **Calc directly on the database** (ODBC/JDBC on the views with a read-only
  role) is possible but needs port 5432 reachable, which is deliberately not the
  case. Not in this CR; noted as a later ops decision with an SSH tunnel or a
  read replica.
- **A self-hosted BI tool** on the same views is a one-afternoon addition once
  layer 1 exists, and a second source of drifting definitions without it.
  Options, all self-hosted so the data stays in the EU: Apache Superset (ASF;
  row-level security in the open-source edition; heavy), Metabase (US, open
  core; row-level sandboxing is paid — a real limit for multi-tenancy), Grafana
  (dashboards, less suited to tabular reports), Lightdash (UK, dbt-based). No
  EU-born BI tool fits; self-hosting is the Europe First route. Not now.

## 7. Security and privacy invariants (gates, not habits)

1. **Tenant isolation**: every view has `tenant_id` (schema gate) and every
   report query filters on the current tenant (engine, with a test that seeds
   two tenants and proves a report shows only its own rows).
2. **Role**: a report declares its role; the engine enforces it; a money report
   without `finance` fails a gate.
3. **Aggregation threshold** in demographic views: no bucket below five.
4. **Exports are logged** (who, which report, which filters, when) in the audit
   domain — an export is data leaving the system.
5. **No ad-hoc SQL from the browser**, ever. Reports are definitions in code;
   parameters are validated against the definition's filters.

## 8. Phasing (each phase shippable)

| Phase | Scope | Risk | Schema change |
|---|---|---|---|
| **0** | The ten questions agreed with Koen; `docs/reporting-datasets.md` with the six views specified | none | none |
| **1** | `reporting` schema, views `v_memberships`, `v_registrations`, `v_payments`; the `tenant_id` gate; dataset ODS export | low | views only |
| **2** | The engine with three reports: members per year, revenue per month, outstanding by age; filter bar, table, totals, drill, ODS | medium | `saved_reports` table |
| **3** | Charts (SVG), the remaining money and member reports (2, 3, 4, 7), saved reports in the menu | low | none |
| **4** | Questions 8–10: aggregated demographics, forms, operations; the four existing exports migrate onto the engine | low | views |
| later | Calc on the database; a self-hosted BI tool | ops decision | none |

Phase 0 is a conversation, not a sprint. Phases 1 and 2 are the release that
makes the impression Koen is after: three reports a board member can open,
filter, read as a chart and take home as a spreadsheet.

## 9. Testing

- **Each view has a numbers test**: seed a known situation (two tenants, three
  years, a refund, an open balance) and assert the exact counts and sums the
  view returns. A view that returns a plausible but wrong number is the worst
  failure mode of reporting; only known seeds catch it.
- **Tenant isolation test** on every report, as in §7.
- **Equivalence tests**: the totals row equals the sum of the rows; the chart
  series equals the table column; the ODS sheet 1 equals the table. Without
  these, three renderings of one query drift apart in a year.
- **Role tests** on money reports, asserting the reason, not just a status
  ≥ 400 (#680).
- **Definition gate**: every `ReportDefinition` references only columns its
  view has (read from `information_schema`), and its default sort ends in a
  unique key (#761).
- **Reproducible screenshots** of the three phase-2 reports join the design
  review rounds (#785).

## 10. Non-goals

- **No BI tool, no data warehouse, no Snowflake, no ETL.** Views on the live
  database, at this scale, are the right answer.
- **No ad-hoc query builder for users.** A new question is a new definition in
  code, reviewed like any change; that is a day, not a project.
- **No PDF reports, no scheduled e-mailing of reports.** Later, if asked; the
  engine's single-query design makes both cheap to add.
- **No client-side chart library in phase 1.** Server-rendered SVG covers bar,
  line and stacked bar; if a chart type needs a library, it is vendored under
  `/static/vendor`, never a CDN.
- **No per-person demographic listing.** Aggregated only (§2.6).
- **No reports reading ORM models.** The layer gate extends to the `reporting`
  domain: its UI reads the engine, the engine reads views.

## 11. Relationship to existing work

- **CR-04 (placement rule)**: a report is a reader; it contains no rules. What
  a status *means* is decided in the domain and exposed by the view.
- **#779 (codes and labels)**: views expose code and label from the code
  tables; reports never carry a label dict.
- **`docs/design-system.md`**: screen type 7 "Report" and, once built, the
  chart macros in §2; the live component page (#783) shows them.
- **#785 (design direction)**: the three phase-2 reports join the review
  rounds; a board member's first impression is a report, so it has to look the
  part.
- **#761 (sort tiebreaker)**: default sorts in definitions end in a unique key.
- **#171 (ML / predictions)**: consumes the same views; independent otherwise.
- **Umami** is web analytics (visits), not business reporting; it stays
  separate.
- **The four existing exports** (#200, #307, #512) become reports in phase 4;
  nothing is removed before its replacement exists.
