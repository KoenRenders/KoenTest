"""Reporting (#894): één object *Jaar*, ook voor de lidmaatschappen.

Koen: *"Een lidmaatschapsjaar hoort bij een lidmaatschap […]. Ik begrijp dus nog
niet waarom we het jaar voor lidmaatschappen dubbel nodig hebben — dat is hetzelfde
veld en de relaties zijn helder."*

Hij had gelijk, en de oorzaak was niet de naamgeving. Er is één gedeelde
datumdimensie `d_date` waar **zes** feiten aan hangen; de twee lidmaatschapsfeiten
waren de enige die dat niet deden en hun eigen `year`-kolom droegen. Twee feiten met
een eigen kolom geeft twee objecten — *Lidmaatschapsjaar* en *Jaar van het
lidmaatschap*, dezelfde woorden in een andere volgorde. Hernoemen loste dat niet op.

**Beslist door Koen op 12 september 2026: beide feiten haken aan op `d_date`, met
1 januari van hun jaar als dag.** Daarmee is er letterlijk één object *Jaar* in de
universe, en verdwijnen de twee oude.

> *"Ik vind het geen probleem dat ze aanhaken op 1 januari als datum. We lossen dat
> wel op als we ooit niet-kalenderjaren invoeren (bv. schooljaren) en er een apart
> object van maken."*

**De aanname staat in het commentaar op de weergave en niet alleen hier**, want daar
wordt ze gelezen: wie ooit een schooljaar invoert, ziet meteen waarom er een
1 januari staat in plaats van te moeten raden.

**En er hoort een grendel op, want de datum is verzonnen.** Op *Maand* of *Datum*
groeperen zou bij deze twee feiten alles op januari laten vallen: plausibel en
betekenisloos, dezelfde val als een detail waarop je kon groeperen (#852). Die
weigering staat in de motor, met de reden erin, en ze is zichtbaar sinds #877 van
een weigering een foutmelding maakte in plaats van een lege staat.

Wat de bewaarde rapporten betreft is dit het geval waarvoor #880 geschreven is: vier
ervan noemen een van de twee verdwijnende objecten, en die selecties gaan hieronder
mee. De gate valt om als er één achterblijft.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "116"
down_revision = "115"
branch_labels = None
depends_on = None


# `make_date(year, 1, 1)`: de dag is verzonnen, het jaar niet. De grendel in de
# motor zorgt dat niemand er een maand uit leest.
F_MEMBERSHIPS = """
CREATE OR REPLACE VIEW reporting.f_memberships AS
WITH ms AS (
    SELECT tenant_id, member_id, year,
           MIN(id) AS membership_id, COUNT(*)::int AS row_count,
           COUNT(*) FILTER (WHERE is_active)::int AS active_count
    FROM membership.memberships
    WHERE deleted_at IS NULL
    GROUP BY tenant_id, member_id, year
),
grid AS (
    SELECT h.tenant_id, h.member_id, y.year
    FROM (SELECT DISTINCT tenant_id, member_id FROM ms) h
    JOIN (SELECT DISTINCT tenant_id, year FROM ms) y ON y.tenant_id = h.tenant_id
)
SELECT
    g.tenant_id,
    g.member_id,
    g.year,
    cur.membership_id,
    CASE
        WHEN cur.membership_id IS NOT NULL AND prev.membership_id IS NOT NULL THEN 'RENEWED'
        WHEN cur.membership_id IS NOT NULL THEN 'NEW'
        ELSE 'LAPSED'
    END                                         AS status_code,
    CASE WHEN cur.membership_id IS NOT NULL THEN 1 ELSE 0 END AS is_member,
    CASE WHEN cur.membership_id IS NOT NULL AND prev.membership_id IS NULL THEN 1 ELSE 0 END AS is_new,
    CASE WHEN cur.membership_id IS NOT NULL AND prev.membership_id IS NOT NULL THEN 1 ELSE 0 END AS is_renewed,
    CASE WHEN cur.membership_id IS NULL THEN 1 ELSE 0 END AS is_lapsed,
    -- The number of ACTIVE membership rows, which is what the dashboard counts.
    -- `is_member` counts households and ignores the flag; these differ whenever a
    -- household has an inactive membership.
    COALESCE(cur.active_count, 0)               AS active_membership_count,
    CASE WHEN cur.membership_id IS NOT NULL THEN COALESCE(sz.size, 0) ELSE 0 END AS person_count,
    COALESCE(pay.amount_charged, 0)::numeric(12, 2) AS amount_charged,
    COALESCE(pay.amount_paid, 0)::numeric(12, 2)    AS amount_paid,
    (COALESCE(pay.amount_charged, 0) - COALESCE(pay.amount_paid, 0))::numeric(12, 2) AS open_amount,
    make_date(g.year, 1, 1)                     AS date_key
