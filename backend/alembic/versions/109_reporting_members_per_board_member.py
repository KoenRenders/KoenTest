"""Reporting (#850): the report "Leden per bestuurslid", and what it needed.

Asked for by Koen on 10 September 2026. The report exists already — the
penningmeester makes it by hand for the voorzitter — and it is the first one that
needs both new dimensions at once: the responsible board member from #849 and the
address from this issue.

**One row per household, not per person.** Hoofdlid and partner are two columns on
the same row, so the grain of the report is the grain of `f_members` and nothing
in the selection may multiply it. Two things could:

- A household can hold more than one row with a partner relation type — nothing in
  the model forbids it. `partner_name` is therefore picked by a LATERAL with a
  deterministic order and `LIMIT 1`, so a second partner changes which name shows
  and never how many rows there are.
- The address is at person grain. It is reached through the **hoofdlid**
  (`f_members.head_person_id` → `d_person` → `d_address`), so exactly one address
  row can attach to a household.

**That join hangs off the fact and not off `d_member`, on purpose.** Putting it on
the dimension would have made the person reachable from *every* fact that reaches
a household — a membership, a payment — and silently turned "Leeftijdsgroep" on a
membership report into the head of the household's, where it is refused today. The
edge belongs to the one fact that needs it. Even there the word means the hoofdlid
rather than the registrant, and the object descriptions say so.

**The address is three columns and not one.** Koen asked for "adres (straat
huisnummer busnummer)". Composed into one string it sorts wrong, and this report
sorts on it; the split is the reason, not a preference.

**`house_number` is a `String(10)`, so alphabetically "10" comes before "9".** That
is precisely the column this report orders on, and a shuffled street is the kind of
fault that reads as a data problem rather than a sorting one. The view therefore
carries the natural sort key as two columns — the leading number as an integer and
whatever follows as text — and the universe object orders on those instead of on
its own label. `12`, `12A` and `12 bus 3` all sort after `9` and among themselves.

Deliberately **not** in the report: children. Koen asked for hoofdlid and partner.
And the scope is households with a membership that is valid **today**, through the
relative filter value of #847 — a hard-coded year would answer the wrong question
in January.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "109"
down_revision = "108"
branch_labels = None
depends_on = None


# `substring(... from '^\\d+')` and not a global digit-strip: "12 bus 3" must sort
# as 12, not as 123.
D_ADDRESS = r"""
CREATE OR REPLACE VIEW reporting.d_address AS
SELECT
    a.tenant_id,
    a.id                                        AS address_id,
    a.person_id,
    mp.member_id,
    a.street,
    a.house_number,
    NULLIF(substring(a.house_number from '^\d+'), '')::int AS house_number_num,
    regexp_replace(a.house_number, '^\d+', '')  AS house_number_rest,
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

D_ADDRESS_COMMENT = (
    "Adres, een rij per LEVEND adres, en dus een per persoon. Die uniciteit komt "
    "van `uq_addresses_person_id` (migratie 053), die PARTIEEL is: UNIQUE "
    "(person_id) WHERE deleted_at IS NULL. Wie verhuisd is, heeft hier dus "
    "soft-deleted adressen naast zijn huidige, en de korrel van deze weergave "
    "hangt volledig aan het feit dat haar WHERE dezelfde is als die van de index. "
    "Valt die filter weg, dan vermenigvuldigt een join hierdoor de feiten "
    "eronder; test_reporting_address.py houdt dat tegen. Hangt aan `d_person` en "
    "niet aan `d_member`: het adres ligt op persoonskorrel. Sinds migratie 044 "
    "draagt alleen het hoofdlid het gezinsadres, maar dat is een afspraak in het "
    "schrijfpad en geen constraint. `member_id` is de verwijzing naar het gezin. "
    "`house_number_num`/`house_number_rest` zijn de natuurlijke sorteersleutel: "
    "huisnummer is tekst, dus alfabetisch komt 10 voor 9. Voor 'hoeveel gezinnen "
    "per gemeente' gebruik je postcode/gemeente op d_member — die staan al op "
    "gezinskorrel. Straat en huisnummer zijn persoonsgegevens (CR-06 §7.3)."
)

