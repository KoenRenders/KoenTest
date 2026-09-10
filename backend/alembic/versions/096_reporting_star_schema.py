"""Reporting phase 1 (#832): the ``reporting`` schema with the first star.

CR-06 §4.1. Read-only views over the live tables — three facts and the dimensions
they share — named the way a board member names things, with the model's history
and soft-delete mechanics hidden. No materialized views and no extensions: at a
few hundred rows per fact Postgres answers in milliseconds.

**Why the SQL is spelled out here instead of imported from the domain.** A
migration is a snapshot: it must keep doing what it did on the day it ran. A view
definition that lives in a module would silently change what this file executes on
a fresh database, and then two environments built from the same chain would not
hold the same views. Changing a view therefore means a *new* migration with
``CREATE OR REPLACE VIEW`` — additive, per CR-06 §4.1.

**Soft deletes.** Every source row is filtered on ``deleted_at IS NULL``, with one
deliberate exception, stated in the view comment of ``f_payments``: a payment is a
financial fact and stays in the fact even when the registration or membership it
paid for was removed. Its enrichment joins therefore reach through soft-deleted
payables — the same choice the payments export already makes.

**Labels.** #779 (codes in the database, Enum in the code) does not exist yet, and
the code tables that *do* exist do not match the stored values: ``payment_records
.status`` holds ``pending``/``paid``/``failed``/``cancelled`` while
``payment_status_codes`` holds ``PENDING``/``PAID``/``FAILED`` and has no
``cancelled`` at all. So the code-list dimensions below carry their Dutch label
inline, and that is the one place in the reporting domain where they live. When
#779 lands the label moves to the code table and these views change additively.
``d_person`` and its gender label are the exception: ``mdm.gender_codes`` is a real
code table with matching values, so it is read.

**Tenant.** Every view carries ``tenant_id`` — a gate reads ``information_schema``
and fails on any view in this schema without it (CR-06 §7.1). The two dimensions
that have no tenant of their own (the date dimension and the code lists) are
crossed with the UNIT organizations, so the column means the same thing everywhere
and the engine can filter on it unconditionally.
"""
from alembic import op

revision = "096"
down_revision = "095"
branch_labels = None
depends_on = None


# The Dutch month names. `to_char` would need a server locale we do not control.
_MONTH_LABEL = """
        CASE EXTRACT(MONTH FROM d.day)::int
            WHEN 1 THEN 'januari' WHEN 2 THEN 'februari' WHEN 3 THEN 'maart'
            WHEN 4 THEN 'april' WHEN 5 THEN 'mei' WHEN 6 THEN 'juni'
            WHEN 7 THEN 'juli' WHEN 8 THEN 'augustus' WHEN 9 THEN 'september'
            WHEN 10 THEN 'oktober' WHEN 11 THEN 'november' ELSE 'december'
        END
"""

# One row per day per tenant. The range is generous on both ends so a trend never
# stops at the edge of the data; 4.000 days x 2 tenants costs nothing.
D_DATE = f"""
CREATE OR REPLACE VIEW reporting.d_date AS
SELECT
    o.id::int                                   AS tenant_id,
    d.day::date                                 AS date_key,
    EXTRACT(YEAR FROM d.day)::int               AS year,
    EXTRACT(QUARTER FROM d.day)::int            AS quarter,
    EXTRACT(MONTH FROM d.day)::int              AS month,
    to_char(d.day, 'YYYY-MM')                   AS year_month,
    {_MONTH_LABEL}                              AS month_label,
    {_MONTH_LABEL} || ' ' || EXTRACT(YEAR FROM d.day)::int::text AS month_year_label
FROM mdm.organizations o
CROSS JOIN generate_series(
    DATE '2015-01-01', (CURRENT_DATE + INTERVAL '2 years')::date, INTERVAL '1 day'
) AS d(day)
WHERE o.org_type = 'UNIT' AND o.deleted_at IS NULL
"""

