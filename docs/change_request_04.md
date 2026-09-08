# Change Request 04 — Object-Oriented Domain Model

**Project:** Web Portal "Raak Millegem"
**Status:** Proposal / discussion — not scheduled. Phased, each phase independently shippable and revertible.
**Apply to:** `backend/app/` (models, services, domains) and, as a parallel track, `frontend/src/`.

---

## Goal

Move from the current *anemic model + functional services* style toward a richer
object-oriented domain model, with **responsibilities isolated in well-bounded
objects** across the three layers (DB / backend / frontend). The driver is
clarity and correctness — *make illegal states unrepresentable* and *talk to a
role, not a concrete type* — applied **surgically where it removes a real bug
class or duplication**, not as a blanket rewrite.

This CR is explicit about where OO pays off here **and where to stop** (see
*Non-goals*), so the codebase does not drift into over-engineering.

---

## Guiding principles

1. **Separation of responsibilities into isolated objects.** Each object owns one
   thing: a persistence row, a value with its rules, a transition, a query.
2. **Make illegal states unrepresentable.** Invariants enforced at construction
   (value objects) and on transitions (state machines), not in scattered checks.
3. **Talk to roles, not concrete types.** Replace `if type == …` branching with
   polymorphism where the branching genuinely recurs.
4. **Respect the existing layering** (`CLAUDE.md`: *form → router; meaning →
   service; integrity-at-rest → DB*). OO enriches the *meaning* layer; it does not
   move query logic onto ORM entities, and it does not weaken DB constraints.
5. **Consistency over purity.** A half-migrated paradigm is worse than either pure
   style; each phase leaves the codebase coherent.

---

## Current state (honest baseline)

- **ORM models** = data mapping only (columns + relationships) with a few
  read-only computed properties (`Activity.poster_asset_url`, …). Effectively
  anemic.
- **Service layer** = module-level functions hold the behaviour
  (`services/membership.py`, `services/registration_totals.py`,
  `domains/payment_status/service.py`, …).
- **OO already present where it earns its keep:** `BaseProvider(ABC)` →
  `MollieProvider` (strategy/adapter), `SoftDeleteMixin` (mixin), custom
  exceptions, Pydantic schema inheritance.
- **Frontend** already separates concerns: `lib/money.ts`, `lib/types.ts`,
  `lib/errors.ts`, `lib/api.ts` (boundary) vs. presentational components.

The proposal extends an instinct that is already in the code — it does not import
a foreign paradigm.

---

## Where a rule goes (the placement rule)

Added 8 September 2026, after a validation round that produced seventeen findings
in one day. Four of them — #720, #727, #733, #681 — were the same defect: a rule
enforced on one entrance and not on another. The public form demanded a mobile
number; the JSON API accepted a registration without one; the admin screen let you
erase it. Not one of those was an oversight. The rule simply had no home, so it
lived in whichever function happened to run.

**A rule belongs where it can see what it needs to judge — and nowhere else.**
That single question decides the form:

| The rule looks at… | Where it goes | Why |
|---|---|---|
| **one field** ("a mobile number is not empty") | an **attribute validator** (SQLAlchemy `@validates`) | fires on every assignment, including on an object loaded from the database and then modified — which is exactly where #733 went wrong |
| **several fields of the same object** ("team name required *if* the component asks for one") | a **method on the aggregate** | it needs siblings; no single attribute can answer it |
| **other objects or the database** ("is this component still not full?") | a **function in the service layer** | a model that needs a session drags persistence into the domain — this is where OO rewrites usually run aground |
| **integrity at rest** (no negative price, uniqueness) | a **database constraint** | the last net: it holds even when two requests race or a script writes directly |

The layers are not alternatives. A critical invariant earns a place in more than
one: a validator for a readable message, a constraint for the guarantee. That is
defence in depth, not duplication — the same reasoning as the three validation
layers in `CLAUDE.md`.

**What this rule replaces:** the habit of putting every check in the route that
happens to receive the request. A check in a route protects that route. Every other
door stays open, and nobody notices until someone walks through one.

### Making it checkable

An end state you cannot count is an intention. Five numbers make this one
measurable; they were taken on 8 September 2026 and belong in every release issue:

