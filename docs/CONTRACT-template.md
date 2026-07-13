# CONTRACT — <component>

> Kopieer dit sjabloon naar `app/domains/<component>/CONTRACT.md` (#396, §12).
> Het contract = facade-signaturen + DTO's + events. Alles daaronder is intern
> en mag vrij wijzigen; het contract wijzigt enkel via de deprecatie-cyclus (§9).

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
