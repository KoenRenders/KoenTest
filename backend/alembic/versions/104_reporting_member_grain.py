"""Reporting phase 7 (#848): the member and activity grains, and one rename.

Five of the six dashboard tiles could not be answered by the universe, and not
because of filters but because of **grain** — there was no fact whose row was a
household or an activity. `f_memberships` holds only households that were ever a
member; `f_registrations` only activities that got a registration. For "all of
them" there was nothing.

**`d_household` becomes `d_member`, and completely** (Koen, 10 September 2026).
`Member` is what the household is called in the model, and two names for one thing
is exactly what makes somebody later wonder whether they are the same. The branch
is not merged, so this is one round instead of a rename migration on live data.
No alias is left behind — an alias is how both names keep living. That means the
foreign key on the three facts is renamed too: a `d_member` joined on
`household_id` would be half a rename, which is the worst of the three states.

**The new fact is `f_members`, not `f_households`.** #848 names it the second way,
and that would put `f_households` beside `d_member` on the day the rename exists
to stop exactly that. Reported to the master CLI; if the literal name is wanted,
it is one more rename while nothing is merged.

Two columns are added rather than derived later, because the dashboard counts
things the star could not say:

- `f_memberships.active_membership_count` — the tile counts membership ROWS with
  `is_active`, and `is_member` counts households and ignores the flag. Two
  different numbers whenever a household has an inactive membership.
- `f_membership_persons.is_valid_today` — the tile counts people whose membership
  covers **today** (`valid_from <= today <= valid_to`), which is not the same as
  "has a membership for this year". The September rule is precisely where the two
  come apart: a household joining in October is valid today and belongs to next
  year.

Both are stated as columns so the report can filter on them **visibly**, the same
choice as the task status: a condition you can see in the saved report beats one
baked into a view.
"""
import sqlalchemy as sa
from alembic import op

revision = "104"
down_revision = "103"
branch_labels = None
depends_on = None


D_MEMBER = """
CREATE OR REPLACE VIEW reporting.d_member AS
SELECT
    m.tenant_id,
    m.id                                        AS member_id,
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

# One row per household, member or not. The dashboard tile "Leden" counts exactly
# this, and `f_memberships` cannot: a household that never joined has no row there.
F_MEMBERS = """
CREATE OR REPLACE VIEW reporting.f_members AS
SELECT
    m.tenant_id,
    m.id                                        AS member_id,
    m.created_at                                AS created_at,
    m.created_at::date                          AS date_key,
    (EXISTS (SELECT 1 FROM membership.memberships ms
             WHERE ms.member_id = m.id AND ms.deleted_at IS NULL)) AS was_ever_member
FROM mdm.members m
WHERE m.deleted_at IS NULL
"""

# One row per activity, with or without registrations. `last_date` is what makes
# "upcoming" answerable: the tile asks for activities whose last day has not
# passed, which is `COALESCE(end_date, start_date)` of the furthest date row.
F_ACTIVITIES = """
CREATE OR REPLACE VIEW reporting.f_activities AS
SELECT
    a.tenant_id,
    a.id                                        AS activity_id,
    a.name                                      AS activity_name,
    COALESCE(a.location, 'Onbekend')            AS location,
    CASE WHEN a.is_cancelled THEN 'Ja' ELSE 'Nee' END AS is_cancelled_label,
    CASE WHEN a.members_only THEN 'Ja' ELSE 'Nee' END AS members_only_label,
    d.first_date,
    d.last_date,
    d.last_date                                 AS date_key,
    EXTRACT(YEAR FROM d.first_date)::int        AS activity_year,
    a.created_at
FROM activities.activities a
LEFT JOIN LATERAL (
    SELECT MIN(ad.start_date) AS first_date,
           MAX(COALESCE(ad.end_date, ad.start_date)) AS last_date
    FROM activities.activity_dates ad
    WHERE ad.activity_id = a.id AND ad.deleted_at IS NULL
) d ON TRUE
WHERE a.deleted_at IS NULL
"""

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
    (COALESCE(pay.amount_charged, 0) - COALESCE(pay.amount_paid, 0))::numeric(12, 2) AS open_amount
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
    ))                                          AS is_valid_today
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
    COALESCE(mshp.member_id, reghh.member_id)   AS member_id,
    mshp.year                                   AS membership_year,
    COALESCE(r.structured_communication, '')    AS structured_communication,
    COALESCE(r.note, '')                        AS note,
    CASE
        WHEN r.payable_type = 'registration' THEN
            COALESCE(
                NULLIF(TRIM(BOTH ' —' FROM
                    COALESCE(reg.contact_name, '') || ' — ' || COALESCE(act.name, '')),
                    ''),
                'Inschrijving #' || r.payable_id::text)
        WHEN r.payable_type = 'membership' THEN
            NULLIF(TRIM(BOTH ' —' FROM
                COALESCE(hoofd.naam, '') || ' — Lidmaatschap ' ||
                COALESCE(mshp.year::text, '')), '')
        ELSE r.payable_type || ' #' || r.payable_id::text
    END                                         AS payable_label
FROM payment.payment_records r
LEFT JOIN activities.registrations reg
       ON r.payable_type = 'registration' AND reg.id = r.payable_id
      AND reg.tenant_id = r.tenant_id
LEFT JOIN activities.activities act
       ON act.id = reg.activity_id AND act.tenant_id = r.tenant_id
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
LEFT JOIN LATERAL (
    SELECT (p.first_name || ' ' || p.last_name) AS naam
    FROM mdm.member_persons mp
    JOIN mdm.persons p ON p.id = mp.person_id
    WHERE mp.member_id = mshp.member_id AND mp.relation_type = 'HOOFDLID'
    ORDER BY mp.id
    LIMIT 1
) hoofd ON TRUE
WHERE r.deleted_at IS NULL
"""