| | then | target |
|---|---|---|
| attribute validators in use | **0** | every field-level rule |
| database check constraints | **1** | the critical invariants (#94) |
| mutating UI routes that confirm success | **2 of 91** | all |
| orderings without a unique tiebreaker | **16** (rough count) | 0 |
| `required=True` promises in templates | **88 in 25 templates** | each with a server-side counterpart |

That last row is the important one, and today it is *unmeasurable*: nobody knows
how many of those 88 promises the server actually keeps. **The first deliverable is
therefore a count, not a fix** — a report that lists, per aggregate, which entrances
exist and which of them pass through validation. Without that number, progress is a
feeling.

### Gates come last, not first

Close a rule with a gate only once the count is near its target. A gate introduced
while eighty-five routes violate it needs an exemption list, and an exemption list
is where a rule goes to die.

There is a sharper reason, learned the same day. The gate from #626 fixed that the
three social icons carry the same CSS class. Correct at the time — they had silently
shrunk. But it encoded *"equal boxes"* while the goal was *"equally legible"*, and
when #744 showed the icons were still optically unequal, that gate stood in the way
of the right fix. A gate freezes the understanding you had when you wrote it. Freeze
it too early and it protects the wrong thing.

---

## Three building blocks

### A. Value Objects (lowest risk, highest clarity)

Small, immutable, always-valid objects that replace primitives. They map onto the
**existing columns** — no schema change required.

| Value Object | Replaces (primitive obsession) | Owns |
|---|---|---|
| `Money` | raw `Decimal`/`Numeric`, `Decimal(str(...))` ceremony | rounding, currency, formatting, negative-refund rule |
| `GestructureerdeMededeling` (OGM) | raw `String` `structured_communication` | mod-97 checksum, parse + validate (currently only *generate* exists), `+++…+++` formatting |
| `Geldigheidsperiode` | loose `valid_from` / `valid_to` pair | `.contains(date)`, ordering, the date-range loop now in `membership.py` |
| `Emailadres` / `Leeftijdscategorie` (optional) | raw strings / JSON config | format validation, category semantics |

A proof-of-concept VO for the OGM already exists as a throwaway spike and passes a
full unit suite with **zero DB fixtures** — illustrating the testability win.

### B. Rich entities (behaviour onto the objects that own it)

Move cohesive, *already-loaded-relationship* behaviour from free functions onto the
entity. Logic that needs a **DB query stays in a service/repository** (hard
boundary).

| Concept | Today (free function) | Proposed (method on the object) |
|---|---|---|
| `Person` | `membership.has_valid_membership(person, date)` | `person.has_valid_membership(date)`, `person.age(on=…)`, `person.primary_contact("mobile")` |
| `Household` (`Member`) | membership loop inside `valid_membership_until` | `household.is_member_in(year)`, `household.active_membership(on=…)`, `household.hoofdlid` |
| `Registration` | `registration_totals.compute_registration_total(...)`, `registration_balance(...)` | `registration.total()`, `registration.lines()`, `registration.balance()`, `registration.is_settled()` |
| `Activity` | scattered `reg_form_type` branching | `activity.is_full()`, `activity.status()` (Open/Vol/Wachtlijst), `activity.is_archived()` |
| `PaymentRecord` | `payment_status/service.py` functions | `record.mark_paid()`, `record.cancel()` (guarded transitions) — see C |

**Ubiquitous-language fix:** the class `Member` actually models a *household/gezin*,
while `Person` is the real member. Renaming `Member → Household` aligns the code
with the domain vocabulary. High clarity, but the largest mechanical change
(Alembic table rename + references) — deliberately the **last** phase.

### C. Polymorphic strategies (replace recurring branching)

| Branching today | Proposed family |
|---|---|
| `reg_form_type` (`INDIVIDUAL` / `TEAM` / `GROUP` / `PAID_PER_PERSON` / `PAID_PRODUCTS` / `AGE_CATEGORY`) drives `if/elif` in routers + frontend | a `RegistrationForm` strategy per type with a shared interface (`extra_fields()`, `compute_total()`, `validate()`). Adding a type = adding a class, callers unchanged. |
| `PaymentRecord.type` (`charge` / `refund`) + self-FK flag | `Charge` / `Refund` as polymorphic subtypes (SQLAlchemy single-table inheritance): `refund.amount` always negative, `charge.refundable_balance()` |
| payment provider (already done) | `BaseProvider` → `MollieProvider` (template for the above) |

This is the same pattern the chatbot work (#205) plans for the swappable LLM layer
— one interface, many implementations — so it reinforces a house pattern.

---

## Layered isolation of responsibilities (DB / backend / frontend)

The point the requester emphasised: **each responsibility in its own isolated
object, per layer.**

**Backend — four roles, no overlap:**

1. **Persistence (DB-mapping):** ORM models map rows and own only read-only
   derived properties. No business rules, no queries. Integrity-at-rest stays in
   DB constraints (per `CLAUDE.md`).
2. **Domain:** entities (rich behaviour over loaded data) + value objects
   (invariant-carrying values) + pure domain services (rules spanning objects).
   This is where "meaning" lives.
3. **Application/orchestration:** transaction boundaries + **repositories** that
   own all queries (`net_paid`, `reconcile`, `get_records_for`). The bridge between
   "needs the session" and "is pure domain logic".
4. **HTTP (router):** request/response only. Pydantic schemas = *form* validation
   and DTOs at the edge; they do not carry domain behaviour.

**The hard boundary:** an entity method may use already-loaded relationships
(membership check, total) but must **never** open a query. Query-shaped logic
(`net_paid`, `reconcile`, balance over a set of payments) belongs to a
**repository/aggregate** (`Payable` = registration|membership + its payment
records), not on the entity. This is the single most important rule to keep the
OO model from fighting the ORM.

**Frontend — mirror the same split (parallel track):**

- **Value/domain helpers** (`lib/money.ts` exists; add `lib/ogm.ts`,
  `lib/membership.ts`) own formatting/validation rules — never duplicated inside
  components.
- **Boundary** (`lib/api.ts`) owns all backend I/O; components never `fetch`.
- **Presentation** (components) own rendering only.
- **Form-type polymorphism** mirrored: a strategy/registry per `reg_form_type`
  instead of branching inside `RegistrationForm.tsx`.

---

## Phasing (each phase shippable, tested, revertible)

| Phase | Scope | Risk | Schema change |
|---|---|---|---|
| **0** | Value objects: `Money`, `GestructureerdeMededeling`, `Geldigheidsperiode`. Wrap existing columns. | Low | None |
| **1** | Rich read-behaviour on `Person` / `Household` / `Registration` by wrapping today's service functions (delegate first, then move). | Low | None |
| **2** | `PaymentRecord` as a guarded state machine; `Charge`/`Refund` polymorphism. | Medium | Possibly (`type` → STI discriminator) |
| **3** | `Activity` `reg_form_type` strategy family (backend + `RegistrationForm.tsx`). | Medium | None |
| **4** | Ubiquitous-language rename `Member → Household` (+ Alembic table rename). | High (mechanical) | Yes (rename) |
| **FE** | Frontend mirror (`lib/ogm.ts`, form-type strategy), runs parallel to 0/3. | Low–Med | None |

Recommended start: **Phase 0**, because the value objects are independently useful
(the OGM `parse/validate` is missing functionality today, not just a refactor),
carry no schema risk, and are the clearest OO teaching surface.

---

## Testing strategy

- Value objects, strategies and the state machine are **pure unit tests, no DB
  fixtures** — fast and exhaustive (boundary checksums, illegal transitions,
  rounding edges).
- Entity methods that wrap former service functions inherit the existing
  service-level pytests; add characterization tests before moving logic.
- Follow the repo convention: value-creating pytests on the invariants that matter
  (money, authorization, data links), CI green on the branch before merge.

---

## Non-goals (where OO does **not** earn its place here)

- **No full DDD machinery:** no aggregate roots-as-ceremony, no domain events / event
  sourcing, no CQRS. The data volume (hundreds of members) does not justify it.
- **No query logic on entities.** Repositories/services keep the session.
- **No blanket "everything becomes a class".** Plain module functions remain correct
  and idiomatic for straightforward CRUD/mapping.
- **No big-bang rewrite.** Mixed-paradigm-in-flight is avoided by keeping each phase
  coherent and revertible.
- **No weakening of DB constraints** in favour of "the object guarantees it" — defence
  in depth is kept (VO *and* `CHECK`/`NOT NULL`).

---

## Risks & rollout

- **ORM friction** (mutable mapped objects vs. immutable VOs): mitigated by mapping
  VOs over columns via composites/adapters and keeping queries in repositories.
- **Rename blast radius** (Phase 4): isolate to its own release; mechanical but wide.
  Optional — the value is clarity, not behaviour.
- **Paradigm consistency:** enforce the layer rules in review; a `domains/<x>/`
  package per bounded concept keeps responsibilities visibly isolated.
- **Process:** create a release-tracking issue listing the phase issues; develop each
  phase in its own feature-branch worktree with CI on the branch; merge to master per
  the standard release flow.

---

## Relationship to existing work

- **Reinforces** the `BaseProvider` strategy pattern and the planned swappable LLM
  layer (#205).
- **Independent of** the ML/predictions track (#171) — different initiative.
- **Touches** payments (`domains/payment_*`), registrations, membership — coordinate
  phase ordering with any in-flight releases.
