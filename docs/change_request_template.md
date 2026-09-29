# Change Request <NN> — <short name>

> Template, decided with Koen on 17 September 2026. Copy it to
> `docs/change_request_<NN>_<slug>.md`. **Part A is written from the
> business, Part B from the solution.** Part A never mentions a component,
> a library or a table; Part B never introduces a new business rule. A
> reviewer must be able to read Part A on its own and agree with it before
> Part B exists. **Part A is written by the business, in its words; the
> analyst does not fill it in on the business's behalf.**
>
> Added 25 September 2026 (Koen, shaping CR-12): **B9 Rule and gatekeeper.** An
> architectural change request does not only fix something; it fixes a *way of
> doing it*. B9 names that rule and the gate that keeps future work on it.
>
> Added 29 September 2026 (Koen, shaping CR-14): **the guidance per section
> sits in a `[!NOTE]` block** — rendered blue and italic on GitHub — so a copy
> shows at a glance what is to be filled in and what is content. **When Claude
> writes a change request from this template, it deletes the note block of a
> section as soon as that section is filled in.** A note left standing means
> the section is not written yet; a finished change request has none. What
> stays in every instance is the **heading with its purpose** ("A1. Reason to
> act — the trigger"): the heading tells the reader what the section is, the
> note tells the writer how to fill it. Keep the headings verbatim.

**Project:** Web Portal "Raak Millegem"
**Status:** <shaped with Koen on …> · <on hold / assigned to vX.Y / built>
**Applies to:** <one line: which parts of the system it touches>

---

# Part A — The business

## A1. Reason to act — the trigger

> [!NOTE]
> *The trigger: the one reason this idea is put forward, in the business's*
> *own words. What the association wants, what stops it today, and why that is*
> *not acceptable. A few sentences; no solution words. Example (CR-14): every*
> *registration on the platform; for the Sint the registration and its*
> *questions had to be split, which is a step back.*

## A2. As-is process — how it works today, and where it hurts

> [!NOTE]
> *How the work is done today, by whom, with which tools and material.*
> *Measured where possible: how often, how long, how many. Name the pain per*
> *step. Two forms, both: a **process drawing** and a **step table** with the*
> *pain column.*
>
> *The drawing is a Mermaid flowchart that follows BPMN Level 1 as Bruce*
> *Silver's "Method and Style" defines it (decided with Koen, 29 September*
> *2026 — GitHub renders Mermaid and nothing else; real BPMN is for a process*
> *that will be executed, see CR-13 B4.10). The Level 1 palette, in Mermaid:*
> *one `subgraph` per actor as its lane (member, organiser, treasurer, the*
> *portal), in the same order in A2 and A3 so the difference is visible; a*
> *rectangle per activity, labelled verb + noun ("Register", "Send link");*
> *one start circle and one named end circle per outcome ("Registered",*
> *"Refused"); a diamond for an exclusive gateway with its question inside*
> *and the answers on the arrows; a dashed arrow for a message between*
> *lanes; at most fifteen activities per drawing — more becomes a subprocess*
> *in its own drawing. No intermediate events, no timers, no data objects:*
> *Level 1 stops there on purpose.*

## A3. To-be process — how it should work afterwards

> [!NOTE]
> *How the work should go afterwards: the same drawing and table as A2, the*
> *same lanes in the same order, so the difference is what the eye finds.*
> *Still no components: "the portal renders the poster", not "WeasyPrint*
> *renders the poster". A step that disappears, moves lane or turns into a*
> *choice is the change — name it under the drawing in one line each.*

## A4. Supplied material — and what it taught us

> [!NOTE]
> *What the business handed over to start from — brand guides, examples,*
> *photos, spreadsheets, briefs — with where it lives (Nextcloud path, never in*
> *the repository when it holds personal data or brand assets). What was learnt*
> *from it goes here too, as measurements: "four example posters; none has a*
> *bleed".*

## A5. Business requirements — what the board asks, with MoSCoW

