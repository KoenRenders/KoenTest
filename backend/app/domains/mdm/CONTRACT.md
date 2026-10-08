# mdm — componentcontract (fase 2, #400)

**Doel.** Masterdata: identiteit van personen en gezinnen, adressen,
contactgegevens, postcodes, externe nummers, organisaties (ACCOUNT/UNIT) en de
bijbehorende codetabellen — plus merge/survivorship.

## Facade (`api.py`) — de enige toegangsdeur voor andere componenten

- **Modellen**: `Person`, `Member`, `MemberPerson`, `Address`, `ContactDetail`,
  `PostalCode`, `ExternalNumber`, `Organization`, `GenderCode`,
  `ContactTypeCode`, `RelationTypeCode` + de MDM-history-klassen.
- **Merge/survivorship** (`service.py`, §6): `merge_persons` (idempotent,
  nooit hard verwijderen, keten platgeslagen), `resolve` (O(1) naar de
  overlever), `unmerge_person` (history-anker), `MergeError`.

- **The household mutations of the family portal** (CR-13 phase 3, #1250;
  `household_service.py`): `household_of`, `household_person`, the cores the
  one save of a household calls (`apply_person_fields`,
  `insert_household_person`, `detach_household_person`, `apply_address`),
  `person_payload`, `actor_of`, and the refusals (`HouseholdNotFound`,
  `PersonNotFound`, `OutsideHousehold`, `CannotRemoveSelf`, `HouseholdRefused`,
  `PersonDetailsMissing`) with `household_refusals_as_http` for a door. The
  household and its persons are master data (Koen, 27 September 2026), so their
  door is here too: the screen route in `ui.py`. The JSON routes for one person
  went with CR-13 phase 4b (#1251): they had no caller. The portal page itself stays
  `membership`'s; these doors ask it for the logged-in member and the page to
  answer with (`membership.api.portal_member`, `family_portal_page`).
- **Rules on the objects** (CR-13 phase 3): `Person` refuses a blank first or last
  name; `MemberPerson.check()` / `Person.check()` require a birth date and a gender
  of every household member (#681), on every flush, with `MemberPerson.require_details`
  for a door that asks before it writes. One exception by name: the member report
  import (`MEMBER_REPORT_IMPORT`, Koen, 29 September 2026). `Person.primary_contact(type)`
  is the one answer to "this person's main e-mail, mobile, …".

## Events (kernel, §5.8 — trede 1)

- Publiceert `EntityMerged` (`app.kernel.contracts.mdm`) bij elke merge.
- Subscribes to `CircleStartChosen` (`app.kernel.contracts.meetings`, #1346): stores
  the start date of a circle relation, refused by `OrganizationPerson.check()` when
  it lies after the end (`mdm.handlers`).

## Data

Schema `mdm` (migratie 078). **Soft-ref-patroon (§6/§8)**: consumenten buiten
het component (registrations, memberships, payments, forms) bewaren
masterdata-id's als waarde zónder DB-FK en lezen via `resolve()`; de
cross-schema FK's zijn in 078 gedropt. Binnen het schema blijven de FK's
gewoon staan (o.a. `member_persons.person_id` RESTRICT, #97).

`persons.superseded_by_id` wijst altijd rechtstreeks naar de eind-overlever;
een merge wordt nooit een hard delete. History is append-only en overleeft de
bron (unmerge gebruikt de `person_merged`-snapshot).
