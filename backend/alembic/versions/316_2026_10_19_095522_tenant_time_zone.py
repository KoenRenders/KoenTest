"""a time zone per tenant; "today" and "the day of a moment" are the tenant's

#2156. Between midnight in Belgium and midnight UTC the application (Brussels) and
the database (`CURRENT_DATE`, UTC) disagreed on what day it is, so the dashboard and
the member list, or a saved report and its button, fell on different days. Koen
(19 October 2026, "Ja", to the master CLI): a time zone per tenant, Brussels by
default; timestamps stay UTC, the day is the tenant's.

- **`mdm.tenants.time_zone`** — an IANA name, `NOT NULL DEFAULT 'Europe/Brussels'`:
  every tenant has a zone, as a fact of the database (the architecture CLI's reading).
- **`mdm.tenant_today(tenant_id)`** and **`mdm.tenant_day(tenant_id, moment)`** — the
  one place SQL asks which day it is, and which day a moment belongs to. The
  application's `kernel.clock` reads the same column; the day is decided in two
  languages from one setting.
- **The six reporting views** that read the database's `CURRENT_DATE` (`d_date`,
  `d_person`, `f_members`, `f_membership_persons`, `f_payments`, `f_tasks`) are replaced
  in place, with the same columns: `CURRENT_DATE` becomes `mdm.tenant_today(<their
  tenant>)`. So do the `moment::date` casts they mixed with it (`created_at`, `paid_at`,
  `done_at`): a cast in the UTC session names the UTC day, and an age is a difference of
  two days that must be the same kind of day. The only rows whose numbers move are the
  moments between midnight in Brussels and midnight UTC.

Not reversible in one step, like 314 and 315 under it (B4: the dump is the way back).
"""

from alembic import op

# The id is a timestamp, not a sequence number (#951).
revision = "316_2026_10_19_095522"
down_revision = "315_2026_10_19_051425"
branch_labels = None
depends_on = None

D_DATE = """
    CREATE OR REPLACE VIEW reporting.d_date AS
SELECT t.id AS tenant_id,
    d.day::date AS date_key,
    EXTRACT(year FROM d.day)::integer AS year,
    EXTRACT(quarter FROM d.day)::integer AS quarter,
    EXTRACT(month FROM d.day)::integer AS month,
    to_char(d.day, 'YYYY-MM'::text) AS year_month,
        CASE EXTRACT(month FROM d.day)::integer
            WHEN 1 THEN 'januari'::text
            WHEN 2 THEN 'februari'::text
            WHEN 3 THEN 'maart'::text
            WHEN 4 THEN 'april'::text
            WHEN 5 THEN 'mei'::text
            WHEN 6 THEN 'juni'::text
            WHEN 7 THEN 'juli'::text
            WHEN 8 THEN 'augustus'::text
            WHEN 9 THEN 'september'::text
            WHEN 10 THEN 'oktober'::text
            WHEN 11 THEN 'november'::text
            ELSE 'december'::text
        END AS month_label,
    (
        CASE EXTRACT(month FROM d.day)::integer
            WHEN 1 THEN 'januari'::text
            WHEN 2 THEN 'februari'::text
            WHEN 3 THEN 'maart'::text
            WHEN 4 THEN 'april'::text
            WHEN 5 THEN 'mei'::text
            WHEN 6 THEN 'juni'::text
            WHEN 7 THEN 'juli'::text
            WHEN 8 THEN 'augustus'::text
            WHEN 9 THEN 'september'::text
            WHEN 10 THEN 'oktober'::text
            WHEN 11 THEN 'november'::text
            ELSE 'december'::text
        END || ' '::text) || EXTRACT(year FROM d.day)::integer::text AS month_year_label
   FROM mdm.tenants t
     CROSS JOIN generate_series('2015-01-01'::date::timestamp with time zone, (mdm.tenant_today(t.id) + '2 years'::interval)::date::timestamp with time zone, '1 day'::interval) d(day)
  WHERE t.kind::text <> 'PLATFORM'::text
    """