FROM grid g
LEFT JOIN ms cur  ON cur.tenant_id = g.tenant_id
                 AND cur.member_id = g.member_id AND cur.year = g.year
LEFT JOIN ms prev ON prev.tenant_id = g.tenant_id
                 AND prev.member_id = g.member_id AND prev.year = g.year - 1
LEFT JOIN LATERAL (
    SELECT COUNT(*)::int AS size
    FROM mdm.member_persons mp
    WHERE mp.member_id = g.member_id AND mp.deleted_at IS NULL
) sz ON TRUE
LEFT JOIN LATERAL (
    SELECT SUM(pr.amount) AS amount_charged,
           SUM(COALESCE(pr.amount_paid, 0)) AS amount_paid
    FROM payment.payment_records pr
    JOIN membership.memberships mm
      ON mm.id = pr.payable_id AND mm.deleted_at IS NULL
    WHERE pr.payable_type = 'membership' AND pr.deleted_at IS NULL
      AND pr.tenant_id = g.tenant_id
      AND mm.member_id = g.member_id AND mm.year = g.year
) pay ON TRUE
WHERE cur.membership_id IS NOT NULL OR prev.membership_id IS NOT NULL
"""

F_MEMBERSHIP_PERSONS = """
CREATE OR REPLACE VIEW reporting.f_membership_persons AS
SELECT DISTINCT ON (ms.tenant_id, mp.person_id, ms.year)
    ms.tenant_id,
    mp.person_id,
    ms.member_id,
    ms.year,
    ms.membership_id,
    -- Does this PERSON have a membership covering today? That is what the
    -- dashboard counts, and it is not the same question as "a membership for this
    -- year" — a household joining in October is valid today and belongs to next
    -- year. Asked over the person and not over this row, so the answer does not
    -- depend on which household the row happened to pick.
    (EXISTS (
        SELECT 1
        FROM mdm.member_persons mp2
        JOIN membership.memberships v
          ON v.member_id = mp2.member_id AND v.deleted_at IS NULL
        WHERE mp2.person_id = mp.person_id AND mp2.deleted_at IS NULL
          AND v.is_active
          AND v.valid_from IS NOT NULL AND v.valid_to IS NOT NULL
          AND v.valid_from <= CURRENT_DATE AND CURRENT_DATE <= v.valid_to
    ))                                          AS is_valid_today,
    make_date(ms.year, 1, 1)                    AS date_key
FROM (
    SELECT tenant_id, member_id, year, MIN(id) AS membership_id
    FROM membership.memberships
    WHERE deleted_at IS NULL
    GROUP BY tenant_id, member_id, year
) ms
JOIN mdm.member_persons mp
  ON mp.member_id = ms.member_id AND mp.tenant_id = ms.tenant_id
 AND mp.deleted_at IS NULL
JOIN mdm.persons p
  ON p.id = mp.person_id AND p.deleted_at IS NULL AND p.superseded_by_id IS NULL