# One row per activity. Component and product are NOT in this dimension: they sit
# at a finer grain and would multiply every activity-level measure. They travel on
# f_registrations itself, where the row already knows them (a degenerate dimension).
D_ACTIVITY = """
CREATE OR REPLACE VIEW reporting.d_activity AS
SELECT
    a.tenant_id,
    a.id                                        AS activity_id,
    a.name                                      AS activity_name,
    COALESCE(a.location, 'Onbekend')            AS location,
    a.is_cancelled,
    a.members_only,
    fd.first_date,
    EXTRACT(YEAR FROM fd.first_date)::int       AS activity_year
FROM activities.activities a
LEFT JOIN LATERAL (
    SELECT MIN(ad.start_date) AS first_date
    FROM activities.activity_dates ad
    WHERE ad.activity_id = a.id AND ad.deleted_at IS NULL
) fd ON TRUE
WHERE a.deleted_at IS NULL
"""

# One row per household. The address is the head of the family's, falling back to
# any member's — a household has one address in practice, and picking
# deterministically beats picking at random (#761 in spirit: no ORDER BY without a
# unique tail).
D_HOUSEHOLD = """
CREATE OR REPLACE VIEW reporting.d_household AS
SELECT
    m.tenant_id,
    m.id                                        AS household_id,
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

# One row per person. NO name and NO contact data — CR-06 §7.3: a count is a
# report, a list of people is a screen. The age group is the age today, not the age
# at some reference date; a person's age band is an attribute of the person here.
D_PERSON = """
CREATE OR REPLACE VIEW reporting.d_person AS
SELECT
    p.tenant_id,
    p.id                                        AS person_id,
    COALESCE(p.gender_code, 'X')                AS gender_code,
    COALESCE(gc.value, 'Onbekend')              AS gender_label,
    EXTRACT(YEAR FROM p.date_of_birth)::int     AS birth_year,
    CASE
        WHEN p.date_of_birth IS NULL THEN 'Onbekend'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 6 THEN '0-5'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 13 THEN '6-12'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 18 THEN '13-17'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 26 THEN '18-25'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 41 THEN '26-40'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 61 THEN '41-60'
        WHEN date_part('year', age(CURRENT_DATE, p.date_of_birth)) < 76 THEN '61-75'
        ELSE '76 of ouder'
    END                                         AS age_group,
    COALESCE(mp.relation_type, 'ONBEKEND')      AS relation_type_code,
    COALESCE(rt.value, mp.relation_type, 'Onbekend') AS relation_type_label,
    mp.member_id                                AS household_id
FROM mdm.persons p
LEFT JOIN mdm.gender_codes gc
       ON gc.code = p.gender_code AND gc.language = 'nl'
LEFT JOIN LATERAL (
    SELECT mp2.member_id, mp2.relation_type
    FROM mdm.member_persons mp2
    WHERE mp2.person_id = p.id AND mp2.deleted_at IS NULL
    ORDER BY (mp2.relation_type = 'HOOFDLID') DESC, mp2.id
    LIMIT 1
) mp ON TRUE
LEFT JOIN mdm.relation_type_codes rt
       ON rt.code = mp.relation_type AND rt.language = 'nl'
WHERE p.deleted_at IS NULL AND p.superseded_by_id IS NULL
"""


def _code_list(name: str, values: str) -> str:
    """A code-list dimension: the codes as they are stored, their Dutch label, and
    a sort order so a chart's bars keep the order a board member expects."""
    return f"""
CREATE OR REPLACE VIEW reporting.{name} AS
SELECT o.id::int AS tenant_id, c.code, c.label, c.sort_order
FROM mdm.organizations o
CROSS JOIN (VALUES {values}) AS c(code, label, sort_order)
WHERE o.org_type = 'UNIT' AND o.deleted_at IS NULL
"""


D_PAYMENT_METHOD = _code_list("d_payment_method", (
    "('online', 'Online', 1), ('transfer', 'Overschrijving', 2), ('cash', 'Cash', 3)"
))

D_PAYMENT_STATUS = _code_list("d_payment_status", (
    "('pending', 'In afwachting', 1), ('paid', 'Betaald', 2), "
    "('failed', 'Mislukt', 3), ('cancelled', 'Geannuleerd', 4)"
))

D_MEMBERSHIP_STATUS = _code_list("d_membership_status", (
    "('NEW', 'Nieuw', 1), ('RENEWED', 'Vernieuwd', 2), ('LAPSED', 'Vervallen', 3)"
))


