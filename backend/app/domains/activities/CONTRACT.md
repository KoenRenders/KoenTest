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

`router.py` — de volledige activiteiten-API onder `/api/v1/activities`
(22 routes; dead-endpoint-sweep uitgevoerd bij de verhuis: alle routes zijn
in gebruik door de frontend).

## Data

Schema `activities` (migratie 081): activiteiten-, registratie- en
history-tabellen. Soft-refs (§8): `registrations.person_id` → mdm (078),
`registration_type(_code)` → public codes (validatie in de Pydantic-schema's),
en `media_assets.activity_id/component_id` (public → activities; ORM-relaties
via expliciete `primaryjoin`, viewonly).

## Betalingen

Registratie-betalingen lopen via het payment-component
(`payable_type="registration"`); saldo/afboeking via `payment.api`.
