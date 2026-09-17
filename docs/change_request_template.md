# Change Request <NN> — <short name>

> Template, decided with Koen on 17 September 2026. Copy it to
> `docs/change_request_<NN>_<slug>.md`. **Part A is written from the
> business, Part B from the solution.** Part A never mentions a component,
> a library or a table; Part B never introduces a new business rule. A
> reviewer must be able to read Part A on its own and agree with it before
> Part B exists.

**Project:** Web Portal "Raak Millegem"
**Status:** <shaped with Koen on …> · <on hold / assigned to vX.Y / built>
**Applies to:** <one line: which parts of the system it touches>

---

# Part A — The business

## A1. Reason to act

Why this change, and **why now**. What goes wrong today, who feels it, what it
costs (time, money, mistakes, missed members), and what changed so that the
moment is now. One or two paragraphs; no solution words.

## A2. As-is process

How the work is done today, step by step, by whom, with which tools and
material. Measured where possible: how often, how long, how many. Name the
pain per step.

## A3. To-be process

How the work should go afterwards, step by step. Same actors as A2 where
possible, so the difference is visible. Still no components: "the portal
renders the poster", not "WeasyPrint renders the poster".

## A4. Supplied material

What the business handed over to start from — brand guides, examples,
photos, spreadsheets, briefs — with where it lives (Nextcloud path, never in
the repository when it holds personal data or brand assets). What was learnt
from it goes here too, as measurements: "four example posters; none has a
bleed".

## A5. Business requirements

One table. Each requirement is a sentence a board member would say, with a
MoSCoW class. Numbered, so Part B and the acceptance criteria can point at
them.

| # | Requirement | MoSCoW | Source |
|---|---|---|---|
| R1 | … | Must | Koen, <date> |

MoSCoW: **Must** (without it the change is worthless), **Should** (important,
but the change ships without it), **Could** (nice, if cheap), **Won't** (asked
and deliberately not done — recorded so it is not asked again).

## A6. Recurring requirements

The requirements every change request is tested against, each answered
explicitly, "not applicable" included:

| Concern | This change |
|---|---|
| **Reporting** — what must be countable afterwards, by whom | … |
| **Security** — who may do what; new inputs from outside; secrets | … |
| **Privacy** — personal data: what, where, who sees it, what leaves the system | … |
| **House style / UI norm** — `docs/design-system.md`; brand rules | … |
| **Multi-tenant** — what differs per unit, what is platform-wide | … |
| **Operations** — settings, env vars, backups, cost limits, kill switch | … |

## A7. Acceptance criteria

Criteria the business signs off on, each testable by a person on HDEV
without reading code, each pointing at a requirement. These are the
business's unit tests; the developer's tests live in Part B.

| # | Criterion | Requirement |
|---|---|---|
| AC1 | … | R1 |

---

# Part B — The solution

## B1. Solution outline

The solution in one paragraph, and the decisions that shape it, each with
the alternatives weighed and why they lost (Europe First named where a tool
or service is chosen).

## B2. Architecture

### B2.1 Components

Which components are new, which existing ones are used, which change. One
table: component · new/used/changed · role in this change.

### B2.2 Application usage

**Diagram (ArchiMate "application usage" view):** the to-be process steps of
A3 on the left, the screens and services that serve each step on the right.
It answers: *where in the application does each business step happen?*

### B2.3 Application structure

**Diagram (ArchiMate "application structure" view):** screens, modules,
facades, data stores and external integrations, with the dependencies
between them. It answers the developer's question: *what has to be built
where, and what talks to what?*

### B2.4 Impact on the existing architecture

What existing modules, tables, screens and contracts are touched, and how
the layer rules (`docs/code-style.md`, CR-04, the import gate) are respected.

## B3. Cost

External and running cost: paid tools and services (per use and per month,
with the measured figure where a prototype exists), storage, and the limits
that cap it. One-off cost where relevant (e.g. a licence). "None" is an
answer.

## B4. Detailed decisions

The design decisions in full, one subsection each, with their reasons.

## B5. Data model

Sketch of schemas, tables, columns, codes; validation layers.

## B6. Privacy and security — the mechanics

How A6's privacy and security answers are implemented: what leaves the
system to whom, what is sanitised, what is logged.

## B7. Phasing

Shippable phases, each with what it delivers and its dependencies.

## B8. Tests

What the build must prove, each test able to go red; guards proven by
violation.

## B9. Prototype findings

What was learnt from prototypes before the build (measurements, refusals,
things that did not work).

## B10. Decisions log

Dated answers from Koen and open proposals awaiting an answer.

## Non-goals

What is deliberately outside this change.

## Relationship to existing work

Issues and CRs this builds on or hands off to.
