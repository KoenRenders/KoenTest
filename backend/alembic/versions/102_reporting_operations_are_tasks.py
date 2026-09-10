"""Reporting: `f_operations` is the workbench, not a union of three tables (#841).

Migration 098 built this fact as a union over the workbench, the mail log and the
payments. That was wrong twice, and the second one is the worse of the two.

**It counted the same problem more than once.** The workbench sweep already turns
a definitively failed mail into a task (`mail.definitief_gefaald`), a pending
refund into a task (`payment.refund_bevestigen`) and a webhook mismatch into a
task (`payment.webhook_mismatch`). The three things #841 names as examples of an
open item are not three tables — they are three *kinds* of task. Reading them as
tables produced one row per problem in the task leg and a second row for the same
problem in the other leg.

**And its mail leg counted things that are not problems.** `status <> 'sent'`
includes `skipped` and `logged`, and `logged` is exactly what a tenant configured
to log instead of send does with every message it writes. On the test database
that is 223 `skipped` and 2 `logged` against 4 `sent`: a board member would have
been shown 225 "problems" on an afdeling that simply does not send mail.

So the fact becomes what the question asks for: **one row per open workbench
task**. The workbench is the visualisation of these tasks and this is the report
over the same rows, which is also why the "Open taken" tile and this report can
now be checked against each other (#848).

Dropping the payments leg is a second gain that was not sought: "open payments" in
a work queue duplicated question 6 of CR-06 §3 (*what is outstanding, and for how
long*). An unpaid membership fee is not a task for a person; it is a balance.

The consequence to know: the workbench is filled by a sweep. If it has not run,
this fact is empty while there are refunds waiting. That is the right behaviour —
the report then says what the tile and the workbench say, and three screens
silently agreeing beats one of them claiming something else.
"""
from alembic import op

revision = "102"
down_revision = "101"
branch_labels = None
depends_on = None


# The Dutch label per task kind, on one place. `#779` will move these to a code
# table; until then the view is that one place, exactly as in migration 096.
#
# A kind that is not in this list keeps its own name rather than becoming
# "Onbekend": a new task kind should read as itself in a report on the day it is
# added, not wait for a migration.
F_OPERATIONS = """
CREATE OR REPLACE VIEW reporting.f_operations AS
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
    t.subject_type                              AS detail,
    t.subject_type,
    t.subject_id::text                          AS subject_id,
    t.id::text                                  AS item_id,
    t.required_role,
    t.created_at,
    t.created_at::date                          AS date_key,
    (CURRENT_DATE - t.created_at::date)         AS age_days,
    CASE
        WHEN CURRENT_DATE - t.created_at::date <= 7 THEN '0-7 dagen'
        WHEN CURRENT_DATE - t.created_at::date <= 30 THEN '8-30 dagen'
        WHEN CURRENT_DATE - t.created_at::date <= 90 THEN '31-90 dagen'
        ELSE 'meer dan 90 dagen'
    END                                         AS age_bucket
FROM workflow.workflow_tasks t
WHERE t.status = 'open'
"""

COMMENT = (
    "Feit operaties, een rij per OPEN WERKBANKTAAK. Bewust geen unie meer over "
    "werkbank, maillog en betalingen (migratie 098): een definitief mislukte "
    "e-mail en een te bevestigen terugbetaling zijn taaksoorten en zaten er dus "
    "twee keer in. `workflow.workflow_tasks` kent geen soft delete. Ouderdom "
    "wordt tegen CURRENT_DATE gemeten, dus deze weergave antwoordt morgen anders "
    "— dat is de bedoeling van een werkvoorraad."
)


def upgrade() -> None:
    # DROP first: the column list changes (the union's `kind_label` values and the
    # `required_role` column are new), and CREATE OR REPLACE refuses that.
    op.execute("DROP VIEW IF EXISTS reporting.f_operations CASCADE")
    op.execute(F_OPERATIONS)
    op.execute(f"COMMENT ON VIEW reporting.f_operations IS '{COMMENT}'")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS reporting.f_operations CASCADE")
