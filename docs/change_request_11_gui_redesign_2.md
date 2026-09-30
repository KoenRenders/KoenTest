# Change Request 11 — GUI redesign 2 (parking lot)

**Project:** Web Portal "Raak Millegem"
**Status:** shaped on 20 September 2026 · brought onto the template of 30 September 2026 · on hold — a parking lot, not a work order
**Applies to:** admin list screens, the public homepage and cards, the admin assistant — GUI work deferred from the v2.5 design track (#913, #996).

> A parking lot: the place where GUI work lands that is consciously *not*
> done yet, so a release can be decided piece by piece without losing the
> rest. Nothing here is assigned; each item returns to the business for a
> separate decision before anyone builds it. When an item is picked up it
> gets its own issue or its own change request; this document remembers
> what was parked and why. The sections that a parking lot cannot fill
> keep the template's note block, as the template prescribes.

---

# Part A — The business

## A1. Reason to act — the trigger

Deciding every GUI candidate the moment it surfaces keeps widening a
release. v2.5 carried the design track plus four other work streams, so the
candidates that were not needed for v2.5 were parked here, to be decided
one by one later — "laten we dat enkel inbouwen in betalingen, de rest is
voor later; dan kunnen we stuk per stuk bekijken wat we nog doen en de rest
parkeren we naar later" (20 September 2026).

## A2. As-is process — how it works today, and where it hurts

Not one process but the screens and the behaviour patterns of the admin and
the public site as they are lived with today. Listed with the person who
uses them daily (Koen, 30 September 2026), one row per pain: which screen or
pattern, what hurts, and — where there is one — a first idea for a solution.
An idea is not a direction: the direction is chosen in Part B, per item,
with the usability arguments beside it.

| # | Screen or pattern | What hurts today | Solution idea | Source |
|---|---|---|---|---|
| 1 | **A repeating group inside a detail** — several e-mail addresses on a person; the same shape for contact details, products under a component, dates on an activity, options on a form field, lines on an order | Every time such a group is built, its behaviour and its look are described again from scratch: where the save button sits, how "make this the main address" looks, that the row title does not repeat per row, the size of the group's heading, the "add" button to the right of the heading. The multiple e-mail addresses (this week: #1223, #1229) were first built as a different screen — ugly, taking far more room than the group deserves — and then corrected point by point, each point a decision the person asking already made elsewhere. A lot of work for the asker, for a thing the application already does several times. | Name it once and build it once: a **repeating group** pattern in the design system (§4, next to P1–P12) with one macro that renders the heading, the "add" action at its right, the rows with their row actions, the one-among-many marker ("hoofdadres") and the save behaviour — rendered live on `/admin/design-system` like the other components. Every existing instance is listed under the pattern and migrated to the macro, so an issue can say "a repeating group of e-mail addresses" and nothing more. The gate that already checks that promised macros exist then guards it. | Koen, 30 Sep 2026 |
| 2 | **Cluttered edit screens** — the activity detail with its components (`_aa_detail.html`) as the example | The screen reads as if each field, radio button and button was added one under the other as it came up: 37 labels, 32 inputs, 7 radio or check controls and 4 action bars in one 422-line template, in one column. Nothing groups what belongs together (a product's price, member price, free and pay-on-site are four separate rows), settings and content sit in one stream, and the eye finds no rhythm. It looks amateurish next to the redesigned list screens. | A **form layout grammar** in the design system, as the list screens got one (§3.2): a screen is sections with a heading, each section a grid that lays related fields side by side on a desktop and stacks on a phone; a small set of control shapes per kind of choice (a segmented control for two or three options instead of a row of radios, a switch for a yes/no, a select above five); settings apart from content; one action bar per section or one per screen, never four. Written once with a live example, then each edit screen is laid out on it — the components screen first, as the worst and the most used. | Koen, 30 Sep 2026 |
| 3 | **Rarely used, discouraged settings take the front row** — the three external links on a component (`external_register_url`, `external_registrations_url`, `info_url`) | They date from the very start, when documents lived in Google Drive and registrations ran on external systems. They are still needed for the odd case and may stay, but they are used in perhaps 2 to 5 % of components, and the platform wants to *discourage* them — yet they take half of the component's form, three full-width fields, as prominent as the name and the price. | A pattern for **the rare and the discouraged**: progressive disclosure. Such settings live in a collapsed section at the bottom of the form ("Externe koppelingen" or "Geavanceerd"), closed by default, with a one-line summary when something is set ("2 externe links") and a short note that the platform's own registration is preferred. Open it and the three fields are there as today. The same shape serves every other rarely used group, so an issue can say "in the advanced section" and be done. Measure the real share on PROD before deciding the wording — 2 % and 20 % ask for a different default. | Koen, 30 Sep 2026 |
| 4 | **Saving behaves differently per detail screen** — a CMS page has a save button at the top and stays open; a meeting saves itself while you type; almost every other screen edits per card with edit → save / cancel | Three ways of saving on screens that are all "a record in detail". The design system decided one (§3.4 record management, P1 *edit and stay*: save and cancel at the bottom, the screen stays, a toast), but two screens went their own way without a rule that says when that is allowed. The user learns three habits for one job, and each new screen is a fresh argument. | Decide **one default** and write the **deviation rule** next to it, so a deviation is a decision and not a habit. The default stays P1 with per-card editing. Deviations are allowed by kind of screen, not by taste: **autosave** where the screen is a *document* — one long text, nothing a rule can refuse, losing typed text is the real risk (meeting notes; possibly the CMS body) — and never on a *record* with fields that validation can refuse; a save button at the top only on a document long enough that the bottom is out of sight, and then the same button at the bottom too. Each detail screen names its save model in one line in §3.4's register; the gate that reads templates checks that a screen declaring "record" uses the edit-toggle macros and one declaring "document" uses the autosave form — so a fourth way cannot appear unnoticed. | Koen, 30 Sep 2026 |

## A3. To-be process — how it should work afterwards

> [!NOTE]
> *How the work should go afterwards: the same drawing and table as A2, the*
> *same lanes in the same order, so the difference is what the eye finds.*
> *Still no components: "the portal renders the poster", not "WeasyPrint*
> *renders the poster". A step that disappears, moves lane or turns into a*
> *choice is the change — name it under the drawing in one line each.*

## A4. Benefits — what the change earns

> [!NOTE]
> *The business side of the decision: what this change earns, in the*
> *measures the association counts in — hours of volunteer work saved per*
> *activity or per year, mistakes avoided, money collected sooner or not*
> *lost, members who would otherwise drop out, a process that becomes*
> *possible at all. One line per benefit, with the figure where it can be*
> *estimated and the reason where it cannot; a benefit that only the*
> *solution can name does not belong here. Set against the cost of B3, this*
> *is what says whether the change is worth doing, and when.*

## A5. Supplied material — and what it taught us

Where each parked item comes from, so the original context can be reread
instead of reconstructed:

| Source | What it holds |
|---|---|
| #913, #996 — the v2.5 design track and its golf packages | the screens as they were redesigned; F10 (ledenlijst as a dense table) left undecided there |
| #1059 — server-side pagination | built for Betalingen only, scoped down on 20 September 2026; Leden and Activiteiten deferred |
| #785 triage, the conventions debate (A12, A17) | sortable columns, column chooser, saved views, command palette, scopes-with-preview for bulk actions — confirmed by all three maker-round directions |
| the Cobalt sketch | the big blue hero card for a featured activity on the homepage |
| #1060 — the admin assistant with screen context | the base on which language-model insights could be built |

## A6. Business requirements — what the board asks, with MoSCoW

Every parked item is a candidate requirement. MoSCoW is **Parked** for all
of them: not a Won't (it may come), not a Could (nothing is planned). Each
row keeps its as-is and the intended direction.

| # | Requirement | MoSCoW | Source | Comment |
|---|---|---|---|---|
| P1 | The admin lists Leden and Activiteiten page like Betalingen does. | Parked | Koen, 20 Sep 2026 | as-is: only Betalingen pages (#1059); decided **together with P2**, because a card list and a dense table page differently |
| P2 | The admin list screens have one settled shape — table or cards — for Leden, Activiteiten and Betalingen alike. | Parked | Koen, 19 Sep 2026 | "Ik twijfel nog altijd of we betalingen ook niet terug moeten zetten naar de cards"; F10 waits until the dense Betalingen screen has been lived with; one decision covers both directions |
| P3 | Bulk actions on admin lists (select many, act once). | Parked | Koen, 19 Sep 2026 | "bulk selectie zou ik voorlopig niet doen"; when it comes, scopes-with-preview as sketched in the conventions debate |
| P4 | The homepage can feature one activity in a large hero card. | Parked | the Cobalt sketch; left out of golf 11 | needs a "which activity" choice by the board and sits above an agenda that already shows the same; candidate: a CMS choice once the board misses it |
| P5 | The admin assistant offers language-model insights on top of the screen context it already has (#1060). | Parked | 20 Sep 2026 | Mistral, Europe First; under the standing rule that every claim carries a clickable source and unsupported claims are dropped |
| P6 | Admin tables follow one set of conventions: sortable columns as the norm, a column chooser, saved views, a Ctrl-K command palette. | Parked | #785 triage | sized for the ERP ambition, not for one release |
| ~~P7~~ | ~~STT and TTS in the Raakje overlay~~ | **un-parked** 20 Sep 2026 | Koen | mic + read-aloud, identical to the rapporten-Raakje — "Raakje is the same everywhere; the only difference is the public security boundary"; now #1075 |

## A7. Non-functional requirements — security, privacy, house style, tenants

> [!NOTE]
> *The requirements every change request is tested against, each answered*
> *explicitly at business level, "not applicable" included. How they are met*
> *belongs in Part B:*

## A8. Acceptance criteria — what the business signs off on HDEV

> [!NOTE]
> *Criteria the business signs off on, each testable by a person on HDEV*
> *without reading code, each pointing at a requirement and at the steps of*
> *the walkthrough (B2.1) that show it. These are the business's unit tests;*
> *the developer's tests live in Part B.*

---

# Part B — The solution

*Empty by design: Part B is written per item, in that item's own issue or
change request, when it is un-parked. The headings stay so the template is
recognisable; every note block below is the template's.*

## B1. Solution outline — the solution and the decisions that shape it

> [!NOTE]
> *The solution in one paragraph, and the decisions that shape it, each with*
> *the alternatives weighed and why they lost (Europe First named where a tool*
> *or service is chosen).*

### B1.1 Functional analysis — the derived requirements

> [!NOTE]
> *The derived, finer-grained requirements the solution answers, traced to A6.*
> *This is design work by the analyst, not business input — which is why it is*
> *not in Part A.*

## B2. Architecture — three readers, three questions

> [!NOTE]
> *B2 answers three questions for three readers, in this order: the business — does the solution fit our to-be*
> *process and our requirements (B2.1)? the architect — how does the whole*
> *hang together across the modules, and what is touched (B2.2)? the build*
> *teams — what exactly must happen in each module, and what does it cost*
> *(B2.3)? Each reader should be able to stop after their section.*

### B2.1 Fit with the process and the requirements — for the business

> [!NOTE]
> *Two things. First, the **application usage drawing**: the to-be process*
> *of A3 once more — same lanes, same activities — with, in every activity*
> *box, a second line naming the screen or module that serves it, the box*
> *coloured per module (`classDef`, one legend line). Every step has a home*
> *or is marked "outside the portal"; a module no step uses is not part of*
> *this change. Two audiences (those who set up, those who use) means two*
> *drawings. Second, the **traceability matrix** — the one place where a*
> *requirement's thread is followed from left to right, so it is not kept*
> *anywhere else: one row per requirement of A6 — R · how the solution meets*
> *it, in the words of the role that will see it · the derived requirements*
> *(F, B1.1) · the module that builds it (B2.3) · the test that proves it*
> *(B7) · the acceptance criterion the business checks (A8). An empty cell*
> *is a finding: a requirement without a test, a test without a*
> *requirement. A Won't gets a row that says so. Third, the **walkthrough** — how the*
> *business tests this on HDEV: one numbered*
> *script per role of A3, in the order of the to-be process, happy path*
> *first and then the turns where it must refuse or fall back; each step*
> *names what to do and what to see — nothing else, it is a script. The*
> *link to the acceptance criteria lives in A8, whose last column names the*
> *steps that show each criterion; every criterion has at least one step.*
> *The closing comment of each issue points at the walkthrough instead of*
> *rewriting it. This is*
> *the page a board member reads to say "yes, that is how we will work, and*
> *this is how I will check it".*

### B2.2 The whole across the modules — for the architect

> [!NOTE]
> *The **application structure drawing**: one subgraph per module touched,*
> *inside it a box per layer (screen · view-model · service · entity ·*
> *facade · migration · template) — a separate box for what is **new** and*
> *for what is **changed** in that layer, and one grey box for what is only*
> *used. Here the colour is the kind of change, not the module: green new,*
> *orange changed, grey unchanged — the module is the subgraph, and B2.1*
> *already coloured per module. One legend line. Arrows between modules*
> *only through a facade (`api.py`), as the import gate enforces; external*
> *systems and data stores as their own boxes. Then the **data model at a glance**: a Mermaid `erDiagram` of the*
> *entities involved with their key columns and relationships, cardinality*
> *on the edges, soft references across schemas drawn as relationships too,*
> *and what is new or changed marked in the label. Under it, in prose: who*
> *calls whom and through which facade, the*
> *direction of every new dependency, the transaction boundary, and the*
> ***impact on the existing architecture** — which existing modules, tables,*
> *screens and contracts are touched, and how the layer rules*
> *(`docs/code-style.md`, the import gate) hold. This is where a*
> *reviewer checks that the change does not bend the architecture.*

### B2.3 Per module: what must happen — for the build teams

> [!NOTE]
> *One subsection per module touched, in build order, each with the same*
> *five headings: **screens** (which, what changes, at which width it is*
> *judged), **code** (view-model · service · entity · facade — the functions*
> *by name), **database** (schema, table, each column with its type,*
> *nullability and constraints, the `ON DELETE` of every FK, the migration*
> *and whether it is additive), **templates*
> *and mail**, **tests** (which of B7). No effort here: the effort per*
> *module and phase is the table of B3, where the cost is added up. Which*
> *requirements a module serves is read from the matrix of B2.1, not*
> *repeated here. A module that is only used, not changed, gets one line. **Reporting*
> *is always one of the modules**, touched or not: the engine reads the*
> *tables through SQL views in the `reporting` schema and through its object*
> *universe, so for every column this change adds, renames, retypes,*
> *retires or gives a new meaning, its subsection says which views and*
> *objects read it (measured, not recalled) and in which phase the view*
> *follows — a view that reads a changed column changes in the same*
> *migration as the column, or the phase says why not; a value change on a*
> *column a view reads is checked against the saved reports on every*
> *environment before the migration. "Reporting — none: no view reads these*
> *columns" is a subsection too.*

### B2.4 Cross-cutting impact — the checklist of what gets forgotten

> [!NOTE]
> *One table, every row answered, "no" included, one sentence each:*
> *reporting views and saved reports (B2.3) · existing tests, e2e*
> *golden flows and 390 px screenshots (B7) · fixed UI decisions and*
> *`CLAUDE.md` · design-system documentation · code lists · events and*
> *handlers · mail templates · migration: additive or contract*
> *(#1255) · tenant settings · env vars · JSON routes and API callers ·*
> *external services (Mollie, mail). A "yes" points at the section that*
> *handles it. The next thing that gets missed becomes the next row.*

## B3. Cost — investment and running cost, and what operations must know

> [!NOTE]
> *Three parts, each with a figure or "none". **Investment:** one table,*
> *module × phase, with the effort to build in CLI-days or person-days (S /*
> *M / L until the team has a track record), a total per module and per*
> *phase; then analysis, review, validation on HDEV and the release steps;*
> *then one-off purchases (a licence, a product, a device). **Running*
> *cost:** what it costs per month or per year once live — usage rights and*
> *paid services (per use and per month, measured where a prototype exists),*
> *storage and backups, hosting, and the maintenance it adds (a job to watch,*
> *a certificate to renew, a dependency to keep current). **Operations:***
> *settings, env vars, limits, kill switch, backups — what the person running*
> *the stack must know. Set beside the benefits of A4: the two together are*
> *the input for the release decision.*

## B4. Detailed decisions — one subsection each, with the reasons

> [!NOTE]
> *The design decisions in full, one subsection each, with their reasons.*

## B5. Privacy and security — the mechanics behind A7

> [!NOTE]
> *How A7's privacy and security answers are implemented: what leaves the*
> *system to whom, what is sanitised, what is logged.*

## B6. Phasing — shippable phases, and what changes on the failure paths

> [!NOTE]
> *Shippable phases, each with what it delivers and its dependencies, one*
> *row per phase: issue · migration · env vars · data · failure paths that*
> *change · manual validation. The "Na de merge" block per phase names what*
> *CI cannot see. The column **failure paths that change** exists because a*
> *change that reorganises behaviour — where a rule lives, who commits, what*
> *a handler does — rarely changes what the system does on the happy path,*
> *and almost always changes what it does when something fails: what rolls*
> *back, what is refused, what is left half done. Name those per phase, so*
> *"no functional change" is a claim about the happy path with the failure*
> *paths listed beside it, and an e2e test that goes red on one of them is*
> *expected, not a surprise. "None" is an answer.*

*Remarks made while listing the as-is that concern phasing — quick wins,
what can wait, what belongs together — are collected here until the phases
are shaped:*

- Row 3 (the collapsed section for the external links) needs no data change and no new component beyond a disclosure the kit already has — a quick-win candidate, and a first instance of the layout grammar of row 2.

## B7. Tests — what the build must prove

> [!NOTE]
> *Two levels. **What the build must prove:** the*
> *new tests, each able to go red, guards proven by violation — numbered, so*
> *B2.3 can point at them per module. **Impact on the test landscape:** which*
> *existing suites, e2e golden flows and screenshot sets change or must be*
> *redone because of this change, per module, with the reason — a screen*
> *that moves, a route that changes, a fixture that no longer matches. A*
> *change that breaks no existing test says so, and why that is plausible.*

## B8. Rule and gatekeeper — what this fixes for all future work

> [!NOTE]
> *An architectural change request fixes a way of doing things, not just one*
> *instance of it. This section makes that explicit, so the decision outlives the*
> *change and the next development follows it without anyone remembering to ask.*
> *Three parts; "no gate" is an answer, with the reason.*
>
> *A rule is fixed only when its gate runs in CI on every push. A rule that lives in a document is a hope; a rule whose test*
> *goes red on the next pull request is a property of the codebase. So the gate of*
> *B8.3 is a pytest in `backend/tests/` that `backend-tests.yml` runs on every*
> *push and PR — not a script someone remembers, not a review checklist. Where*
> *that is impossible, B8.3 says so and names what catches it instead*
> *(a review agent, a release step), and that is a weaker guarantee, written*
> *down as one.*
>
> *1. The rule. One sentence a reviewer can apply, in the form the decision*
> *   takes from now on ("a code list is a code table in the owning domain's*
> *   schema, a label table per language, and an `Enum` only where code branches*
> *   on the value"). Where it ends up: `CLAUDE.md`, `docs/code-style.md` or the*
> *   architecture document — name the place.*
>
> *2. The reach and the baseline. Where the rule applies (the whole codebase,*
> *   or which modules) and how many places violate it today, measured on the*
> *   branch, not recalled. This change request brings that number down — say to*
> *   what. A number that cannot be counted is an intention, not a rule (CR-04,*
> *   Making it checkable).*
>
> *3. The gate. Which test fails when a new development breaks the rule: what*
> *   it looks at, what its message says, and the violation it was proven with*
> *   (B7). Two shapes, chosen by the baseline:*
> *   - Ratchet when the count is not yet zero: a frozen list of today's*
> *     violations that may only shrink (the #780 pattern). Nothing new may join*
> *     it; an entry that disappears from the code must leave the list.*
> *   - Hard gate when the count is zero after this change: any violation is*
> *     red.*
>
> *   Gates come last, not first (CR-04): a gate with a growing exemption list is*
> *   a dead rule, and a gate written too early freezes the wrong understanding.*
> *   Where the rule cannot be checked mechanically, say so and hand it to the*
> *   judgment layer (the `design-conformiteit-bewaker` agent, review) instead of*
> *   pretending a grep is a gate.*
>
> *   The gate is also what makes the rule cheap to follow: for a new case it*
> *   spells out the steps ("a new code list needs a table, a label row per*
> *   language, an `Enum` member and a label call") and fails on the one that was*
> *   forgotten, with the name of the missing piece.*

## B9. Prototype findings — what was measured before the build

> [!NOTE]
> *What was learnt from prototypes before the build (measurements, refusals,*
> *things that did not work).*

## B10. Decisions log — dated answers and open proposals

| Date | Decision | By |
|---|---|---|
| 20 Sep 2026 | CR-11 is a parking lot, not a work order; pagination in v2.5 on Betalingen only; the rest decided piece by piece later. | Koen |
| 20 Sep 2026 | STT/TTS in the Raakje overlay un-parked: mic + read-aloud, the same Raakje everywhere (#1075). | Koen |
| 30 Sep 2026 | Brought onto the change-request template of 30 September; the parked items are candidate requirements P1–P6 in A6. | Koen |

## Q&A log — asked once, answered here

| # | Date | Question (who) | Answer |
|---|---|---|---|
| Q1 | 30 Sep 2026 | Does CR-11 become a real change request on the new template, or stay a parking lot from which each item gets its own CR or issue? (Claude) | *open* |
| Q2 | 30 Sep 2026 | Which of P1–P6 are taken up now, and is there new material — the dense Betalingen screen lived with (P2), the board missing a featured activity (P4)? (Claude) | *open* |

## Non-goals — deliberately outside this change

- Building anything from this list without an un-park decision and its own issue.
- Parking new GUI candidates on a release tracker instead of here.

## Relationship to existing work — issues and change requests

- **#913, #996** — the v2.5 design track this list was deferred from.
- **#1059** — pagination, built for Betalingen; P1 is its continuation.
- **#785** — the conventions debate; P3 and P6 come from its triage.
- **#1060** — the admin assistant's screen context; P5 builds on it.
- **#1075** — STT/TTS in the Raakje overlay, the one item un-parked so far.
- **CR-08 (visual), CR-10 (Design Studio)** — the design work this list sits next to.