# `d_member` gains the head of the household as a reference plus the two names the
# listing needs. Both picks are LATERAL with LIMIT 1: the grain of this dimension
# is one row per household and a second partner may change a name, never a count.
D_MEMBER = """
CREATE OR REPLACE VIEW reporting.d_member AS
SELECT
    m.tenant_id,
    m.id                                        AS member_id,
    m.board_member_id,
    COALESCE(hoofd.name, '')                    AS head_name,
    COALESCE(partner.name, '')                  AS partner_name,
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
    SELECT (p.first_name || ' ' || p.last_name) AS name
    FROM mdm.member_persons mp
    JOIN mdm.persons p ON p.id = mp.person_id AND p.deleted_at IS NULL
    WHERE mp.member_id = m.id AND mp.deleted_at IS NULL
    ORDER BY (mp.relation_type = 'HOOFDLID') DESC, mp.id
    LIMIT 1
) hoofd ON TRUE
LEFT JOIN LATERAL (
    SELECT (p.first_name || ' ' || p.last_name) AS name
    FROM mdm.member_persons mp
    JOIN mdm.persons p ON p.id = mp.person_id AND p.deleted_at IS NULL
    WHERE mp.member_id = m.id AND mp.deleted_at IS NULL
      AND mp.relation_type = 'PARTNER'
    ORDER BY mp.id
    LIMIT 1
) partner ON TRUE
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
    "het verantwoordelijke bestuurslid en is leeg als er geen toegewezen is. "
    "`head_name` en `partner_name` "
    "worden deterministisch gekozen (LATERAL met LIMIT 1): een tweede partner in "
    "hetzelfde gezin verandert welke naam er staat, nooit het aantal rijen."
)

# `f_members` gains the scope this report needs. "Valid today" is deliberately not
# "a membership for this year": somebody joining in October is valid today and
# belongs to next year, and the relative value `dit_jaar` of #847 would drop them.
# It is measured against CURRENT_DATE, so the report still answers correctly in
# January without a year anywhere in the selection — the same shape as
# `membership_person_valid_today` on the person grain.
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

F_MEMBERS_COMMENT = (
    "Feit gezin, een rij per gezin — ook een dat nooit lid was. "
    "`is_valid_today` toetst tegen CURRENT_DATE en is iets anders dan 'lid voor "
    "dit jaar': wie in oktober voor volgend jaar aansluit, is vandaag geldig en "
    "hoort bij volgend jaar. `head_person_id` is de sleutel naar het hoofdlid: "
    "langs die weg bereikt dit feit `d_person` en dus `d_address`, zonder dat de "
    "korrel verschuift — één hoofdlid per gezin."
)


# One row per household, so the measure is a household count and every other
# object is a household attribute. Sorted board member first, then the street and
# the natural house-number key that the universe object carries.
MEMBERS_PER_BOARD_MEMBER = {
    "objects": ["board_member", "address_street", "address_house_number",
                "address_bus", "member_head_name", "member_partner_name",
                "member_total_count"],
    "filters": [{"object": "member_valid_today", "operator": "eq",
                 "values": ["Ja"]}],
    "sort": [{"object": "board_member", "direction": "asc"},
             {"object": "address_street", "direction": "asc"},
             {"object": "address_house_number", "direction": "asc"},
             {"object": "address_bus", "direction": "asc"}],
    "layout": "pivot",
    "pivot_column": "",
}


def upgrade() -> None:
    # DROP and not REPLACE, here and below: the new columns land in the middle of
    # the column list and CREATE OR REPLACE may only append.
    op.execute("DROP VIEW IF EXISTS reporting.f_members CASCADE")
    op.execute(F_MEMBERS)
    op.execute(f"COMMENT ON VIEW reporting.f_members IS "
               f"'{F_MEMBERS_COMMENT.replace(chr(39), chr(39) * 2)}'")
    op.execute("DROP VIEW IF EXISTS reporting.d_address CASCADE")
    op.execute(D_ADDRESS)
    op.execute(f"COMMENT ON VIEW reporting.d_address IS "
               f"'{D_ADDRESS_COMMENT.replace(chr(39), chr(39) * 2)}'")
    op.execute("DROP VIEW IF EXISTS reporting.d_member CASCADE")
    op.execute(D_MEMBER)
    op.execute(f"COMMENT ON VIEW reporting.d_member IS "
               f"'{D_MEMBER_COMMENT.replace(chr(39), chr(39) * 2)}'")

    bind = op.get_bind()
    tenants = [row[0] for row in bind.execute(sa.text(
        "SELECT id FROM mdm.organizations "
        "WHERE org_type = 'UNIT' AND deleted_at IS NULL ORDER BY id"))]
    for tenant_id in tenants:
        bind.execute(
            sa.text(
                "INSERT INTO reporting.saved_reports "
                "  (tenant_id, name, description, selection, is_shared, builtin_key) "
                "SELECT :t, :n, :d, CAST(:s AS json), TRUE, :k "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM reporting.saved_reports "
                "   WHERE tenant_id = :t AND builtin_key = :k AND deleted_at IS NULL)"
            ),
            {"t": tenant_id,
             "n": "Leden per bestuurslid",
             "d": ("Eén rij per gezin met een vandaag geldig lidmaatschap: adres, "
                   "hoofdlid en partner, gegroepeerd per verantwoordelijk "
                   "bestuurslid, met het aantal gezinnen per bestuurslid."),
             "s": json.dumps(MEMBERS_PER_BOARD_MEMBER),
             "k": "members_per_board_member"},
        )


def downgrade() -> None:
    op.execute("DELETE FROM reporting.saved_reports "
               "WHERE builtin_key = 'members_per_board_member'")