D_PERSON_MEMBER = """
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
    mp.member_id
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

COMMENTS = {
    "d_member": (
        "Gezin (Member in het model), een rij per gezin. Heette tot #848 "
        "`d_household`; twee namen voor hetzelfde ding laten iemand twijfelen of "
        "het over hetzelfde gaat. Soft-deleted gezinnen uitgesloten. Adres = dat "
        "van het hoofdlid, anders van het eerste gezinslid."
    ),
    "f_members": (
        "Feit gezin, een rij per gezin — ook een gezin dat nooit lid was. Dat is "
        "het verschil met f_memberships, dat alleen gezinnen kent die ooit een "
        "lidmaatschap hadden. Soft-deleted gezinnen uitgesloten."
    ),
    "f_activities": (
        "Feit activiteit, een rij per activiteit — ook een activiteit zonder "
        "inschrijvingen. `last_date` is de laatste dag (einddatum, anders "
        "begindatum) en maakt 'komende activiteiten' beantwoordbaar. "
        "Soft-deleted activiteiten en datumrijen uitgesloten."
    ),
    # A DROP takes the comment with it, so the four views that only changed a
    # column name have to say again what they exclude. The schema gate caught this
    # — it exists for exactly the assumption "the comment is still there".
    "d_person": (
        "Persoon, een rij per persoon. Soft-deleted en samengevoegde personen "
        "uitgesloten. Leeftijdsgroep = de leeftijd vandaag. Draagt sinds CR-06 "
        "§7.3 (10 september 2026) persoonsgegevens waar de universe ze nodig "
        "heeft; de grens ligt bij de rol die het scherm bereikt."
    ),
    "f_memberships": (
        "Feit lidmaatschap, een rij per gezin per jaar waarin dat gezin lid was of "
        "het jaar ervoor lid was. Soft-deleted lidmaatschappen uitgesloten. Een "
        "rij met status LAPSED heeft geen lidmaatschap: haar maten zijn 0. "
        "`active_membership_count` telt lidmaatschapsRIJEN die op actief staan — "
        "`is_member` telt gezinnen en negeert die vlag."
    ),
    "f_membership_persons": (
        "Feit lid-persoon, een rij per persoon per lidmaatschapsjaar. Een persoon "
        "in twee gezinnen telt één keer, onder het laagste gezin. Soft-deleted "
        "lidmaatschappen, gezinskoppelingen en personen uitgesloten, net als "
        "samengevoegde personen. `is_valid_today` vraagt of de PERSOON vandaag "
        "een geldig lidmaatschap heeft — een andere vraag dan 'lid voor dit jaar'."
    ),
    "f_payments": (
        "Feit betaling, een rij per betaalrecord (vordering én terugbetaling; een "
        "terugbetaling draagt een negatief bedrag). Soft-deleted betalingen "
        "uitgesloten — maar de verrijking (activiteit, gezin, `payable_label`) "
        "reikt BEWUST door soft-deleted inschrijvingen en lidmaatschappen heen: "
        "een betaling is een financieel feit en blijft staan als datgene waarvoor "
        "betaald werd verdwijnt. `payable_label` draagt een persoonsnaam; dat mag "
        "sinds CR-06 §7.3 en wordt begrensd door de rol die het scherm bereikt."
    ),
}


def upgrade() -> None:
    # The dimension first, then everything that points at it: dropping a view that
    # others select from needs CASCADE, and re-creating in dependency order keeps
    # the chain honest on a fresh database.
    for naam in ("d_household", "f_memberships", "f_membership_persons",
                 "f_payments", "d_person"):
        op.execute(f"DROP VIEW IF EXISTS reporting.{naam} CASCADE")

    op.execute(D_MEMBER)
    op.execute(D_PERSON_MEMBER)
    op.execute(F_MEMBERS)
    op.execute(F_ACTIVITIES)
    op.execute(F_MEMBERSHIPS)
    op.execute(F_MEMBERSHIP_PERSONS)
    op.execute(F_PAYMENTS)

    for naam, tekst in COMMENTS.items():
        op.execute(f"COMMENT ON VIEW reporting.{naam} IS "
                   f"'{tekst.replace(chr(39), chr(39) * 2)}'")

    # Saved reports that point at the renamed keys. Only rows that still carry the
    # old ones, so a report a board member already adjusted is left alone.
    bind = op.get_bind()
    for oud, nieuw in (("household_municipality", "member_municipality"),
                       ("household_postal_code", "member_postal_code"),
                       ("household_size_group", "member_size_group"),
                       ("household_member_since", "member_since"),
                       ("\"household\"", "\"member\"")):
        bind.execute(
            sa.text("UPDATE reporting.saved_reports "
                    "SET selection = CAST(REPLACE(selection::text, :oud, :nieuw) AS json) "
                    "WHERE selection::text LIKE :patroon"),
            {"oud": oud, "nieuw": nieuw, "patroon": f"%{oud}%"})


def downgrade() -> None:
    for naam in ("f_members", "f_activities", "d_member"):
        op.execute(f"DROP VIEW IF EXISTS reporting.{naam} CASCADE")
