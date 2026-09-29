"""The dashboard counts households that are a member today (#1307).

Koen, 29 September 2026: the member list showed 110 active households, the
dashboard 109. There were four definitions of "active household", and the tile
had the odd one: active membership ROWS carrying this year's number. A household
that renews after the turnover date gets next year's membership, valid from the
day it paid — a member today, and missing from the tile until 1 January. And it
counted rows, not households, under the label "Actieve gezinnen".

The one rule now lives in `membership.service.valid_on`: active, and today falls
within the validity period. This migration brings the two reporting pieces in
line with it:

- `f_members.is_valid_today` lacked `is_active` — a fourth definition, one word
  short. It gains it, so the flag means exactly the rule;
- the shipped tile report `dashboard_active_members` becomes "households that are
  a member today": the household count `member_total_count` filtered on that flag,
  the same shape as the persons tile beside it. No year filter any more.

`test_active_households_parity` holds the SQL here and the Python rule together.
"""

import json

import sqlalchemy as sa
from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
# `repr` with double quotes (#781): the generated file must already be what
# `ruff format` writes, or every new migration turns CI red. A `repr` still, not
# a bare string, because `down_revision` is a tuple for a merge and None for the
# first migration.
revision = "169_2026_09_29_090415"
down_revision = "168_2026_09_29_073633"
branch_labels = None
depends_on = None


F_MEMBERS = """
CREATE OR REPLACE VIEW reporting.f_members AS
SELECT
    m.tenant_id,
    m.id                                        AS member_id,
    m.created_at                                AS created_at,
    m.created_at::date                          AS date_key,
    hoofd.person_id                             AS head_person_id,
    (EXISTS (SELECT 1 FROM membership.memberships ms
             WHERE ms.member_id = m.id AND ms.deleted_at IS NULL)) AS was_ever_member,
    (EXISTS (SELECT 1 FROM membership.memberships ms
             WHERE ms.member_id = m.id AND ms.deleted_at IS NULL
               AND ms.is_active
               AND ms.valid_from IS NOT NULL AND ms.valid_to IS NOT NULL
               AND CURRENT_DATE BETWEEN ms.valid_from AND ms.valid_to))
                                                AS is_valid_today
FROM mdm.members m
LEFT JOIN LATERAL (
    SELECT mp.person_id
    FROM mdm.member_persons mp
    WHERE mp.member_id = m.id AND mp.deleted_at IS NULL
    ORDER BY (mp.relation_type = 'HOOFDLID') DESC, mp.id
    LIMIT 1
) hoofd ON TRUE
WHERE m.deleted_at IS NULL
"""

F_MEMBERS_BEFORE = """
CREATE OR REPLACE VIEW reporting.f_members AS
SELECT
    m.tenant_id,
    m.id                                        AS member_id,
    m.created_at                                AS created_at,
    m.created_at::date                          AS date_key,
    hoofd.person_id                             AS head_person_id,
    (EXISTS (SELECT 1 FROM membership.memberships ms
             WHERE ms.member_id = m.id AND ms.deleted_at IS NULL)) AS was_ever_member,
    (EXISTS (SELECT 1 FROM membership.memberships ms
             WHERE ms.member_id = m.id AND ms.deleted_at IS NULL
               AND ms.valid_from IS NOT NULL AND ms.valid_to IS NOT NULL
               AND CURRENT_DATE BETWEEN ms.valid_from AND ms.valid_to))
                                                AS is_valid_today
FROM mdm.members m
LEFT JOIN LATERAL (
    SELECT mp.person_id
    FROM mdm.member_persons mp
    WHERE mp.member_id = m.id AND mp.deleted_at IS NULL
    ORDER BY (mp.relation_type = 'HOOFDLID') DESC, mp.id
    LIMIT 1
) hoofd ON TRUE
WHERE m.deleted_at IS NULL
"""

ACTIVE_HOUSEHOLDS = {
    "objects": ["member_total_count"],
    "filters": [{"object": "member_valid_today", "operator": "eq", "values": ["Ja"]}],
    "sort": [],
    "layout": "table",
    "pivot_column": "",
}
ACTIVE_HOUSEHOLDS_DESCRIPTION = "Gezinnen die vandaag lid zijn."

ACTIVE_MEMBERSHIPS_BEFORE = {
    "objects": ["membership_active_count"],
    "filters": [
        {"object": "membership_year", "operator": "eq", "values": [], "symbolic": "dit_jaar"}
    ],
    "sort": [],
    "layout": "table",
    "pivot_column": "",
}
ACTIVE_MEMBERSHIPS_DESCRIPTION_BEFORE = "Lidmaatschappen van dit jaar die op actief staan."


def _set_tile_report(selection: dict, description: str) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE reporting.saved_reports "
            "SET selection = CAST(:s AS json), description = :d "
            "WHERE builtin_key = 'dashboard_active_members'"
        ),
        {"s": json.dumps(selection), "d": description},
    )


def upgrade() -> None:
    op.execute(F_MEMBERS)
    _set_tile_report(ACTIVE_HOUSEHOLDS, ACTIVE_HOUSEHOLDS_DESCRIPTION)


def downgrade() -> None:
    # Restores the schema and the shipped report as they were. A tile report
    # someone edited after this migration is overwritten with the old selection,
    # as the upgrade overwrote the old one: it is a shipped report, not theirs.
    op.execute(F_MEMBERS_BEFORE)
    _set_tile_report(ACTIVE_MEMBERSHIPS_BEFORE, ACTIVE_MEMBERSHIPS_DESCRIPTION_BEFORE)