# One row per household per membership year — and that is wider than the
# memberships table, on purpose. "How many lapse?" (CR-06 §3, question 2) cannot be
# answered from rows that exist: a lapsed household is exactly the one that has no
# row this year and did have one last year. So the grain is the grid of household x
# year, kept only where something happened in the year or the year before it.
#
# The three statuses are mutually exclusive and are also exposed as 0/1 columns, so
# every measure over this fact is a plain SUM. Counting with a CASE inside the
# universe would put the meaning of "renewed" in the semantic layer; it belongs in
# the view (CR-06 §11).
F_MEMBERSHIPS = """
CREATE OR REPLACE VIEW reporting.f_memberships AS
WITH ms AS (
    SELECT tenant_id, member_id AS household_id, year,
           MIN(id) AS membership_id, COUNT(*)::int AS row_count
    FROM membership.memberships
    WHERE deleted_at IS NULL
    GROUP BY tenant_id, member_id, year
),
grid AS (
    SELECT h.tenant_id, h.household_id, y.year
    FROM (SELECT DISTINCT tenant_id, household_id FROM ms) h
    JOIN (SELECT DISTINCT tenant_id, year FROM ms) y ON y.tenant_id = h.tenant_id
)
SELECT
    g.tenant_id,
    g.household_id,
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
    CASE WHEN cur.membership_id IS NOT NULL THEN COALESCE(sz.size, 0) ELSE 0 END AS person_count,
    COALESCE(pay.amount_charged, 0)::numeric(12, 2) AS amount_charged,
    COALESCE(pay.amount_paid, 0)::numeric(12, 2)    AS amount_paid,
    (COALESCE(pay.amount_charged, 0) - COALESCE(pay.amount_paid, 0))::numeric(12, 2) AS open_amount
FROM grid g
LEFT JOIN ms cur  ON cur.tenant_id = g.tenant_id
                 AND cur.household_id = g.household_id AND cur.year = g.year
LEFT JOIN ms prev ON prev.tenant_id = g.tenant_id
                 AND prev.household_id = g.household_id AND prev.year = g.year - 1
LEFT JOIN LATERAL (
    SELECT COUNT(*)::int AS size
    FROM mdm.member_persons mp
    WHERE mp.member_id = g.household_id AND mp.deleted_at IS NULL
) sz ON TRUE
LEFT JOIN LATERAL (
    SELECT SUM(pr.amount) AS amount_charged,
           SUM(COALESCE(pr.amount_paid, 0)) AS amount_paid
    FROM payment.payment_records pr
    JOIN membership.memberships mm
      ON mm.id = pr.payable_id AND mm.deleted_at IS NULL
    WHERE pr.payable_type = 'membership' AND pr.deleted_at IS NULL
      AND pr.tenant_id = g.tenant_id
      AND mm.member_id = g.household_id AND mm.year = g.year
) pay ON TRUE
WHERE cur.membership_id IS NOT NULL OR prev.membership_id IS NOT NULL
"""

