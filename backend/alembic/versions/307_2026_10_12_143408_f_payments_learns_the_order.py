"""f_payments learns the order (CR-21, phase 2)

The payment report's view joins a third payable: a webshop order. The order's
buyer is a guest name or the person of the order, its household the person's —
and the label reads "Bestelling". The registration and membership rows are
unchanged: the same CASE branches, the same joins, one more left join that a
registration or membership row never touches.
"""

from alembic import op

# The id is a timestamp, not a sequence number (#951). The number at the front
# of the FILE NAME is for readability only — alembic ignores it; the head is
# what `alembic heads` says.
revision = "307_2026_10_12_143408"
down_revision = "306_2026_10_12_123500"
branch_labels = None
depends_on = None

F_PAYMENTS_WITH_ORDER = """
CREATE OR REPLACE VIEW reporting.f_payments AS
SELECT
    r.tenant_id,
    r.id                                        AS payment_id,
    r.payable_type,
    CASE r.payable_type
        WHEN 'registration' THEN 'Activiteit'
        WHEN 'membership' THEN 'Lidgeld'
        WHEN 'order' THEN 'Bestelling'
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
    COALESCE(mshp.member_id, reghh.member_id, sohh.member_id) AS member_id,
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
        WHEN r.payable_type = 'order' THEN
            NULLIF(TRIM(BOTH ' —' FROM
                COALESCE(so.guest_name, koper.naam, '') || ' — Bestelling ' || so.id::text), '')
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
LEFT JOIN sales.sales_orders so
       ON r.payable_type = 'order' AND so.id = r.payable_id
      AND so.tenant_id = r.tenant_id
LEFT JOIN LATERAL (
    SELECT mp.member_id
    FROM mdm.member_persons mp
    WHERE mp.person_id = so.person_id AND mp.deleted_at IS NULL
    ORDER BY (mp.relation_type = 'HOOFDLID') DESC, mp.id
    LIMIT 1
) sohh ON TRUE
LEFT JOIN LATERAL (
    SELECT (p.first_name || ' ' || p.last_name) AS naam
    FROM mdm.persons p
    WHERE p.id = so.person_id AND p.deleted_at IS NULL
    LIMIT 1
) koper ON TRUE
WHERE r.deleted_at IS NULL
"""

# The view as it stood before the order join (migration 106), for the downgrade.
F_PAYMENTS_BEFORE = """
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


def upgrade() -> None:
    op.execute(F_PAYMENTS_WITH_ORDER)


def downgrade() -> None:
    op.execute(F_PAYMENTS_BEFORE)