D_PERSON = """
    CREATE OR REPLACE VIEW reporting.d_person AS
SELECT pt.tenant_id,
    p.id AS person_id,
    COALESCE(p.gender_code, 'X'::character varying) AS gender_code,
    COALESCE(gl.value, 'Onbekend'::character varying) AS gender_label,
    EXTRACT(year FROM p.date_of_birth)::integer AS birth_year,
        CASE
            WHEN p.date_of_birth IS NULL THEN 'Onbekend'::text
            WHEN date_part('year'::text, age(mdm.tenant_today(pt.tenant_id)::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 6::double precision THEN '0-5'::text
            WHEN date_part('year'::text, age(mdm.tenant_today(pt.tenant_id)::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 13::double precision THEN '6-12'::text
            WHEN date_part('year'::text, age(mdm.tenant_today(pt.tenant_id)::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 18::double precision THEN '13-17'::text
            WHEN date_part('year'::text, age(mdm.tenant_today(pt.tenant_id)::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 26::double precision THEN '18-25'::text
            WHEN date_part('year'::text, age(mdm.tenant_today(pt.tenant_id)::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 41::double precision THEN '26-40'::text
            WHEN date_part('year'::text, age(mdm.tenant_today(pt.tenant_id)::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 61::double precision THEN '41-60'::text
            WHEN date_part('year'::text, age(mdm.tenant_today(pt.tenant_id)::timestamp with time zone, p.date_of_birth::timestamp with time zone)) < 76::double precision THEN '61-75'::text
            ELSE '76 of ouder'::text
        END AS age_group,
    COALESCE(mp.relation_type, 'ONBEKEND'::character varying) AS relation_type_code,
    COALESCE(rl.value, mp.relation_type, 'Onbekend'::character varying) AS relation_type_label,
    mp.member_id,
    p.first_name,
    p.last_name,
    TRIM(BOTH FROM concat_ws(' '::text, p.first_name, p.last_name)) AS person_name
   FROM mdm.persons p
     JOIN mdm.person_tenants pt ON pt.person_id = p.id
     LEFT JOIN mdm.gender_labels gl ON gl.code::text = p.gender_code::text AND gl.language::text = 'nl'::text
     LEFT JOIN LATERAL ( SELECT mp2.member_id,
            mp2.relation_type
           FROM mdm.member_persons mp2
          WHERE mp2.person_id = p.id AND mp2.deleted_at IS NULL
          ORDER BY (mp2.relation_type::text = 'HOOFDLID'::text) DESC, mp2.id
         LIMIT 1) mp ON true
     LEFT JOIN mdm.relation_type_labels rl ON rl.code::text = mp.relation_type::text AND rl.language::text = 'nl'::text
  WHERE p.deleted_at IS NULL AND p.superseded_by_id IS NULL
    """

F_MEMBERS = """
    CREATE OR REPLACE VIEW reporting.f_members AS
SELECT t.tenant_id,
    m.id AS member_id,
    m.created_at,
    mdm.tenant_day(t.tenant_id, m.created_at) AS date_key,
    hoofd.person_id AS head_person_id,
    (EXISTS ( SELECT 1
           FROM membership.memberships ms
          WHERE ms.member_id = m.id AND ms.tenant_id = t.tenant_id AND ms.deleted_at IS NULL)) AS was_ever_member,
    (EXISTS ( SELECT 1
           FROM membership.memberships ms
          WHERE ms.member_id = m.id AND ms.tenant_id = t.tenant_id AND ms.deleted_at IS NULL AND ms.is_active AND ms.valid_from IS NOT NULL AND ms.valid_to IS NOT NULL AND mdm.tenant_today(t.tenant_id) >= ms.valid_from AND mdm.tenant_today(t.tenant_id) <= ms.valid_to)) AS is_valid_today
   FROM mdm.members m
     JOIN mdm.household_tenants t ON t.member_id = m.id
     LEFT JOIN LATERAL ( SELECT mp.person_id
           FROM mdm.member_persons mp
          WHERE mp.member_id = m.id AND mp.deleted_at IS NULL
          ORDER BY (mp.relation_type::text = 'HOOFDLID'::text) DESC, mp.id
         LIMIT 1) hoofd ON true
  WHERE m.deleted_at IS NULL
    """