# One row per registration line. A registration WITHOUT lines still produces one
# row (LEFT JOIN, quantity 0): a free component without products is a real
# registration, and a fact that drops it would answer "how many registered" with a
# number that is too low — the worst kind of reporting error.
#
# `unit_price` repeats the member-price rule of `activities.totals` in SQL: the
# member price applies when the registrant held a valid membership on the day of
# registration and the product has one. A test pins the view's total against that
# module for a seeded set, so the two cannot drift apart unnoticed.
F_REGISTRATIONS = """
CREATE OR REPLACE VIEW reporting.f_registrations AS
SELECT
    x.*,
    CASE WHEN x.is_free OR x.pay_on_site THEN 0::numeric(12, 2)
         ELSE (x.unit_price * x.quantity)::numeric(12, 2) END AS line_amount
FROM (
    SELECT
        reg.tenant_id,
        reg.id                                  AS registration_id,
        ri.id                                   AS registration_line_id,
        reg.activity_id,
        reg.component_id,
        COALESCE(comp.name, 'Onbekend')         AS component_name,
        ri.product_id,
        COALESCE(prod.name, 'Geen product')     AS product_name,
        COALESCE(ri.quantity, 0)                AS quantity,
        reg.person_id,
        reg.registered_at,
        reg.registered_at::date                 AS date_key,
        reg.registration_type,
        COALESCE(reg.payment_method, 'online')  AS method_code,
        (reg.team_name IS NOT NULL AND reg.team_name <> '')         AS has_team,
        (reg.contact_email IS NOT NULL AND reg.contact_email <> '') AS has_contact,
        COALESCE(prod.is_free, TRUE)            AS is_free,
        COALESCE(prod.pay_on_site, FALSE)       AS pay_on_site,
        mem.is_member,
        CASE
            WHEN prod.id IS NULL THEN 0::numeric(12, 2)
            WHEN mem.is_member AND prod.member_price IS NOT NULL AND prod.member_price >= 0
                THEN prod.member_price
            ELSE prod.price
        END                                     AS unit_price
    FROM activities.registrations reg
    LEFT JOIN activities.registration_items ri
           ON ri.registration_id = reg.id AND ri.deleted_at IS NULL
    LEFT JOIN activities.activity_products prod
           ON prod.id = ri.product_id AND prod.deleted_at IS NULL
    LEFT JOIN activities.activity_sub_registrations comp
           ON comp.id = reg.component_id AND comp.deleted_at IS NULL
    LEFT JOIN LATERAL (
        SELECT EXISTS (
            SELECT 1
            FROM mdm.member_persons mp
            JOIN membership.memberships mms
              ON mms.member_id = mp.member_id AND mms.deleted_at IS NULL
            WHERE mp.person_id = reg.person_id AND mp.deleted_at IS NULL
              AND mms.is_active
              AND mms.valid_from IS NOT NULL AND mms.valid_to IS NOT NULL
              AND mms.valid_from <= reg.registered_at::date
              AND reg.registered_at::date <= mms.valid_to
        ) AS is_member
    ) mem ON TRUE
    WHERE reg.deleted_at IS NULL
) x
"""

# One row per payment record — charges and refunds alike. A refund carries a
# NEGATIVE amount (the domain's convention, #83), so every SUM over this fact is
# already a net amount and needs no CASE.
#
# `age_bucket` and `open_days` are measured against CURRENT_DATE: an ageing report
# is about today by definition, so this view answers differently tomorrow. That is
# intended and it is why the ageing columns are not stored anywhere.
F_PAYMENTS = """
CREATE OR REPLACE VIEW reporting.f_payments AS
SELECT
    r.tenant_id,
    r.id                                        AS payment_id,
    r.payable_type,
    CASE r.payable_type
        WHEN 'registration' THEN 'Activiteit'
        WHEN 'membership' THEN 'Lidgeld'
        ELSE r.payable_type
    END                                         AS payable_type_label,
    r.payable_id,
    r.type                                      AS record_type,
    CASE r.type
        WHEN 'charge' THEN 'Vordering'
        WHEN 'refund' THEN 'Terugbetaling'
        ELSE r.type
    END                                         AS record_type_label,
    r.method                                    AS method_code,
    r.status                                    AS status_code,
    r.amount::numeric(12, 2)                    AS amount,
    COALESCE(r.amount_paid, 0)::numeric(12, 2)  AS amount_paid,
    (r.amount - COALESCE(r.amount_paid, 0))::numeric(12, 2) AS open_amount,
    CASE WHEN r.status = 'paid' AND r.paid_at IS NOT NULL
         THEN (r.paid_at::date - r.created_at::date) END AS days_to_paid,
    CASE WHEN r.status <> 'paid'
         THEN (CURRENT_DATE - r.created_at::date) END AS open_days,
    CASE
        WHEN r.status = 'paid' THEN 'Betaald'
        WHEN CURRENT_DATE - r.created_at::date <= 30 THEN '0-30 dagen'
        WHEN CURRENT_DATE - r.created_at::date <= 60 THEN '31-60 dagen'
        WHEN CURRENT_DATE - r.created_at::date <= 90 THEN '61-90 dagen'
        ELSE 'meer dan 90 dagen'
    END                                         AS age_bucket,
    r.created_at,
    r.created_at::date                          AS date_key,
    r.paid_at::date                             AS paid_date,
    reg.activity_id,
    reg.component_id,
    COALESCE(mshp.member_id, reghh.member_id)   AS household_id,
    mshp.year                                   AS membership_year
FROM payment.payment_records r
LEFT JOIN activities.registrations reg
       ON r.payable_type = 'registration' AND reg.id = r.payable_id
      AND reg.tenant_id = r.tenant_id
LEFT JOIN membership.memberships mshp
       ON r.payable_type = 'membership' AND mshp.id = r.payable_id
      AND mshp.tenant_id = r.tenant_id
LEFT JOIN LATERAL (
    SELECT mp.member_id
    FROM mdm.member_persons mp
    WHERE mp.person_id = reg.person_id AND mp.deleted_at IS NULL
    ORDER BY (mp.relation_type = 'HOOFDLID') DESC, mp.id
    LIMIT 1
) reghh ON TRUE
WHERE r.deleted_at IS NULL
"""


