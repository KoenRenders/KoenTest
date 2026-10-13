# CONTRACT — <component>

> Kopieer dit sjabloon naar `app/domains/<component>/CONTRACT.md` (#396, §12).
> Het contract = facade-signaturen + DTO's + events. Alles daaronder is intern
> en mag vrij wijzigen; het contract wijzigt enkel via de deprecatie-cyclus (§9).

> Four headings are in English (#1954, 13 October 2026): they are what the
> architecture document reads per module — its part B *is* this file. The five
> Dutch headings below are older and stay as they are until the template is
> revised in one go. Nine headings in all; the module-shape gate requires them.
> Where a heading has nothing to say: "none", with one reason — never empty.

## Purpose and process
One paragraph: what the module is for, which business process of the
architecture document (part A2) it carries, and its aggregates.

## Publiceert
- **Facade** (`api.py`): `functie(args) -> DTO` — één regel per functie, met de
  invariant die ze garandeert.
- **Events**: `<Aggregate><Verb>` (bv. `SubmissionCreated`) — payload-velden +
  bezorging (synchroon/in-transactie, event-ladder trede 1).

## Consumeert
- Facades: `mdm.api.resolve`, …
- Events: `PaymentSettled`, …

## Bezit
- **Schema**: `<component>` (alle eigen tabellen; geen cross-schema FK's).
- **Referentiecodes**: welke code-tabellen/waarden dit component beheert.
- **Jobs**: geregistreerde kernel-jobs (`<component>.<naam>`).

## Deprecaties
| Sinds | Wat | Vervangen door | Verwijderen bij |
|---|---|---|---|

## Schermen
- UI-routes (`ui.py`) + nav-items die dit component registreert.

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
