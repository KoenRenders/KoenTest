# activities — componentcontract (fase 4a, #402)

## Purpose and process

**Doel.** Activiteiten, onderdelen (componenten), producten en registraties
(3-level, alle `reg_form_type`s incl. `pay_on_site`), plus de exports.

*Process (architecture document, A2.2 — an activity: registering and paying).* The organiser's activity with its components and products, and the registration a visitor, a member or the board places on it. Aggregate: `Registration` (with its items), which carries its own `check()`; an `Activity` with its dates, components, products and organisers is saved as one fiche.

## Publishes

### Facade (`api.py`) — de enige toegangsdeur voor andere componenten

- **Modellen als type**: `Activity`, `ActivityDate`, `ActivitySubRegistration`,
  `ActivityProduct`, `Registration`, `RegistrationItem` + de history-klassen.
- **`compute_registration_total(registration)`** — dé totaalberekening
  (§19.3): uitsluitend server-side, één plek. Ledenprijs via de
  membership-facade (`has_valid_membership`).
- `build_component_export_ods` — deelnemerslijst + betaalblad.

### Router

The activities have no JSON API any more. CR-13 phase 4b (#1251) pruned every
route under `/api/v1/activities` — none had a caller: the screens are
server-rendered and ask the facade — and with the last routes the service
functions only they called (creating an activity, and the single date,
component, product and order-line doors; the fiche save and
`set_order_quantities` are what the screens use). `router.py` is no router:
it is not included in `main.py`. The functions the facade calls
(`activities_for`, `get_activity_detail`, `get_public_registrations`,
`register_for_activity`, `create_registration`) stay in this file until
phase 4c moves them.

### Events

- Publishes `OrderChanged(registration_id, total_due, actor)`
  (`app.kernel.contracts.activities`, CR-13 phase 1) after every change to a
  registration's order lines, the deletion of the registration included, before
  its one commit. `payment` subscribes and reconciles; activities no longer calls
  `payment.api` to do it. The service refuses to publish when nothing subscribes.

*Counted in the code on 13 October 2026:* the facade exports 99 names (71 functions, 22 classes, 6 values); events it owns (`kernel/contracts/`): `ActivityCopied`, `AnswerLinkSent`, `OrderChanged`, `RegistrationConfirmed`; ports it offers: none.

## Consumes

### Betalingen

Registratie-betalingen lopen via het payment-component
(`payable_type="registration"`); saldo/afboeking via `payment.api`.

*Counted in the code on 13 October 2026:* imports the facades of auth, chatbot, designstudio, forms, mdm, media, membership, payment; subscribes to no event; calls `CopyForm`, `SubmitAttached`, `UpdateAttached` (forms), `StoreFile`, `RemoveFileOf` (media).

## Owns

### Data

Schema `activities` (migratie 081): activiteiten-, registratie- en
history-tabellen. Soft-refs (§8): `registrations.person_id` → mdm (078),
`registration_type(_code)` → public codes (validatie in de Pydantic-schema's),
en `media_assets.activity_id/component_id` (public → activities; ORM-relaties
via expliciete `primaryjoin`, viewonly).

*Counted in the code on 13 October 2026:* schema `activities`, 21 tables (13 data, 8 code and label), 13 of them with `tenant_id`; status columns: `activities.status` (code list `activity_status`: draft, published); jobs: none.

## Screens

`ui.py`: 10 routes under `/activiteiten`, `/archief` and `/inschrijving/{token}`; `admin_ui.py`: 32 routes under `/admin/activiteiten` and `/admin/inschrijvingen`.

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

| Standard | Element | Our name | Follows / deviates, with the reason |
|---|---|---|---|
| OpenDocument | Spreadsheet (ODS), cells typed | the participant list and the payment sheet (`export.py`, through `kernel/ods.py`) | follows (#200) |
| UBL 2.1 | `cac:BuyerCustomerParty` | a guest registration carries name, e-mail and mobile on the record | deviates: no party for a guest, "not now"; the party model decides it (→ E28) |

## Rules and gates

- **Rules whose home is this module** — `Registration`: `@validates` on `contact_name` and on `contact_email`, and `check()` on the aggregate; 10 `CheckConstraint`s in `models.py`. `compute_registration_total` is the one total (the facade above).
- **Gates in this module's own `tests/`** — `test_reporting_schema_gate.py`: refuses a `reporting` view without `tenant_id` or without a comment saying what it excludes. It stands here because its imports are this domain's (`test_tests_placement_gate.py`).

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E20** — the OO foundation (CR-13): built in v2.8.0 and v2.16.0; one follow-up open, the registration history through a counter or an event (#1502), not planned.
- **E21** — the command port (CR-16): the three commands from activities into forms; on hold, re-measured before planning.
- **E26** — the checkout in two steps (CR-31): a registration stands with an open charge when the provider does not answer; planned, on no release.
- **E28** — the party model: decides the buyer for a guest registration; parked.
- **E34** — parked on v2.19: #1882 (the search term of the activities list in the registrations tab).