> [!NOTE]
> *One table. Each requirement is a sentence a board member would say, with a*
> *MoSCoW class. Numbered, so Part B and the acceptance criteria can point at*
> *them.*

| # | Requirement | MoSCoW | Source | Comment |
|---|---|---|---|---|
| R1 | … | Must | Koen, <date> | … |

MoSCoW: **Must** (without it the change is worthless), **Should** (important,
but the change ships without it), **Could** (nice, if cheap), **Won't** (asked
and deliberately not done — recorded so it is not asked again).

## A6. Non-functional requirements — reporting, security, privacy, house style, tenants

> [!NOTE]
> *The requirements every change request is tested against, each answered*
> *explicitly at business level, "not applicable" included. How they are met*
> *belongs in Part B:*

| Concern | This change |
|---|---|
| **Reporting** — what must be countable afterwards, by whom | … |
| **Security** — who may do what; new inputs from outside; secrets | … |
| **Privacy** — personal data: what, where, who sees it, what leaves the system | … |
| **House style / UI norm** — `docs/design-system.md`; brand rules | … |
| **Multi-tenant** — what differs per unit, what is platform-wide | … |

## A7. Acceptance criteria — what the business signs off on HDEV

> [!NOTE]
> *Criteria the business signs off on, each testable by a person on HDEV*
> *without reading code, each pointing at a requirement. These are the*
> *business's unit tests; the developer's tests live in Part B.*

| # | Criterion | Requirement |
|---|---|---|
| AC1 | … | R1 |

---

# Part B — The solution

## B1. Solution outline — the solution and the decisions that shape it

> [!NOTE]
> *The solution in one paragraph, and the decisions that shape it, each with*
> *the alternatives weighed and why they lost (Europe First named where a tool*
> *or service is chosen).*

### B1.1 Functional analysis — the derived requirements

> [!NOTE]
> *The derived, finer-grained requirements the solution answers, traced to A5.*
> *This is design work by the analyst, not business input — which is why it is*
> *not in Part A.*

## B2. Architecture

### B2.1 Components — new, used, changed

> [!NOTE]
> *Which components are new, which existing ones are used, which change. One*
> *table: component · new/used/changed · role in this change.*

### B2.2 Application usage — where each business step happens

> [!NOTE]
> ***Diagram (ArchiMate "application usage" view):** the to-be process steps of*
> *A3 on the left, the screens and services that serve each step on the right.*
> *It answers: *where in the application does each business step happen?**

### B2.3 Application structure — what is built where, and what talks to what

> [!NOTE]
> ***Diagram (ArchiMate "application structure" view):** screens, modules,*
> *facades, data stores and external integrations, with the dependencies*
> *between them. It answers the developer's question: *what has to be built*
> *where, and what talks to what?**

### B2.4 Impact on the existing architecture — what is touched, and how the layer rules hold

> [!NOTE]
> *What existing modules, tables, screens and contracts are touched, and how*
> *the layer rules (`docs/code-style.md`, CR-04, the import gate) are respected.*

## B3. Cost and operations — settings, limits, running cost

> [!NOTE]
> *Operations first: settings, env vars, backups, limits, kill switch.*
> *Then external and running cost: paid tools and services (per use and per month,*
> *with the measured figure where a prototype exists), storage, and the limits*
> *that cap it. One-off cost where relevant (e.g. a licence). "None" is an*
> *answer.*

## B4. Detailed decisions — one subsection each, with the reasons

> [!NOTE]
> *The design decisions in full, one subsection each, with their reasons.*

## B5. Data model

### B5.1 Entity-relationship diagram

> [!NOTE]
> *Mermaid `erDiagram`: entities with their key columns, relationships with*
> *cardinality; soft references across schemas drawn as relationships too.*

### B5.2 Tables — schemas, columns, validation layers

> [!NOTE]
> *Sketch of schemas, tables, columns, codes; validation layers.*

## B6. Privacy and security — the mechanics behind A6

