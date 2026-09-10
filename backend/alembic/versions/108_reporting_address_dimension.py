"""Reporting phase 9 (#850): the address as a dimension of its own.

Koen: *"Ik zou adressen graag apart hebben, die dan refereert naar `d_member`. Je
kan er zeker van zijn dat adressen ooit ook buiten members gaan terugkomen. Als we
naar een ERP met andere modules groeien."* That is the whole reason. A block of
address columns on the household dimension works until the day a second thing has
an address — a location, a supplier, a hall — and then the address model is in the
universe three times.

**The data model itself does not change here.** An address hangs off a person
(`mdm.addresses.person_id`) and that stays. Making the address generic in the
master data is an ERP decision Koen takes separately, explicitly not in v2.3, and
there is no groundwork for it in this migration.

**The grain is one address per person, and the database enforces it — partially.**
`uq_addresses_person_id` (migration 053) is `UNIQUE (person_id) WHERE deleted_at
IS NULL`. So a person can have one *live* address and any number of soft-deleted
ones: somebody who moves twice leaves three rows behind, two of them deleted. The
whole grain of this view therefore rests on its `WHERE a.deleted_at IS NULL`
matching the index predicate exactly. Drop that one line and the view silently
returns a row per former address, a join through it multiplies the facts
underneath, and the numbers stay plausible enough that nobody looks. That is what
`test_reporting_address.py` fixes with a gate that was broken once on purpose.

**It hangs off `d_person`, not off `d_member`, and that is not a detail.** The
address is at person grain; the household is not. Since migration 044 (#125) only
the hoofdlid carries the household address, so today the two grains happen to
coincide — but that is a convention in the write path, not a constraint, and one
non-hoofdlid with an address would make a chained household join count that
household twice. `member_id` rides along as the reference Koen asked for, and a
report that wants "households per municipality" uses the postcode and municipality
on `d_member`, which are already lifted to household grain.

Those two stay, and the descriptions say once what the difference is, so a board
member picks the right one:
- `d_address` — the whole address, per person. For "waar woont wie".
- postcode/municipality on `d_member` — the derived household picture. For
  "hoeveel gezinnen per gemeente".

Street and house number are personal data: declared under the person-detail role
and bounded by the door in front of the screen (CR-06 §7.3). Postcode and
municipality are not, and stay groupable under the same small-cell guard as their
household counterparts.
"""
from alembic import op

revision = "108"
down_revision = "107"
branch_labels = None
depends_on = None


D_ADDRESS = """
CREATE OR REPLACE VIEW reporting.d_address AS
SELECT
    a.tenant_id,
    a.id                                        AS address_id,
    a.person_id,
    mp.member_id,
    a.street,
    a.house_number,
    COALESCE(a.bus_number, '')                  AS bus_number,
    TRIM(a.street || ' ' || a.house_number ||
         CASE WHEN COALESCE(a.bus_number, '') <> ''
              THEN ' bus ' || a.bus_number ELSE '' END) AS address_line,
    COALESCE(pc.postal_code, 'Onbekend')        AS postal_code,
    COALESCE(pc.municipality, 'Onbekend')       AS municipality
FROM mdm.addresses a
LEFT JOIN mdm.postal_codes pc ON pc.id = a.postal_code_id
LEFT JOIN LATERAL (
    SELECT mp2.member_id
    FROM mdm.member_persons mp2
    WHERE mp2.person_id = a.person_id AND mp2.deleted_at IS NULL
    ORDER BY (mp2.relation_type = 'HOOFDLID') DESC, mp2.id
    LIMIT 1
) mp ON TRUE
WHERE a.deleted_at IS NULL
"""

COMMENT = (
    "Adres, een rij per adres — en feitelijk één per persoon, want een adres hangt "
    "aan een persoon (`mdm.addresses.person_id`). Die uniciteit is NIET in de "
    "databank afgedwongen; er staat een gate op de korrel omdat een tweede adres "
    "per persoon de feiten eronder stil zou vermenigvuldigen. Hangt aan "
    "`d_person` en niet aan `d_member`: het adres ligt op persoonskorrel, en aan "
    "het gezin hangen zou een gezin tellen per bewoner met een adres. "
    "`member_id` is de verwijzing naar het gezin. Voor 'hoeveel gezinnen per "
    "gemeente' gebruik je postcode/gemeente op d_member — die staan al op "
    "gezinskorrel. Straat en huisnummer zijn persoonsgegevens (CR-06 §7.3). "
    "Soft-deleted adressen uitgesloten."
)


def upgrade() -> None:
    op.execute(D_ADDRESS)
    op.execute(f"COMMENT ON VIEW reporting.d_address IS "
               f"'{COMMENT.replace(chr(39), chr(39) * 2)}'")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS reporting.d_address CASCADE")