ORDER BY ms.tenant_id, mp.person_id, ms.year, ms.member_id
"""

JAAR_AANNAME = (
    "`date_key` is 1 JANUARI van het lidmaatschapsjaar en is dus een verzonnen "
    "dag: hij bestaat alleen om aan de gedeelde datumdimensie te kunnen hangen, "
    "zodat er één object Jaar is in plaats van twee (#894). De aanname eronder is "
    "dat een lidmaatschapsjaar een KALENDERJAAR is. Voert iemand ooit "
    "niet-kalenderjaren in (schooljaren), dan klopt deze dag niet meer en hoort "
    "het jaar een eigen object te worden — Koen, 12 september 2026. Groeperen op "
    "maand of dag wordt geweigerd door de motor, want dan valt alles op januari: "
    "een plausibel ogende, betekenisloze uitkomst."
)

F_MEMBERSHIPS_COMMENT = (
    "Feit lidmaatschap, een rij per gezin per lidmaatschapsjaar — inclusief de "
    "gezinnen die dat jaar niet vernieuwden, want anders is 'hoeveel vervallen "
    "er' niet te tellen. " + JAAR_AANNAME
)

F_MEMBERSHIP_PERSONS_COMMENT = (
    "Feit lid (persoon), een rij per persoon per lidmaatschapsjaar. Een persoon "
    "in twee gezinnen telt één keer. " + JAAR_AANNAME
)

# De vier meegeleverde rapporten die een van de twee verdwijnende objecten noemen.
# `date_year` is hetzelfde jaar, nu uit de gedeelde dimensie.
HERSCHREVEN = {
    "members_per_year": {
        "objects": ["date_year", "membership_households", "membership_persons"],
        "filters": [],
        "sort": [{"object": "date_year", "direction": "desc"}],
        "layout": "table", "pivot_column": "",
    },
    "membership_flow_per_year": {
        "objects": ["date_year", "membership_status", "membership_count"],
        "filters": [],
        "sort": [{"object": "date_year", "direction": "desc"}],
        "layout": "table", "pivot_column": "",
    },
    "member_demographics": {
        "objects": ["date_year", "person_age_group", "member_municipality",
                    "membership_person_count"],
        "filters": [],
        "sort": [{"object": "date_year", "direction": "desc"}],
        "layout": "table", "pivot_column": "",
    },
    "dashboard_active_members": {
        "objects": ["membership_active_count"],
        "filters": [{"object": "date_year", "operator": "eq",
                     "values": [], "symbolic": "dit_jaar"}],
        "sort": [], "layout": "table", "pivot_column": "",
    },
    "households_per_board_member": {
        "objects": ["board_member", "date_year", "membership_status",
                    "membership_households", "membership_persons"],
        "filters": [{"object": "date_year", "operator": "eq",
                     "values": [], "symbolic": "dit_jaar"}],
        "sort": [{"object": "board_member", "direction": "asc"}],
        "layout": "table", "pivot_column": "",
    },
}


def upgrade() -> None:
    op.execute(F_MEMBERSHIPS)
    op.execute(f"COMMENT ON VIEW reporting.f_memberships IS "
               f"'{F_MEMBERSHIPS_COMMENT.replace(chr(39), chr(39) * 2)}'")
    op.execute(F_MEMBERSHIP_PERSONS)
    op.execute(f"COMMENT ON VIEW reporting.f_membership_persons IS "
               f"'{F_MEMBERSHIP_PERSONS_COMMENT.replace(chr(39), chr(39) * 2)}'")

    bind = op.get_bind()
    for sleutel, selectie in HERSCHREVEN.items():
        bind.execute(
            sa.text(
                "UPDATE reporting.saved_reports SET selection = CAST(:s AS json) "
                "WHERE builtin_key = :k "
                "  AND (selection::text LIKE '%membership_year%' "
                "    OR selection::text LIKE '%membership_person_year%')"
            ),
            {"s": json.dumps(selectie), "k": sleutel},
        )

    # Wat iemand zelf bouwde en een verdwenen object noemt, kan hier niet
    # gerepareerd worden — de selectie vroeg om iets dat niet meer bestaat. Melden
    # dus, in plaats van stil herschrijven.
    resterend = bind.execute(sa.text(
        "SELECT id, name FROM reporting.saved_reports "
        "WHERE deleted_at IS NULL AND builtin_key IS NULL "
        "  AND (selection::text LIKE '%membership_year%' "
        "    OR selection::text LIKE '%membership_person_year%')"
    )).fetchall()
    for rij in resterend:
        print(f"  #894: bewaard rapport {rij[0]} ({rij[1]}) gebruikt het oude "
              f"jaarobject; open het en kies Jaar.")


def downgrade() -> None:
    pass
