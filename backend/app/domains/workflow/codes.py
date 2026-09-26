"""The code lists the workflow domain owns (CR-12 phase 4).

Three stored lists and one **derived** one. The derived one is the category of
a task kind: `payment.webhook_mismatch` is in category `payment`, and that is
the part before the dot — computed, never stored, so it needs no column and no
foreign key. §B5.3 note 5 says a derived list is still a list with labels, and
that is exactly what is wanted here: the issue asks for `CAT_LABELS` to go, and
the group heading on the workbench still has to read *Betalingen* rather than
`payment`. One code table, labels per language, no storing column.
"""
from app.domains.workflow.models import (
    RunStatus,
    RunStatusCode,
    RunStatusLabel,
    TaskCategoryCode,
    TaskCategoryLabel,
    TaskKindCode,
    TaskKindLabel,
    TaskStatus,
    TaskStatusCode,
    TaskStatusLabel,
)
from app.kernel.codes import CodeList, CodeSeed

TASK_STATUS_CODES = (
    CodeSeed(code="open", nl="Open", en="Open", sort_order=10),
    CodeSeed(code="done", nl="Afgehandeld", en="Done", sort_order=20),
)

TASK_STATUS = CodeList(
    name="task_status", schema="workflow",
    codes=TaskStatusCode, labels=TaskStatusLabel, enum=TaskStatus,
    fk_from=("workflow.workflow_tasks.status",),
)

RUN_STATUS_CODES = (
    CodeSeed(code="running", nl="Bezig", en="Running", sort_order=10),
    CodeSeed(code="done", nl="Afgerond", en="Done", sort_order=20),
    CodeSeed(code="failed", nl="Mislukt", en="Failed", sort_order=30),
)

RUN_STATUS = CodeList(
    name="run_status", schema="workflow",
    codes=RunStatusCode, labels=RunStatusLabel, enum=RunStatus,
    fk_from=("workflow.workflow_instances.status",),
)

TASK_KIND_CODES = (
    CodeSeed(code="payment.webhook_mismatch",
             nl="Betaling: webhook wijkt af",
             en="Payment: webhook mismatch", sort_order=10),
    CodeSeed(code="payment.refund_bevestigen",
             nl="Betaling: terugbetaling bevestigen",
             en="Payment: confirm refund", sort_order=20),
    CodeSeed(code="mail.definitief_gefaald",
             nl="E-mail: definitief mislukt",
             en="E-mail: permanently failed", sort_order=30),
    CodeSeed(code="kernel.job_gefaald",
             nl="Achtergrondtaak mislukt",
             en="Background job failed", sort_order=40),
    # Not in the catalogue of §B5.3, and that is a finding of this phase: the
    # measurement looked for `kind="…"` in the code, and this kind comes from
    # DATA — the workflow definition `bericht` of migration 082 puts it in its
    # steps JSON, and migration 074 wrote rows with it. Exactly the case for
    # which this list gets no enum.
    CodeSeed(code="bericht.behartigen",
             nl="Bericht behartigen", en="Handle message", sort_order=50),
)

TASK_KIND = CodeList(
    name="task_kind", schema="workflow",
    codes=TaskKindCode, labels=TaskKindLabel,
    # No enum — see the constants in `models.py`. A workflow definition is
    # data and may introduce a kind; an enum column would refuse that row.
    enum=None,
    fk_from=("workflow.workflow_tasks.kind",),
)

#: The categories, derived from the codes above and never stored. No enum:
#: nothing in Python branches on a category — the workbench groups by it and
#: filters on a prefix, and both work on the string the kind already carries.
TASK_CATEGORY_CODES = (
    CodeSeed(code="payment", nl="Betalingen", en="Payments", sort_order=10),
    CodeSeed(code="mail", nl="E-mail", en="E-mail", sort_order=20),
    CodeSeed(code="kernel", nl="Systeem", en="System", sort_order=30),
    CodeSeed(code="bericht", nl="Berichten", en="Messages", sort_order=40),
)

TASK_CATEGORY = CodeList(
    name="task_category", schema="workflow",
    codes=TaskCategoryCode, labels=TaskCategoryLabel, enum=None,
    derived=True,
)
