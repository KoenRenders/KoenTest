"""Reporting phase 5 (#841 point 4): the payment columns a row list needs.

CR-06 §7.3 changed on 10 September 2026: person-level data is allowed in the
universe, bounded by the role that reaches the screen — `require_admin_ui`, the
same door as the member screens that already show these names. This migration is
the first thing that uses that room.

Three columns on `f_payments`, additive as CR-06 §4.1 requires — a column is added,
never renamed or removed:

- `payable_label` — what a payment was *for*, as the payments screen writes it:
  the registrant and the activity, or the head of the family and the membership
  year. This is the one that carries a name.
- `structured_communication` — the OGM on a transfer.
- `note` — what the treasurer wrote next to it.

**The label reaches through soft deletes on purpose**, exactly like
`payment.exports._enrich` does: a payment is a financial fact, and when the
registration behind it is removed the payment does not stop having been for
something. Showing "Inschrijving #41" where a name used to stand would make a
financial record unreadable for the person who has to reconcile it.
"""
from alembic import op

revision = "102"
down_revision = "101"
branch_labels = None
depends_on = None


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
    mshp.year                                   AS membership_year,
    COALESCE(r.structured_communication, '')    AS structured_communication,
    COALESCE(r.note, '')                        AS note,
    -- What this payment was for, written the way the payments screen writes it.
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

COMMENT = (
    "Feit betaling, een rij per betaalrecord (vordering én terugbetaling; een "
    "terugbetaling draagt een negatief bedrag). Soft-deleted betalingen "
    "uitgesloten — maar de verrijking (activiteit, gezin, `payable_label`) reikt "
    "BEWUST door soft-deleted inschrijvingen en lidmaatschappen heen: een betaling "
    "is een financieel feit en blijft in het feit staan als datgene waarvoor "
    "betaald werd verwijderd is. `payable_label` draagt een persoonsnaam; dat mag "
    "sinds CR-06 §7.3 (10 september 2026) en wordt begrensd door de rol die het "
    "scherm bereikt."
)


def upgrade() -> None:
    # CREATE OR REPLACE refuses a changed column list, and this adds three.
    op.execute("DROP VIEW IF EXISTS reporting.f_payments CASCADE")
    op.execute(F_PAYMENTS)
    op.execute(f"COMMENT ON VIEW reporting.f_payments IS '{COMMENT}'")


def downgrade() -> None:
    # Going back means re-creating the view as migration 096 left it; that is what
    # 096 is for, and re-running it is the honest way down.
    op.execute("DROP VIEW IF EXISTS reporting.f_payments CASCADE")
