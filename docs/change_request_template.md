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

**Project:** Web Portal "Raak Millegem"
**Status:** <shaped with Koen on …> · <on hold / assigned to vX.Y / built>
**Applies to:** <one line: which parts of the system it touches>

---

# Part A — The business

## A1. Reason to act

Written by the business, or left open when there is no single trigger.
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

| # | Requirement | MoSCoW | Source | Comment |
|---|---|---|---|---|
| R1 | … | Must | Koen, <date> | … |

MoSCoW: **Must** (without it the change is worthless), **Should** (important,
but the change ships without it), **Could** (nice, if cheap), **Won't** (asked
and deliberately not done — recorded so it is not asked again).

## A6. Non-functional requirements

The requirements every change request is tested against, each answered
explicitly at business level, "not applicable" included. How they are met
belongs in Part B:

| Concern | This change |
|---|---|
| **Reporting** — what must be countable afterwards, by whom | … |
| **Security** — who may do what; new inputs from outside; secrets | … |
| **Privacy** — personal data: what, where, who sees it, what leaves the system | … |
| **House style / UI norm** — `docs/design-system.md`; brand rules | … |
| **Multi-tenant** — what differs per unit, what is platform-wide | … |

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

### B1.1 Functional analysis

The derived, finer-grained requirements the solution answers, traced to A5.
This is design work by the analyst, not business input — which is why it is
not in Part A.

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

## B3. Cost and operations

Operations first: settings, env vars, backups, limits, kill switch.
Then external and running cost: paid tools and services (per use and per month,
with the measured figure where a prototype exists), storage, and the limits
that cap it. One-off cost where relevant (e.g. a licence). "None" is an
answer.

## B4. Detailed decisions

The design decisions in full, one subsection each, with their reasons.

## B5. Data model

### B5.1 Entity-relationship diagram

Mermaid `erDiagram`: entities with their key columns, relationships with
cardinality; soft references across schemas drawn as relationships too.

### B5.2 Tables

Sketch of schemas, tables, columns, codes; validation layers.

## B6. Privacy and security — the mechanics

How A6's privacy and security answers are implemented: what leaves the
system to whom, what is sanitised, what is logged.

## B7. Phasing

Shippable phases, each with what it delivers and its dependencies.

## B8. Tests

What the build must prove, each test able to go red; guards proven by
violation.

## B9. Rule and gatekeeper

An architectural change request fixes a **way of doing things**, not just one
instance of it. This section makes that explicit, so the decision outlives the
change and the next development follows it without anyone remembering to ask.
Three parts; "no gate" is an answer, with the reason.

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

## B10. Prototype findings

What was learnt from prototypes before the build (measurements, refusals,
things that did not work).

## B11. Decisions log

Dated answers from Koen and open proposals awaiting an answer.

## Q&A log

Questions asked during shaping, review and build, dated, with who asked and
the answer — so nothing is asked twice and open questions are visible.

| # | Date | Question (who) | Answer |
|---|---|---|---|
| Q1 | … | … | … / *open* |

## Non-goals

What is deliberately outside this change.

## Relationship to existing work

Issues and CRs this builds on or hands off to.
