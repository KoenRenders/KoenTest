# CONTRACT — <component>

> Copy this template to `app/domains/<component>/CONTRACT.md` (#396, §12).
> The contract is the facade's signatures, its DTOs and its events. Everything
> under it is internal and may change freely; the contract changes only through
> the deprecation cycle (§9).
>
> Nine headings, in this order, in English (#1954; Koen, 13 October 2026, to
> the choice between nine English headings in one go and five Dutch plus four
> English: "3a"). They are what the architecture document reads per module —
> its part B *is* this file — and the module-shape gate requires them. Where a
> heading has nothing to say: "none", with one reason — never empty.
>
> A domain with a JSON route also keeps its heading `## Callers`, after
> *Publishes*: the rules gate reads it (every `/api/v1` route names its
> caller). It is not one of the nine; a domain without a JSON route has none.

## Purpose and process
One paragraph: what the module is for, which business process of the
architecture document (part A2) it carries, and its aggregates.

## Publishes
- **Facade** (`api.py`): `function(args) -> DTO` — one line per function, with
  the invariant it guarantees.
- **Events**: `<Aggregate><Verb>` (e.g. `SubmissionCreated`) — the payload's
  fields and the delivery (synchronous, in the transaction; step 1 of the
  event ladder).

## Consumes
- Facades: `mdm.api.resolve`, …
- Events: `PaymentSettled`, …

## Owns
- **Schema**: `<component>` (all its own tables; no foreign key across
  schemas).
- **Reference codes**: the code tables and values this component manages.
- **Jobs**: the kernel jobs it registers (`<component>.<name>`).

## Screens
- The UI routes (`ui.py`, `admin_ui.py`) and the navigation items this
  component registers.

## Deprecations
| Since | What | Replaced by | Remove at |
|---|---|---|---|

## Standards
The standards this module carries out (part D of the architecture document),
one row each. A deviation names the reason.

| Standard | Element | Our name | Follows / deviates, with the reason |
|---|---|---|---|

## Rules and gates
- **Rules whose home is this module** — one line each, with the address
  (`@validates`, `check()` on an aggregate, the service, a constraint;
  `docs/code-style.md`, *A rule has one home*).
- **Gates in this module's own `tests/`** — the file and what it refuses.

## Evolutions
The rows of part E of the architecture document that touch this module, by
id, with one line each: what is planned, and its status.