F_MEMBERSHIP_PERSONS = """
    CREATE OR REPLACE VIEW reporting.f_membership_persons AS
SELECT DISTINCT ON (ms.tenant_id, mp.person_id, ms.year) ms.tenant_id,
    mp.person_id,
    ms.member_id,
    ms.year,
    ms.membership_id,
    (EXISTS ( SELECT 1
           FROM mdm.member_persons mp2
             JOIN membership.memberships v ON v.member_id = mp2.member_id AND v.deleted_at IS NULL
          WHERE mp2.person_id = mp.person_id AND mp2.deleted_at IS NULL AND v.tenant_id = ms.tenant_id AND v.is_active AND v.valid_from IS NOT NULL AND v.valid_to IS NOT NULL AND v.valid_from <= mdm.tenant_today(ms.tenant_id) AND mdm.tenant_today(ms.tenant_id) <= v.valid_to)) AS is_valid_today,
    make_date(ms.year, 1, 1) AS date_key
   FROM ( SELECT memberships.tenant_id,
            memberships.member_id,
            memberships.year,
            min(memberships.id) AS membership_id
           FROM membership.memberships
          WHERE memberships.deleted_at IS NULL
          GROUP BY memberships.tenant_id, memberships.member_id, memberships.year) ms
     JOIN mdm.member_persons mp ON mp.member_id = ms.member_id AND mp.deleted_at IS NULL
     JOIN mdm.persons p ON p.id = mp.person_id AND p.deleted_at IS NULL AND p.superseded_by_id IS NULL
  ORDER BY ms.tenant_id, mp.person_id, ms.year, ms.member_id
    """