COMMENTS = {
    "d_date": (
        "Dagdimensie, een rij per dag per tenant (2015 t.e.m. twee jaar vooruit). "
        "Bevat geen seizoen: het model kent er geen (CR-06 §12, vraag 2)."
    ),
    "d_activity": (
        "Activiteit, een rij per activiteit. Soft-deleted activiteiten uitgesloten. "
        "Onderdeel en product staan NIET hier maar op f_registrations: ze liggen "
        "fijner en zouden elke maat op activiteitniveau vermenigvuldigen."
    ),
    "d_household": (
        "Gezin, een rij per gezin. Soft-deleted gezinnen uitgesloten. Adres = dat "
        "van het hoofdlid, anders van het eerste gezinslid."
    ),
    "d_person": (
        "Persoon, een rij per persoon. GEEN naam en GEEN contactgegevens (CR-06 "
        "§7.3). Soft-deleted en samengevoegde personen uitgesloten. Leeftijdsgroep "
        "= de leeftijd vandaag."
    ),
    "d_payment_method": "Codelijst betaalwijze. Label hier tot #779 bestaat.",
    "d_payment_status": "Codelijst betaalstatus. Label hier tot #779 bestaat.",
    "d_membership_status": (
        "Codelijst lidmaatschapsstatus (nieuw/vernieuwd/vervallen), afgeleid in "
        "f_memberships. Label hier tot #779 bestaat."
    ),
    "f_memberships": (
        "Feit lidmaatschap, een rij per gezin per jaar waarin dat gezin lid was of "
        "het jaar ervoor lid was. Soft-deleted lidmaatschappen uitgesloten. Een "
        "rij met status LAPSED heeft geen lidmaatschap: haar maten zijn 0."
    ),
    "f_registrations": (
        "Feit inschrijving, een rij per inschrijfregel. Een inschrijving zonder "
        "regels levert één rij met aantal 0. Soft-deleted inschrijvingen, regels "
        "en producten uitgesloten."
    ),
    "f_payments": (
        "Feit betaling, een rij per betaalrecord (vordering én terugbetaling; een "
        "terugbetaling draagt een negatief bedrag). Soft-deleted betalingen "
        "uitgesloten — maar de verrijking (activiteit, gezin) reikt BEWUST door "
        "soft-deleted inschrijvingen en lidmaatschappen heen: een betaling is een "
        "financieel feit en blijft in het feit staan als datgene waarvoor betaald "
        "werd verwijderd is."
    ),
}

# The order matters only for readability; views here never depend on each other.
VIEWS = [
    ("d_date", D_DATE),
    ("d_activity", D_ACTIVITY),
    ("d_household", D_HOUSEHOLD),
    ("d_person", D_PERSON),
    ("d_payment_method", D_PAYMENT_METHOD),
    ("d_payment_status", D_PAYMENT_STATUS),
    ("d_membership_status", D_MEMBERSHIP_STATUS),
    ("f_memberships", F_MEMBERSHIPS),
    ("f_registrations", F_REGISTRATIONS),
    ("f_payments", F_PAYMENTS),
]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS reporting")
    for name, sql in VIEWS:
        # DROP first: CREATE OR REPLACE refuses a changed column list, and on a
        # re-run of a partially applied chain that is exactly what we would hit.
        op.execute(f"DROP VIEW IF EXISTS reporting.{name} CASCADE")
        op.execute(sql)
        comment = COMMENTS[name].replace("'", "''")
        op.execute(f"COMMENT ON VIEW reporting.{name} IS '{comment}'")


def downgrade() -> None:
    for name, _sql in reversed(VIEWS):
        op.execute(f"DROP VIEW IF EXISTS reporting.{name} CASCADE")
    op.execute("DROP SCHEMA IF EXISTS reporting CASCADE")
