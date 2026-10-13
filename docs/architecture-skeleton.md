# The architecture document, restructured — the skeleton

**What this file is.** The skeleton of the restructured `docs/architecture.md`:
the five parts, their headings, and for every section of today's document where
it goes. Step 1 of the three Koen agreed to on 13 October 2026 (Q&A of 11 October
2026, nr. 02, question 7: *"a"* — skeleton first, then part by part against the
code, then the templates and the PDF build). When parts A to E are filled and
measured, this skeleton becomes `docs/architecture.md` and this file goes.

**Why.** Koen, 11 October 2026 (voice message, three points): the document
follows the shape of the change request template, so that every change request
updates it in a known place; the gates and rules that make development
predictable — *het harnas* — become a chapter of their own, because the ambition
is a software company that builds for other companies and continuity and
predictability matter; and the document is the as-is, with one chapter that
traces every planned evolution and improvement point. The PDF build stays in the
repository, the Mermaid diagrams stay, the visualisations get one convention.
Costs do not belong in the architecture document; the standards table does.

**Decided on 13 October 2026** (Q&A of 11 October 2026, nr. 02, Koen's answers):

| Q | Decision | Koen's words |
|---|---|---|
| 1 | `CONTRACT.md` is the home of a module's section; the PDF build takes part B from the fifteen contracts, nothing stands twice | "a" |
| 2 | `architecture.md` is the project's as-is document; chapter 8 and the *Gespreksleidraad* move to a reference-architecture document that quotes it; the evolutions stay in the architecture document (part E) | "a, maar ook wel de evoluties erin (zie hoger)" |
| 3 | every gate file carries a one-sentence docstring (refuses · form · since), a gate requires it, the build reads the gates table from those sentences | "akkoord" |
| 4 | one evolutions table (id · what · why · track · status), "→ En" references in the text, no other roadmap markings; closed at step 14 of every release; rejected choices stay with their reason | "akkoord" |
| 5 | the standards table sums only what is followed and what deliberately deviates; "checked, not applicable" stays in the change request | "a" |
| 6 | the diagram conventions: six kinds with one purpose each, three colour classes from the brand tokens (in a change request the colour is the kind of change), `flowchart TB` also for the layer picture, a lifecycle per module with a status column drawn from the code in step 2, the fourteen existing figures converted at the move of their section in step 2 (Q&A of 13 October 2026, nr. 02, with rendered examples) | "a" to each of the five questions |
| 7 | skeleton first, then part by part against the code, C and E first; the counting can go to the design-documentation CLI | "a, en weet dat er tegenwoordig een "design-documentation" CLI is die goedkoper tellingen etc doet" |

**Status tags of the new document.** Two, not four: the text describes `master`
at the tag in the head; what is not built stands in part E with its status.
[PROD], [HDEV], [PARTIAL] and [ROADMAP] go — they said at four places what one
line in the head and one table say better.

---

## The head of the new document

```
title: Architecture — the Raak platform
Version: 2.0 — <date>
As-is: master @ <sha>, released as v<X.Y.Z> on <date>; PROD runs v<X.Y.Z>
Scope: every claim is traceable to code (Appendix B); planned work stands in part E
```

No subtitle, no author line with a company: the document describes the project.
The version line is updated at step 14 of every release, by the architecture CLI.

## Part A — The solution

Mirrors A1–A3 and B1–B3 of the change request template: what it is, which
processes it automates, how it is built and run.

| § | Heading | Comes from | To measure in step 2 |
|---|---|---|---|
| A1 | What it is and for whom | §1 (the summary, minus the pitch) | the first tenant, the platform tenant, CR-19 tenant kinds |
| A2 | The processes it automates — one subsection each: membership and renewal · activities with registration and payment · meetings · newsletter · web content and forms · reporting and the change report · the poster studio · the chatbot · the webshop (CR-21, when built) | new; today scattered over §1, §3.3–3.5, §7.1 | one BPMN level-1 drawing per process (the convention of Q&A 13 October nr. 02) and the screens that carry it |
| A3 | Principles — each with where it is enforced | §2 (2.1–2.9) | every "enforced by" against the gate list of part C |
| A4 | System context and deployment | §3.1 | the compose files, the shared Caddy, the three environments |
| A5 | The way of working — short, pointing to `AGENTS.md`: the two kinds of working copy, the release steps, the builders outside the Claude series, the review doors; one `gitGraph` | new; §6.1 | the fourteen release steps as they stand in `AGENTS.md` |
| A6 | The GUI layer — the two shells, the kit, the design system (`docs/design-system.md` is the norm; `docs/design-system-end-state.md` the target), how a screen is built (view-model, template, htmx) | new; §2.2 | the macro list of `_macros.html`, the two shells, the list and record layouts |
| A7 | The module map — kernel, domains behind facades, events, ports and reads, jobs, history, when to build more | §3.2, §3.2.1 | fifteen packages, the kernel modules, the contracts in `kernel/contracts/` |
| A8 | A request, end to end — the gatekeeper ladder, the request flow, roles and where a user lands, the workbench | §4.1, §4.2, §4.4, §4.5 | the gatekeepers in `main.py` order; `docs/rollen-en-rechten.md` against the code |
| A9 | Money — the ledger, online payment and the untrusted webhook, the order-mail rule | §4.3 | the reconciliation invariant's one home; the webhook re-fetch |
| A10 | Tenancy and security — the tenant model and resolution, modules per tenant, the security controls | §5.1, §5.3, §5.4 | tenant-scoped tables (63 on 26 September), the module registry of CR-19 |
| A11 | AI in the solution — what runs, the tool boundary, Europe first | §7.1; §2.9 | the providers, the allow-listed tools, what is mocked in CI |

§5.2 (honest gaps) and §7.2 (the mailing engine) do not come to part A: each gap
and each designed-only feature becomes a row of part E.

## Part B — Per module

Fifteen sections, one per package under `backend/app/domains/`, each the module's
`CONTRACT.md` (decision 1). The PDF build includes them; `architecture.md` carries
only this introduction and the order: the two foundation domains first (`mdm`,
`auth`), then the business domains in the order of the processes of A2, then the
cross-cutting ones (`workflow`, `reporting`, `mail`, `media`, `chatbot`,
`designstudio`).

The headings every contract gets — today's five stay, four are added — proposed
to the master CLI for `docs/CONTRACT-template.md` (a process document; the
architecture CLI does not edit it) and for the module-shape gate of CR-13 that
requires the file:

| Heading | Today | Content |
|---|---|---|
| Purpose and process | new | one paragraph: what the module is for, which process of A2 it carries, its aggregates |
| Owns | `Bezit` | schema, aggregates, reference codes, jobs; the data model as an `erDiagram`; a lifecycle as a `stateDiagram-v2` where a status column exists |
| Publishes | `Publiceert` | facade functions with their invariant; events |
| Consumes | `Consumeert` | facades, events, ports |
| Screens | `Schermen` | the routes and the navigation items |
| Standards | new | the rows of part D this module implements (standard · element · our name · follows / deviates with reason) |
| Rules and gates | new | the rules that live in this module (`code-style.md`, *A rule has one home*) and the gates in its own `tests/` |
| Deprecations | `Deprecaties` | as today |
| Evolutions | new | the rows of part E that touch this module, by id |

The new headings are English, as all new documentation is; the five existing
ones stay as they are until the template is revised in one go.

## Part C — The harness

The rules and the gates that give predictable development without drift.
Mirrors B7 and C7 of the change request template.

| § | Heading | Comes from | To measure in step 2 |
|---|---|---|---|
| C1 | The rules and where each lives — `AGENTS.md` (the process), `docs/code-style.md` (the code), `docs/design-system.md` (the screens), `docs/change_request_template.md` (a change), `docs/review-protocol.md` (a review); one table: rule · home · gate that holds it | new | every rule named in A3 and in the gates has a home |
| C2 | The gates — one table generated from the docstrings (decision 3): file · refuses · hard or ratchet · since; the two baselines that may only shrink (the Dutch identifiers #780, the hand-drawn lists #1911); the meta-gate that refuses an empty gate | §6.2, §2.7 | 53 files on 13 October 2026 (`test_*gate*.py`, `*ratchet*.py`; a glob finds 54 because `test_registration_aggregate.py` matches on *aggregate*); each gets its sentence; a gate on the sentence |
| C3 | The CI — the jobs, what each blocks, what is reporting only (`pip-audit`), the measurement baseline, the e2e suite | §6.2 | `.github/workflows/` against the text |
| C4 | The judgment layer — the merge gate on the rendered screen at 390 px, the two read-only agents, the build read of a change request, the review on request | §6.4; `AGENTS.md` | the agent files, the review protocol |
| C5 | The process gates — issue first, the release steps 1–14, HDEV before the tag, the three confirmations, close-out of a change request at step 14 | §6.1 | the table in `AGENTS.md` |
| C6 | What the gates caught — the failures that made each rule, as evidence | §6.3 | the docstrings of the gates ("what I broke") |

## Part D — Standards

One table, summed from B3a of every change request (decision 5): standard ·
element · our table or column · module · follows / deviates with reason. Only what
is followed and what deliberately deviates; a new standard enters only through a
change request.

Sources to sum in step 2: the B3a tables of CR-12 to CR-31; the rule *Modelleer op
standaarden* in `AGENTS.md` (UBL 2.1 / EN 16931 for party, address, identification
and payment; ISO 20022 for accounts; ISO 6523 for organisation identifiers); the
OpenDocument exports; the language codes of `mdm.language_codes`; BPMN level 1 as
the drawing standard of A2.

## Part E — Evolutions

| § | Heading | Comes from |
|---|---|---|
| E1 | The as-is line — version, tag, date, what PROD runs (the same as the head) | the head |
| E2 | The evolutions — one table: id (E1, E2, …) · what · why · track (CR-nn or #issue) · status (planned / in build / built in vX.Y.Z / rejected); the text refers with "→ En"; rejected choices stay with their reason (the React question among them) | §9 (R0–R11), §5.2 (the four gaps), every [ROADMAP] marking, the open change requests with their tracking issues |
| E3 | The change log of the document — release · change request · sections touched | new; filled from step 14 of every release from v2.17 on |

## Appendices

| Today | Becomes |
|---|---|
| Appendix A — documentation versus code (July 2026) | goes once part A is measured against the code (decision 2's reading: its job is done by the measurement) |
| Appendix B — evidence index | stays, re-measured; every row's files exist |
| Chapter 8 — from association to enterprise | `docs/reference-architecture.md`, with the *Gespreksleidraad* and the `enterprise` figure; it quotes the architecture document and carries its own date |
| Gespreksleidraad | the same |

## Where every section of today's document goes

| Today | New place |
|---|---|
| 1 Executive summary, Table 1 | A1; Table 1 re-measured; the "how it was built" paragraph to C |
| 2 Principles 2.1–2.9 | A3 (2.9 also A11) |
| 3.1 System context and deployment | A4 |
| 3.2 Component map · 3.2.1 Events, ports and reads | A7 |
| 3.3 Master data and membership | A2 (the process) + B `mdm`, `membership` (the model) |
| 3.4 Activities, registrations and the ledger | A2 + A9 + B `activities`, `payment` |
| 3.5 Form engine, CMS, media and workflow | A2 + B `forms`, `cms`, `media`, `workflow` |
| 4.1 Gatekeeper ladder · 4.2 A request end to end | A8 |
| 4.3 Money | A9 |
| 4.4 Roles · 4.5 The workbench | A8 |
| 5.1 Tenant model · 5.3 Modules per tenant · 5.4 Security controls | A10 |
| 5.2 Honest gaps | E2, one row per gap |
| 6.1 The loop | A5 + C5 |
| 6.2 Test layers | C2 + C3 |
| 6.3 What the gates caught | C6 |
| 6.4 Two read-only agents | C4 |
| 7.1 AI today | A11 |
| 7.2 The mailing engine [ROADMAP] | E2 |
| 8 From association to enterprise | `docs/reference-architecture.md` |
| 9 Way forward (R0–R11) | E2 |
| Appendix A | goes after the measurement of A |
| Appendix B | Appendix B |
| Gespreksleidraad | `docs/reference-architecture.md` |

## Alignment with the change request template

Proposed to the master CLI for `docs/change_request_template.md` (a process
document), so that step 14 of the release becomes checkable:

- **B3** gets one line: *which module sections of part B of the architecture
  document change* (the contracts touched).
- **B3a** says that its "follows" and "deviates" rows are summed into part D at
  the close-out; "checked, not applicable" stays here.
- **C10** gets the line: *which sections of the architecture document were
  updated — part B of the modules touched, part D for a new standard, part E (the
  row closed or added), the change log E3*.
- **The diagram conventions** (Koen, 13 October 2026, Q&A nr. 02, "a" to each
  of the five questions), for the template and for part A of the document:
  - six kinds, one purpose each: `flowchart LR` for a process (lanes per actor,
    the BPMN level-1 palette A2/A3 already prescribe) — **a process of up to
    about eight steps and three lanes lies (LR); an end-to-end process stands
    (TB, the lanes as columns), and when a standing figure no longer fits one
    page it is cut: one overview figure with the handovers between the parties,
    then one figure per part** (Koen, 13 October 2026, to the choice between
    Mermaid standing for long and lying for short, a BPMN tool outside Mermaid,
    and cutting: "a, met c zodra een staande figuur niet meer op één pagina
    past"). **An end-to-end figure draws the business process, not the
    system** (Koen, 13 October 2026, the convention he knew from a company he
    worked at, approved on three rendered examples: "ja"): the lanes are people
    and roles only — the member, the member administration, the treasurer, an
    outside party such as the national association; the colour of a step is the
    tool it is done in: platform blue with the module in brackets ("Boekt de
    betaling in (Betalingen)"), white for a step done by hand without any tool
    ("Denkt eraan de wijzigingen op te halen"), orange for a step done in
    another system (Mollie, the bank, the national programme); a task the
    workbench hands the person is a green hexagon labelled `Taak: … (werkbank)`;
    a lane *Platform, uit zichzelf* exists only for what the system does without
    a person — checking a webhook, putting a task ready, a timer — and is left
    out where there is none. So a figure shows where the platform guides the
    process and where the person has to know it alone: the member
    administration has no platform lane and white boxes, payments have a task.
    Part A draws every business process end to end this way, as-is; a task that
    does not exist yet is a row in part E, not a box; `flowchart TB` for a
    structure (layers, module map, tenant hierarchy, test layers);
    `sequenceDiagram` for a course in time between parties (request, webhook,
    event chain), numbered, with a note where an invariant sits; `erDiagram` for
    a data model, with key columns and cardinality, a reference across a schema
    drawn as a line labelled "by value"; `stateDiagram-v2` for the lifecycle of a
    record; `gitGraph` once, for the branch model;
  - three colour classes from the brand tokens, named in the legend sentence:
    kernel (fill `#e8f0ff`, stroke `#0051a4`), domain (white, stroke `#52607a`),
    external (fill `#fff7ed`, stroke `#f16532`); in a change request the colour
    is the kind of change — new (fill `#eef7ee`, stroke `#005d29`), changed
    (orange), unchanged (fill `#eef3f9`, stroke `#d7e0ec`) — and an external
    system is a double-bordered box;
  - one figure line above every diagram (`<!-- figure: name=… caption=… -->`,
    `wide=1` for a landscape page), at most one screen high (about fifteen
    boxes, else a second figure), one sentence under each figure saying what to
    see, no semicolon in a label;
  - considered and not chosen, with the reason in the Q&A: `C4Context`,
    `block-beta` (also for the layer picture: one kind for every structure),
    `timeline`, `journey`, `gantt`, `classDiagram` (only CR-13's OO figure),
    `zenuml` (a second notation for the same picture, ignores the theme),
    `requirementDiagram` (repeats the requirement and rule tables of a change
    request as boxes), and the charts.

## Tooling to extend — one issue each, after the skeleton is read

- `scripts/build-doc-pdf.sh` / `docs/build/build_doc_pdf.py`: an include line
  per module (`<!-- include: backend/app/domains/<m>/CONTRACT.md -->`) so part B
  is taken from the contracts; the gates table of C2 generated from the first
  line of every gate file.
- A gate that requires the one-sentence docstring on every `test_*gate*.py` and
  `*ratchet*.py` (refuses · form · since), proven red with one file without it.
- `docs/CONTRACT-template.md`: the four new headings (via the master CLI).

## Order of work and who measures

C and E first (the most outdated, closest to Koen's second and third point),
then A, B, D. Each part is moved **and** measured against `master` in the same
commit: counts, file names, gates, with the sources in Appendix B.

Counting that the design-documentation CLI can do cheaper (Koen, 13 October
2026), handed over by the master CLI as a bounded task per part, each answered
as a list the architecture CLI folds into the text; the two sessions never
write in the same working copy:

- C2: the 53 gate files with, per file, what it refuses and whether it holds a baseline;
- A7/B: tables per schema, tenant-scoped tables, facade functions per module;
- A6: the macros of the kit and the screens on each layout;
- D: the B3a rows of every change request, collected into one list;
- E2: the open change requests with their tracking issues and status.