F_PAYMENTS = """
    CREATE OR REPLACE VIEW reporting.f_payments AS
SELECT r.tenant_id,
    r.id AS payment_id,
    r.payable_type,
        CASE r.payable_type
            WHEN 'registration'::text THEN 'Activiteit'::character varying
            WHEN 'membership'::text THEN 'Lidgeld'::character varying
            WHEN 'order'::text THEN 'Bestelling'::character varying
            ELSE r.payable_type
        END AS payable_type_label,
    r.payable_id,
    r.type AS record_type,
        CASE r.type
            WHEN 'charge'::text THEN 'Vordering'::character varying
            WHEN 'refund'::text THEN 'Terugbetaling'::character varying
            ELSE r.type
        END AS record_type_label,
    r.method AS method_code,
    r.status AS status_code,
    r.amount::numeric(12,2) AS amount,
    COALESCE(r.amount_paid, 0::numeric)::numeric(12,2) AS amount_paid,
    (r.amount - COALESCE(r.amount_paid, 0::numeric))::numeric(12,2) AS open_amount,
        CASE
            WHEN r.status::text = 'paid'::text AND r.paid_at IS NOT NULL THEN mdm.tenant_day(r.tenant_id, r.paid_at) - mdm.tenant_day(r.tenant_id, r.created_at)
            ELSE NULL::integer
        END AS days_to_paid,
        CASE
            WHEN r.status::text <> 'paid'::text THEN mdm.tenant_today(r.tenant_id) - mdm.tenant_day(r.tenant_id, r.created_at)
            ELSE NULL::integer
        END AS open_days,
        CASE
            WHEN r.status::text = 'paid'::text THEN 'Betaald'::text
            WHEN (mdm.tenant_today(r.tenant_id) - mdm.tenant_day(r.tenant_id, r.created_at)) <= 30 THEN '0-30 dagen'::text
            WHEN (mdm.tenant_today(r.tenant_id) - mdm.tenant_day(r.tenant_id, r.created_at)) <= 60 THEN '31-60 dagen'::text
            WHEN (mdm.tenant_today(r.tenant_id) - mdm.tenant_day(r.tenant_id, r.created_at)) <= 90 THEN '61-90 dagen'::text
            ELSE 'meer dan 90 dagen'::text
        END AS age_bucket,
    r.created_at,
    mdm.tenant_day(r.tenant_id, r.created_at) AS date_key,
    mdm.tenant_day(r.tenant_id, r.paid_at) AS paid_date,
    reg.activity_id,
    reg.component_id,
    COALESCE(mshp.member_id, reghh.member_id, sohh.member_id) AS member_id,
    mshp.year AS membership_year,
    COALESCE(r.structured_communication, ''::character varying) AS structured_communication,
    COALESCE(r.note, ''::character varying) AS note,
        CASE
            WHEN r.payable_type::text = 'registration'::text THEN COALESCE(NULLIF(TRIM(BOTH ' —'::text FROM (COALESCE(reg.contact_name, ''::character varying)::text || ' — '::text) || COALESCE(act.name, ''::character varying)::text), ''::text), 'Inschrijving #'::text || r.payable_id::text)
            WHEN r.payable_type::text = 'membership'::text THEN NULLIF(TRIM(BOTH ' —'::text FROM (COALESCE(hoofd.naam, ''::text) || ' — Lidmaatschap '::text) || COALESCE(mshp.year::text, ''::text)), ''::text)
            WHEN r.payable_type::text = 'order'::text THEN NULLIF(TRIM(BOTH ' —'::text FROM (COALESCE(so.guest_name, koper.naam::character varying, ''::character varying)::text || ' — Bestelling '::text) || so.id::text), ''::text)
            ELSE (r.payable_type::text || ' #'::text) || r.payable_id::text
        END AS payable_label
   FROM payment.payment_records r
     LEFT JOIN activities.registrations reg ON r.payable_type::text = 'registration'::text AND reg.id = r.payable_id AND reg.tenant_id = r.tenant_id
     LEFT JOIN activities.activities act ON act.id = reg.activity_id AND act.tenant_id = r.tenant_id
     LEFT JOIN membership.memberships mshp ON r.payable_type::text = 'membership'::text AND mshp.id = r.payable_id AND mshp.tenant_id = r.tenant_id
     LEFT JOIN LATERAL ( SELECT mp.member_id
           FROM mdm.member_persons mp
          WHERE mp.person_id = reg.person_id AND mp.deleted_at IS NULL
          ORDER BY (mp.relation_type::text = 'HOOFDLID'::text) DESC, mp.id
         LIMIT 1) reghh ON true
     LEFT JOIN LATERAL ( SELECT (p.first_name::text || ' '::text) || p.last_name::text AS naam
           FROM mdm.member_persons mp
             JOIN mdm.persons p ON p.id = mp.person_id
          WHERE mp.member_id = mshp.member_id AND mp.relation_type::text = 'HOOFDLID'::text
          ORDER BY mp.id
         LIMIT 1) hoofd ON true
     LEFT JOIN sales.sales_orders so ON r.payable_type::text = 'order'::text AND so.id = r.payable_id AND so.tenant_id = r.tenant_id
     LEFT JOIN LATERAL ( SELECT mp.member_id
           FROM mdm.member_persons mp
          WHERE mp.person_id = so.person_id AND mp.deleted_at IS NULL
          ORDER BY (mp.relation_type::text = 'HOOFDLID'::text) DESC, mp.id
         LIMIT 1) sohh ON true
     LEFT JOIN LATERAL ( SELECT (p.first_name::text || ' '::text) || p.last_name::text AS naam
           FROM mdm.persons p
          WHERE p.id = so.person_id AND p.deleted_at IS NULL
         LIMIT 1) koper ON true
  WHERE r.deleted_at IS NULL
    """

