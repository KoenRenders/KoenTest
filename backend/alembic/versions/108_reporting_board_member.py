"""Reporting phase 8 (#849): the responsible board member as a dimension.

Koen: *"Het bestuurslid dat toegewezen is aan een gezin. Een bestuurslid neemt de
leden in zijn omgeving tot zijn verantwoordelijkheid."* The data has been there all
along — `mdm.members.board_member_id` — and the family portal already calls it
**"Verantwoordelijk bestuurslid"**. That is the term everywhere: in the universe,
in the report titles, on every screen. The word that goes round in conversation is
not in the product and does not enter here.

What was missing is the ability to report on it, and two questions follow at once:
how many households does each board member carry, and which of mine have not
renewed. The second is not a number but a **work list**, which is what the
assignment exists for.

**A household without a board member has to stay visible.** `board_member_id` is
nullable, so those exist, and "not assigned" is one of the most useful answers this
report gives. The join is a LEFT JOIN and the label falls back to a readable
"Niet toegewezen" instead of an empty cell that reads like a rendering fault.

**The dimension carries the CURRENT assignment, not a history.** A household that
moved from one board member to another shows only where it sits today; a report run
last month is not reproducible from it. Saying so in the view comment is cheaper
than somebody finding out from a number.

The name is a person's name, so it declares `member_details` and is bounded by the
role that reaches the screen (CR-06 §7.3, 10 September 2026).
"""
from alembic import op

revision = "108"
down_revision = "107"
branch_labels = None
depends_on = None


# One row per board member who carries at least one household.
D_BOARD_MEMBER = """
CREATE OR REPLACE VIEW reporting.d_board_member AS
SELECT DISTINCT
    m.tenant_id,
    p.id                                        AS board_member_id,
    (p.first_name || ' ' || p.last_name)        AS board_member_name
FROM mdm.members m
JOIN mdm.persons p
  ON p.id = m.board_member_id AND p.deleted_at IS NULL
WHERE m.deleted_at IS NULL
"""

# `d_member` gains the reference. Everything else about it is unchanged; the
# column list changes, so the view is recreated rather than replaced.
D_MEMBER = """
CREATE OR REPLACE VIEW reporting.d_member AS
SELECT
    m.tenant_id,
    m.id                                        AS member_id,
    m.board_member_id,
    COALESCE(sz.size, 0)                        AS household_size,
    CASE
        WHEN COALESCE(sz.size, 0) = 0 THEN 'Onbekend'
        WHEN sz.size = 1 THEN '1 persoon'
        WHEN sz.size = 2 THEN '2 personen'
        WHEN sz.size BETWEEN 3 AND 4 THEN '3-4 personen'
        ELSE '5 of meer'
    END                                         AS household_size_group,
    COALESCE(pc.postal_code, 'Onbekend')        AS postal_code,
    COALESCE(pc.municipality, 'Onbekend')       AS municipality,
    ms.first_year                               AS member_since_year,
    m.created_at::date                          AS created_date
FROM mdm.members m
LEFT JOIN LATERAL (
    SELECT COUNT(*)::int AS size
    FROM mdm.member_persons mp
    WHERE mp.member_id = m.id AND mp.deleted_at IS NULL
) sz ON TRUE
LEFT JOIN LATERAL (
    SELECT ad.postal_code_id
    FROM mdm.member_persons mp
    JOIN mdm.addresses ad ON ad.person_id = mp.person_id AND ad.deleted_at IS NULL
    WHERE mp.member_id = m.id AND mp.deleted_at IS NULL
    ORDER BY (mp.relation_type = 'HOOFDLID') DESC, mp.id
    LIMIT 1
) addr ON TRUE
LEFT JOIN mdm.postal_codes pc ON pc.id = addr.postal_code_id
LEFT JOIN LATERAL (
    SELECT MIN(ms2.year)::int AS first_year
    FROM membership.memberships ms2
    WHERE ms2.member_id = m.id AND ms2.deleted_at IS NULL
) ms ON TRUE
WHERE m.deleted_at IS NULL
"""

D_MEMBER_COMMENT = (
    "Gezin (Member in het model), een rij per gezin. Heette tot #848 "
    "`d_household`. Soft-deleted gezinnen uitgesloten. Adres = dat van het "
    "hoofdlid, anders van het eerste gezinslid. `board_member_id` verwijst naar "
    "het verantwoordelijke bestuurslid en is leeg als er geen toegewezen is."
)

D_BOARD_MEMBER_COMMENT = (
    "Verantwoordelijk bestuurslid, een rij per bestuurslid dat aan minstens één "
    "gezin toegewezen is. Draagt de HUIDIGE toewijzing en geen historie: een "
    "gezin dat vorige maand bij iemand anders hoorde, staat hier alleen waar het "
    "vandaag staat, en een rapport van vorige maand is er niet mee te "
    "reproduceren. Soft-deleted personen en gezinnen uitgesloten. De naam is een "
    "persoonsnaam; dat mag sinds CR-06 §7.3 en wordt begrensd door de rol die het "
    "scherm bereikt."
)


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS reporting.d_member CASCADE")
    op.execute(D_MEMBER)
    op.execute(f"COMMENT ON VIEW reporting.d_member IS "
               f"'{D_MEMBER_COMMENT.replace(chr(39), chr(39) * 2)}'")
    op.execute(D_BOARD_MEMBER)
    op.execute(f"COMMENT ON VIEW reporting.d_board_member IS "
               f"'{D_BOARD_MEMBER_COMMENT.replace(chr(39), chr(39) * 2)}'")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS reporting.d_board_member CASCADE")
