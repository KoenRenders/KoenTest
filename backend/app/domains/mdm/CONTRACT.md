# mdm — master data

*First written for fase 2, #400.*

## Purpose and process

**Doel.** Masterdata: identiteit van personen en gezinnen, adressen,
contactgegevens, postcodes, externe nummers, organisaties (ACCOUNT/UNIT) en de
bijbehorende codetabellen — plus merge/survivorship.

*Process (A2.1 — membership: joining, changing, leaving, for the persons and the household; and the party under every other process).* Aggregates with a `check()` of their own: `Person`, `MemberPerson`, `PartyRelationship`, `ContactDetail`; beside them `Member` (the household), `Address`, `Organization` with its identifications and bank accounts, and the `Tenant` with its modules (CR-20).

## Publishes

### Facade (`api.py`) — de enige toegangsdeur voor andere componenten

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

### Events (kernel, §5.8 — trede 1)

- Publiceert `EntityMerged` (`app.kernel.contracts.mdm`) bij elke merge.
- Publishes `BoardMemberReported` and `MembershipReported` (CR-13 phase 4c, #1251)
  when the member import is applied: the report names a board member with an
  address and no login, and lists a household as a member for its year. `auth`
  makes the login, `membership` adds the membership, each in the import's
  transaction. Not optional: the import refuses to publish into silence. What the
  preview counts is read through `auth.api.has_login` and
  `membership.api.has_membership_for_year`.
- Subscribes to `CircleStartChosen` (`app.kernel.contracts.meetings`, #1346): stores
  the start date of a circle relation, refused by `PartyRelationship.check()` when
  it lies after the end (`mdm.handlers`).

**The account scope (CR-26 phase 1).** A person, a household, an organisation
and what hangs on them belong to the account (`AccountMixin`, `parties`), not to
a tenant. What a tenant sees is what has a fact at it: two views of migration
314, `mdm.household_tenants` and `mdm.person_tenants`, read by `facts.py` and
the reporting views. **A new kind of fact** — an invoice, a webshop customer —
adds a branch to `mdm.person_tenants` in a migration of its own; forgotten, the
person is simply not at the tenant, and nothing fails.

**One pointer: the party (CR-26 phase 3).** An address, a contact detail, a bank
account, an identification (`party_identifications`) and a member number hang on
a party by `party_id` — the person's or the organisation's — never by a pair of
`person_id` and `organization_id` (`tests/test_pointer_gate.py`). The member
number stays a fact per department (`external_numbers.tenant_id`). A screen that
asks "whose" goes through the owner's `party_id` (`Person.address`,
`Person.contact_details`, `ExternalNumber.person` do it for a person).

*Counted in the code on 13 October 2026:* the facade exports 184 names (100 functions, 65 classes, 19 values); events it owns (`kernel/contracts/`): `BoardMemberReported`, `EmailAddressAdded`, `EntityMerged`, `HouseholdDeleted`, `MembershipReported`, `TenantCreated`; ports it offers: `CreateHousehold`.

## Consumes

*Counted in the code on 13 October 2026:* imports the facades of activities, auth, membership, payment; subscribes to `AccountCodeEntered`, `AddressCodeEntered`, `CircleStartChosen`; calls no port.

## Owns

### Data

Schema `mdm` (migratie 078). **Soft-ref-patroon (§6/§8)**: consumenten buiten
het component (registrations, memberships, payments, forms) bewaren
masterdata-id's als waarde zónder DB-FK en lezen via `resolve()`; de
cross-schema FK's zijn in 078 gedropt. Binnen het schema blijven de FK's
gewoon staan (o.a. `member_persons.person_id` RESTRICT, #97).

`persons.superseded_by_id` wijst altijd rechtstreeks naar de eind-overlever;
een merge wordt nooit een hard delete. History is append-only en overleeft de
bron (unmerge gebruikt de `person_merged`-snapshot).

*Counted in the code on 13 October 2026:* schema `mdm`, 39 tables (16 data, 23 code and label), 13 of them with `tenant_id`; status columns: none; jobs: none.

## Screens

`ui.py`: 14 routes under `/admin/leden`, `/admin/leden-import` and `/leden/gezin` (the household's own persons). The platform screens Organisaties and Tenants are drawn by `app/ui/` and ask this facade.

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

| Standard | Element | Our name | Follows / deviates, with the reason |
|---|---|---|---|
| UBL 2.1 | `cac:Party/cac:Person` (`cbc:FirstName`, `cbc:FamilyName`) | `mdm.persons` · `first_name`, `last_name` | follows; the column names stay (`AGENTS.md`: do not rename) |
| UBL 2.1 | `cac:BuyerCustomerParty/cac:Party` | `mdm.persons.id`, referenced by value from a registration | follows: the party is the person, no customer table |
| UBL 2.1 | `cac:PartyLegalEntity` (`cbc:CompanyLegalForm`, `cbc:RegistrationName`) | `mdm.organizations` · `legal_form`, `name` | follows: singular on the party |
| UBL 2.1; ISO 6523 / ICD; ISO 3166-1 alpha-2 | `cac:PartyIdentification`, `cac:PartyTaxScheme`, repeatable, with a scheme and a country | `mdm.party_identifications` · `scheme`, `value`, `country`, on the party | follows: a table, never a column per kind |
| UBL 2.1; ISO 20022 | `cac:PayeeFinancialAccount`; `IBAN`, `BICFI` | `mdm.bank_accounts` · `iban`, `bic`, `beneficiary` | follows the shape (a table of its own, #945); deviates in the names: UBL's `cbc:ID` is unreadable on a screen, the mapping is one line in the docstring |
| UBL 2.1; vCard | `cac:Contact` (`cbc:ElectronicMail`, `cbc:Telephone`, `cbc:WebsiteURI`); `EMAIL`, `TEL` with `PREF` | `mdm.contact_details` · `contact_type_code`, `value`, `is_primary` | follows vCard (repeatable and typed); the primary maps to UBL's one element |
| UBL 2.1 | `cac:PostalAddress` with `cac:Country` | `mdm.addresses`, hung on the party; the postal code from the lookup table | follows |
| OpenID Connect | `email_verified` | `mdm.contact_details.confirmed_at` | follows the meaning; a timestamp instead of a boolean, because *when* matters for an audit |
| E.164 | telephone number | `mdm.contact_details` · MOBILE, stored as typed | deviates: "not now" — no sending party needs the international form yet (CR-22 B3a) |
| none named: our own one list of language codes | language code | `mdm.language_codes` (`nl`, `en`), the target of the `language` column of every label table | follows (CR-12 §B2.4) |
| ISO 8601 | date and time with offset | `DateTime(timezone=True)` on every timestamp | follows |

## Rules and gates

- **Rules whose home is this module** — `Person`: `@validates` on `first_name` and `last_name`, and `check()`; `MemberPerson.check()`, `PartyRelationship.check()`, `ContactDetail.check()`; 3 `CheckConstraint`s in `models.py`. `new_contact_detail` is the one place a `ContactDetail` is made.
- **Gates in this module's own `tests/`** — none among its 63 test files. The gates about it stand in `backend/tests/`: `test_contact_detail_factory_gate.py`, `test_contact_labels_gate.py`.

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E8** — the consent register in master data, then segments; planned beyond phase A of CR-05.
- **E15** — the domain model as a party model (CR-04): proposal, not scheduled.
- **E24** — the tenant apart from the organisation (CR-20): `mdm.tenants` holds the site (code, kind, account, the organisation shown, site name, time zone); `mdm.organizations` keeps the party, with no role column (an account is the organisation a tenant names); built in phase 1 for v2.17.
- **E28** — the party model (CR-26, to be written): the vocabulary for a person, a household and an organisation; parked.
- **E29** — the label of the kind `ACCOUNT` is "Account": built on `master` for v2.17 (#1945).
- **E30** — workbench tasks for the member administration (a new household, a changed member): open.
- **E34** — parked on v2.19: #1883 (Lid worden shows a signed-in visitor as the main member).
