# membership — componentcontract (fase 4a, #402)

**Doel.** Lidmaatschappen: jaarrecords per gezin, geldigheidsregel
("mag deze persoon de ledenprijs?", #111) en het hernieuwingsvenster.

## Facade (`api.py`) — de enige toegangsdeur voor andere componenten

- `has_valid_membership(person, ref_date=None)` / `valid_membership_until(...)`
  — dé geldigheidsregel (actief + binnen `[valid_from, valid_to]`).
- `is_member(db, email)` — de vraag van andere componenten (activities, §5.4):
  lost e-mail → Person op via het auth-component en past de regel toe.
- `renewal_open(today=None)` / `renewal_available(valid_until, today=None)` —
  het hernieuwingsvenster (§19.3: één plek; `MEMBERSHIP_RENEWAL_START_MD`).
- Modellen als type: `Membership`, `MembershipHistory`.

## Data

Schema `membership` (migratie 080): `memberships`, `membership_history`.
`member_id` is een soft-ref naar `mdm.members` (§6/§8, FK gedropt in 078);
de ORM-relatie via backref blijft voor intern gemak. Activatie na betaling
gebeurt door het payment-component (idempotent, #113).
