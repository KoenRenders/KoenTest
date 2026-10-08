# activities — componentcontract (fase 4a, #402)

**Doel.** Activiteiten, onderdelen (componenten), producten en registraties
(3-level, alle `reg_form_type`s incl. `pay_on_site`), plus de exports.

## Facade (`api.py`) — de enige toegangsdeur voor andere componenten

- **Modellen als type**: `Activity`, `ActivityDate`, `ActivitySubRegistration`,
  `ActivityProduct`, `Registration`, `RegistrationItem` + de history-klassen.
- **`compute_registration_total(registration)`** — dé totaalberekening
  (§19.3): uitsluitend server-side, één plek. Ledenprijs via de
  membership-facade (`has_valid_membership`).
- `build_component_export_ods` — deelnemerslijst + betaalblad.

## Router

`router.py` — what is left of the activities API under `/api/v1/activities`.
CR-13 phase 4b (#1251) prunes every JSON route without a caller: the screens
are server-rendered and ask the facade. Gone so far: registering, the list,
updating and deleting an activity, the registrations of an activity, the
export, changing an order line, the registration's remarks, deleting a
registration and the public participant list. The functions the facade calls
(`activities_for`, `get_activity_detail`, `get_public_registrations`,
`register_for_activity`, `create_registration`) stay in this file until
phase 4c moves them.

## Data

Schema `activities` (migratie 081): activiteiten-, registratie- en
history-tabellen. Soft-refs (§8): `registrations.person_id` → mdm (078),
`registration_type(_code)` → public codes (validatie in de Pydantic-schema's),
en `media_assets.activity_id/component_id` (public → activities; ORM-relaties
via expliciete `primaryjoin`, viewonly).

## Betalingen

Registratie-betalingen lopen via het payment-component
(`payable_type="registration"`); saldo/afboeking via `payment.api`.

## Events

- Publishes `OrderChanged(registration_id, total_due, actor)`
  (`app.kernel.contracts.activities`, CR-13 phase 1) after every change to a
  registration's order lines, the deletion of the registration included, before
  its one commit. `payment` subscribes and reconciles; activities no longer calls
  `payment.api` to do it. The service refuses to publish when nothing subscribes.