F_TASKS = """
    CREATE OR REPLACE VIEW reporting.f_tasks AS
SELECT tenant_id,
    kind,
        CASE kind
            WHEN 'payment.refund_bevestigen'::text THEN 'Terugbetaling bevestigen'::character varying
            WHEN 'mail.definitief_gefaald'::text THEN 'E-mail definitief mislukt'::character varying
            WHEN 'payment.webhook_mismatch'::text THEN 'Webhook wijkt af van het grootboek'::character varying
            WHEN 'kernel.job_gefaald'::text THEN 'Achtergrondtaak mislukt'::character varying
            WHEN 'bericht.behartigen'::text THEN 'Bericht behartigen'::character varying
            ELSE kind
        END AS kind_label,
    status,
        CASE status
            WHEN 'open'::text THEN 'Open'::character varying
            WHEN 'done'::text THEN 'Afgehandeld'::character varying
            ELSE status
        END AS status_label,
    subject_type AS detail,
    subject_type,
    subject_id::text AS subject_id,
    id::text AS item_id,
    required_role,
    COALESCE(done_by, ''::character varying) AS done_by,
    created_at,
    mdm.tenant_day(tenant_id, created_at) AS date_key,
    done_at,
    mdm.tenant_day(tenant_id, done_at) AS done_date,
        CASE
            WHEN status::text <> 'done'::text THEN mdm.tenant_today(tenant_id) - mdm.tenant_day(tenant_id, created_at)
            ELSE NULL::integer
        END AS age_days,
        CASE
            WHEN done_at IS NOT NULL THEN mdm.tenant_day(tenant_id, done_at) - mdm.tenant_day(tenant_id, created_at)
            ELSE NULL::integer
        END AS days_to_done,
        CASE
            WHEN status::text = 'done'::text THEN 'Afgehandeld'::text
            WHEN (mdm.tenant_today(tenant_id) - mdm.tenant_day(tenant_id, created_at)) <= 7 THEN '0-7 dagen'::text
            WHEN (mdm.tenant_today(tenant_id) - mdm.tenant_day(tenant_id, created_at)) <= 30 THEN '8-30 dagen'::text
            WHEN (mdm.tenant_today(tenant_id) - mdm.tenant_day(tenant_id, created_at)) <= 90 THEN '31-90 dagen'::text
            ELSE 'meer dan 90 dagen'::text
        END AS age_bucket
   FROM workflow.workflow_tasks t
    """


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE mdm.tenants
            ADD COLUMN time_zone VARCHAR(64) NOT NULL DEFAULT 'Europe/Brussels';

        CREATE FUNCTION mdm.tenant_day(tenant_id integer, moment timestamptz)
        RETURNS date
        LANGUAGE sql STABLE AS
        $$ SELECT (moment AT TIME ZONE t.time_zone)::date FROM mdm.tenants t WHERE t.id = tenant_id $$;

        CREATE FUNCTION mdm.tenant_today(tenant_id integer)
        RETURNS date
        LANGUAGE sql STABLE AS
        $$ SELECT mdm.tenant_day(tenant_id, now()) $$;

        COMMENT ON FUNCTION mdm.tenant_day(integer, timestamptz) IS
            'The day a moment belongs to in the tenant''s time zone (mdm.tenants.time_zone).';
        COMMENT ON FUNCTION mdm.tenant_today(integer) IS
            'Today in the tenant''s time zone: what kernel.clock says in the application, in SQL.';
        """
    )
    for view in (D_DATE, D_PERSON, F_MEMBERS, F_MEMBERSHIP_PERSONS, F_PAYMENTS, F_TASKS):
        op.execute(view)


def downgrade() -> None:
    # Not reversible in one step, like 314 and 315 under it: the way back is the dump
    # taken before the deploy (B4).
    raise NotImplementedError("#2156: restore the dump taken before the deploy")
