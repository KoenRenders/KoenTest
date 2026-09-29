# audit — component contract (CR-13 phase 4)

**Purpose.** The trail of who changed what: append-only history rows for master
data, memberships, registrations, activities and payments, and the change screens
and export that read them (the list the treasurer types over into the national
member programme).

## Facade (`api.py`) — the only door for other components

- **Snapshots** (`service.py`): `snapshot_person`, `snapshot_member`,
  `snapshot_member_person`, `snapshot_membership`, `snapshot_address`,
  `snapshot_contact_detail`, `snapshot_registration`, `snapshot_registration_item`,
  `snapshot_payment_record`, `snapshot_activity`, `snapshot_activity_date`,
  `snapshot_component`, `snapshot_product` — one history row per change, written
  in the caller's transaction. `PUBLIEKE_ACTOR` for a change by a visitor.
- **Changes** (`changes.py`): `member_changes_since`, `all_changes_since`,
  `build_member_changes_ods`, `GROUPS`.

## Data

Audit owns no table. Every history table is its domain's model, in that domain's
schema, next to the table it records (`models.py` says so). History is
append-only: a row is never changed or deleted by the application.

## Events

None yet. The snapshots are called directly by the writing services (84 calls,
`COMMAND_CALLS`); turning them into events that audit subscribes to is part of
CR-13 phase 4.
