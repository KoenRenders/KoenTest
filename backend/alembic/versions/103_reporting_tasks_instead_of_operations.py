"""Reporting: `f_operations` becomes `f_tasks`, with every task and status as a
dimension (#841, decided by Koen 10 September 2026).

**The name was a promise about scope.** `f_operations` promised work, mails and
payments, and since migration 102 it is only the workbench. Somebody reading that
name in half a year concludes the mail leg belongs there and puts it back — which
is exactly the mistake that produced the union in the first place: the issue named
three *kinds* of open item and it was read as three tables.

**And it filtered `status = 'open'`, which made the fact lie about itself.** A fact
called "tasks" that silently holds only the open ones cannot answer "how many did
we finish last month". With status as a dimension, "open" becomes a filter — the
same rows, one condition less in the view, one dimension more — and a question
opens that could not be asked before: *are we working the queue down or is it
growing?*

`done_at` and `done_by` were already on the task, so the time it took and who
closed it come along for free. `done_by` is an e-mail address; it is declared
`member_details` like every other person-level field, allowed in the universe
since CR-06 §7.3 and bounded by the role that reaches the screen.

Two shapes are copied from `f_payments` deliberately, because a reader who knows
one should not have to learn the other:

- `age_days` and `age_bucket` describe **waiting**, so they are null and
  "Afgehandeld" for a task that is done — the same way an ageing bucket reads
  "Betaald" for a settled payment.
- `days_to_done` is the counterpart of `days_to_paid`.

The seeded report "Wat vraagt nu aandacht" is rewritten to the new keys and gains
the status filter it used to get for free. That filter being **visible in the
saved report** rather than baked into the fact is the point: the dashboard tile
"Open taken" reads the same rows through the same visible condition (#848).
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "103"
down_revision = "102"
branch_labels = None
depends_on = None


F_TASKS = """
CREATE OR REPLACE VIEW reporting.f_tasks AS
SELECT
    t.tenant_id,
    t.kind,
    CASE t.kind
        WHEN 'payment.refund_bevestigen' THEN 'Terugbetaling bevestigen'
        WHEN 'mail.definitief_gefaald'   THEN 'E-mail definitief mislukt'
        WHEN 'payment.webhook_mismatch'  THEN 'Webhook wijkt af van het grootboek'
        WHEN 'kernel.job_gefaald'        THEN 'Achtergrondtaak mislukt'
        WHEN 'bericht.behartigen'        THEN 'Bericht behartigen'
        ELSE t.kind
    END                                         AS kind_label,
    t.status,
    CASE t.status
        WHEN 'open' THEN 'Open'
        WHEN 'done' THEN 'Afgehandeld'
        ELSE t.status
    END                                         AS status_label,
    t.subject_type                              AS detail,
    t.subject_type,
    t.subject_id::text                          AS subject_id,
    t.id::text                                  AS item_id,
    t.required_role,
    COALESCE(t.done_by, '')                     AS done_by,
    t.created_at,
    t.created_at::date                          AS date_key,
    t.done_at,
    t.done_at::date                             AS done_date,
    -- Ageing is about WAITING, so a finished task has none — the same shape as
    -- `open_days` and the "Betaald" bucket on f_payments.
    CASE WHEN t.status <> 'done'
         THEN (CURRENT_DATE - t.created_at::date) END AS age_days,
    CASE WHEN t.done_at IS NOT NULL
         THEN (t.done_at::date - t.created_at::date) END AS days_to_done,
    CASE
        WHEN t.status = 'done' THEN 'Afgehandeld'
        WHEN CURRENT_DATE - t.created_at::date <= 7 THEN '0-7 dagen'
        WHEN CURRENT_DATE - t.created_at::date <= 30 THEN '8-30 dagen'
        WHEN CURRENT_DATE - t.created_at::date <= 90 THEN '31-90 dagen'
        ELSE 'meer dan 90 dagen'
    END                                         AS age_bucket
FROM workflow.workflow_tasks t
"""

COMMENT = (
    "Feit taak, een rij per werkbanktaak — open én afgehandeld, met de status als "
    "dimensie. Bewust geen unie over werkbank, maillog en betalingen (die stond "
    "in migratie 098 en telde hetzelfde probleem twee keer: een definitief "
    "mislukte e-mail en een te bevestigen terugbetaling zijn taaksoorten). "
    "`workflow.workflow_tasks` kent geen soft delete. Ouderdom wordt tegen "
    "CURRENT_DATE gemeten en geldt alleen voor wat nog wacht."
)

# The saved report keeps its name and its question; only the keys it points at
# change, and the status condition it used to get from the view becomes visible.
OPERATIONS_NOW = {
    "objects": ["task_kind", "task_age_bucket", "task_count", "task_age_days"],
    "filters": [{"object": "task_status", "operator": "eq", "values": ["Open"]}],
    "sort": [{"object": "task_count", "direction": "desc"}],
    "layout": "table",
    "pivot_column": "",
}


def upgrade() -> None:
    op.execute(F_TASKS)
    op.execute(f"COMMENT ON VIEW reporting.f_tasks IS '{COMMENT}'")
    op.execute("DROP VIEW IF EXISTS reporting.f_operations CASCADE")

    # Repoint the shipped report. Only the rows that still carry the old keys, so
    # a report a board member already adjusted is left alone.
    op.get_bind().execute(
        sa.text(
            "UPDATE reporting.saved_reports SET selection = CAST(:s AS json) "
            "WHERE builtin_key = 'operations_now' "
            "  AND selection::text LIKE '%operation_%'"
        ),
        {"s": json.dumps(OPERATIONS_NOW)},
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS reporting.f_tasks CASCADE")
