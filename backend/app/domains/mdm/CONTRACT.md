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

## Events (kernel, §5.8 — trede 1)

- Publiceert `EntityMerged` (`app.kernel.contracts.mdm`) bij elke merge.

## Data

Schema `mdm` (migratie 078). **Soft-ref-patroon (§6/§8)**: consumenten buiten
het component (registrations, memberships, payments, forms) bewaren
masterdata-id's als waarde zónder DB-FK en lezen via `resolve()`; de
cross-schema FK's zijn in 078 gedropt. Binnen het schema blijven de FK's
gewoon staan (o.a. `member_persons.person_id` RESTRICT, #97).

`persons.superseded_by_id` wijst altijd rechtstreeks naar de eind-overlever;
een merge wordt nooit een hard delete. History is append-only en overleeft de
bron (unmerge gebruikt de `person_merged`-snapshot).