> [!NOTE]
> *How A6's privacy and security answers are implemented: what leaves the*
> *system to whom, what is sanitised, what is logged.*

## B7. Phasing — shippable phases, and what changes on the failure paths

> [!NOTE]
> *Shippable phases, each with what it delivers and its dependencies.*

Per phase, next to the "Na de merge" block, one column **failure paths that
change** (added 27 September 2026, from CR-13). A change that reorganises
behaviour — where a rule lives, who commits, what a handler does — rarely
changes what the system does on the happy path, and almost always changes
what it does when something fails: what rolls back, what is refused, what
is left half done. Name those per phase, so "no functional change" is a
claim about the happy path with the failure paths listed beside it, and an
e2e test that goes red on one of them is expected, not a surprise. "None"
is an answer.

## B8. Tests — what the build must prove

> [!NOTE]
> *What the build must prove, each test able to go red; guards proven by*
> *violation.*

## B9. Rule and gatekeeper — what this fixes for all future work

An architectural change request fixes a **way of doing things**, not just one
instance of it. This section makes that explicit, so the decision outlives the
change and the next development follows it without anyone remembering to ask.
Three parts; "no gate" is an answer, with the reason.

**A rule is fixed only when its gate runs in CI on every push** (Koen, 27
September 2026). A rule that lives in a document is a hope; a rule whose test
goes red on the next pull request is a property of the codebase. So the gate of
B9.3 is a pytest in `backend/tests/` that `backend-tests.yml` runs on every
push and PR — not a script someone remembers, not a review checklist. Where
that is impossible, B9.3 says so and names what catches it instead
(a review agent, a release step), and that is a weaker guarantee, written
down as one.

1. **The rule.** One sentence a reviewer can apply, in the form the decision
   takes from now on ("a code list is a code table in the owning domain's
   schema, a label table per language, and an `Enum` only where code branches
   on the value"). Where it ends up: `CLAUDE.md`, `docs/code-style.md` or the
   architecture document — name the place.

2. **The reach and the baseline.** Where the rule applies (the whole codebase,
   or which modules) and **how many places violate it today**, measured on the
   branch, not recalled. This change request brings that number down — say to
   what. A number that cannot be counted is an intention, not a rule (CR-04,
   *Making it checkable*).

3. **The gate.** Which test fails when a new development breaks the rule: what
   it looks at, what its message says, and the violation it was proven with
   (B8). Two shapes, chosen by the baseline:
   - **Ratchet** when the count is not yet zero: a frozen list of today's
     violations that may only shrink (the #780 pattern). Nothing new may join
     it; an entry that disappears from the code must leave the list.
   - **Hard gate** when the count is zero after this change: any violation is
     red.

   Gates come last, not first (CR-04): a gate with a growing exemption list is
   a dead rule, and a gate written too early freezes the wrong understanding.
   Where the rule cannot be checked mechanically, say so and hand it to the
   judgment layer (the `design-conformiteit-bewaker` agent, review) instead of
   pretending a grep is a gate.

   The gate is also what makes the rule cheap to follow: for a new case it
   spells out the steps ("a new code list needs a table, a label row per
   language, an `Enum` member and a label call") and fails on the one that was
   forgotten, with the name of the missing piece.

## B10. Prototype findings — what was measured before the build

> [!NOTE]
> *What was learnt from prototypes before the build (measurements, refusals,*
> *things that did not work).*

## B11. Decisions log — dated answers and open proposals

> [!NOTE]
> *Dated answers from Koen and open proposals awaiting an answer.*

## Q&A log — asked once, answered here

> [!NOTE]
> *Questions asked during shaping, review and build, dated, with who asked and*
> *the answer — so nothing is asked twice and open questions are visible.*

| # | Date | Question (who) | Answer |
|---|---|---|---|
| Q1 | … | … | … / *open* |

## Non-goals — deliberately outside this change

> [!NOTE]
> *What is deliberately outside this change.*

## Relationship to existing work — issues and change requests

> [!NOTE]
> *Issues and CRs this builds on or hands off to.*
