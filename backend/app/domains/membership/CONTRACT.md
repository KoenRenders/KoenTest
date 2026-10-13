# membership — componentcontract (fase 4a, #402)

## Purpose and process

**Doel.** Lidmaatschappen: jaarrecords per gezin, geldigheidsregel
("mag deze persoon de ledenprijs?", #111) en het hernieuwingsvenster.

*Process (A2.1 — membership: joining, changing, leaving, for the yearly membership and its renewal).* Aggregate: `Membership`, which carries its own `check()`; its history is `MembershipHistory`.

## Publishes

### Facade (`api.py`) — de enige toegangsdeur voor andere componenten

- `has_valid_membership(person, ref_date=None)` / `valid_membership_until(...)`
  — dé geldigheidsregel (actief + binnen `[valid_from, valid_to]`).
- `is_member(db, email)` — de vraag van andere componenten (activities, §5.4):
  lost e-mail → Person op via het auth-component en past de regel toe.
- `renewal_open(today=None)` / `renewal_available(valid_until, today=None)` —
  het hernieuwingsvenster (§19.3: één plek; `MEMBERSHIP_RENEWAL_START_MD`).
- Modellen als type: `Membership`, `MembershipHistory`. `Membership.valid_on(day)`
  is the rule itself since CR-13 phase 3 (#1250), and `Membership.check()` refuses
  a period that ends before it begins, on every flush.
- `portal_member(request, db)` and `family_portal_page(request, db, person)` — the
  family portal's logged-in member and its page, for the doors of `mdm` that change
  a person of the household (CR-13 phase 3). The portal is this component's screen;
  the persons are `mdm`'s data.

### Events

- Subscribes to `PaymentReceived` (CR-13 phase 2): `handlers.activate_membership_on_payment`
  activates a membership once its payment covers it — idempotently, a repeated
  event activates once (#113, #720). Until phase 2 the payment component wrote
  this itself; the owner writes its rows now (`service.activate_after_payment`).
- Publishes `MembershipRenewalPlaced` (#1903, `kernel/contracts/membership.py`): a
  renewal was placed, by the household or by the board for it. `mail` subscribes and
  queues the confirmation to the main member's confirmed address; without such an
  address nothing is published.
- Publishes `MembershipDeleted` (CR-13 phase 4c, `kernel/contracts/membership.py`):
  the board deleted a membership, on its own or with its household. `payment`
  subscribes and lets the money follow (#619). Not optional: membership refuses
  to publish when nothing subscribes.

*Counted in the code on 13 October 2026:* the facade exports 39 names (33 functions, 6 classes, 0 values); events it owns (`kernel/contracts/`): `FamilyRegistered`, `MembershipDeleted`, `MembershipRenewalPlaced`; ports it offers: none.

## Consumes

*Counted in the code on 13 October 2026:* imports the facades of auth, mdm, payment; subscribes to `HouseholdDeleted`, `MembershipReported`, `PaymentReceived`; calls `CreateHousehold` (mdm).

## Owns

### Data

Schema `membership` (migratie 080): `memberships`, `membership_history`.
`member_id` is een soft-ref naar `mdm.members` (§6/§8, FK gedropt in 078);
de ORM-relatie via backref blijft voor intern gemak.

*Counted in the code on 13 October 2026:* schema `membership`, 2 tables (2 data, 0 code and label), 2 of them with `tenant_id`; status columns: none; jobs: none.

## Screens

`ui.py`: 6 routes under `/lid-worden` and `/leden/gezin` (the family portal).

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

None: no row of part D of the architecture document names this module, and its `models.py` names no standard.

## Rules and gates

- **Rules whose home is this module** — `Membership.check()` (a period that ends before it begins is refused) and `Membership.valid_on(day)`, the validity rule; 1 `CheckConstraint` in `models.py`.
- **Gates in this module's own `tests/`** — none among its 5 test files.

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E26** — the checkout in two steps (CR-31): the renewal as one of the three doors that open a charge; planned, on no release.
- **E30** — workbench tasks for the member administration: open.
