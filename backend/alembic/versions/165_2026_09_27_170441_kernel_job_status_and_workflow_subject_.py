"""kernel job status and workflow subject type become code lists

CR-12 phase 4 residue (#1181), found when phase 5 (#1182) measured its
precondition: three columns stored our own vocabulary without a key.

- `kernel_jobs.status` — the scheduler writes four values and the workbench
  turns a failed job into a task. A code list in `public`, next to the table.
- `workflow_tasks.subject_type` and `workflow_instances.subject_type` — one
  list, the four subjects our handlers name; the workbench branches on them.
- `workflow_instances.definition_code` — its table already exists
  (`workflow_definitions.code` is the primary key), so it gets only the key.

Every key is preceded by a count of the rows it would refuse, and the
migration stops naming them instead of failing on the constraint.
`scripts/cr12-preflight.sql` asks the same question read-only, before the
deploy.

No data change. The downgrade removes the keys and the new tables; it has no
data to restore.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.workflow.codes import SUBJECT_TYPE_CODES
from app.kernel.codes import create_code_list
from app.kernel.jobs import JOB_STATUS_CODES


# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
revision = '165_2026_09_27_170441'
down_revision = '164_2026_09_27_152744'
branch_labels = None
depends_on = None


DEFINITION_FK = "fk_workflow_instances_definition_code"


def upgrade() -> None:
    create_code_list(op, schema="public", name="kernel_job_status",
                     codes=JOB_STATUS_CODES, fk_from=("public.kernel_jobs.status",),
                     code_length=10)
    create_code_list(op, schema="workflow", name="subject_type",
                     codes=SUBJECT_TYPE_CODES,
                     fk_from=("workflow.workflow_tasks.subject_type",
                              "workflow.workflow_instances.subject_type"))

    bind = op.get_bind()
    existing = {fk["name"] for fk in sa.inspect(bind).get_foreign_keys(
        "workflow_instances", schema="workflow")}
    if DEFINITION_FK not in existing:
        stray = bind.execute(sa.text(
            "SELECT definition_code AS value, count(*) AS n FROM workflow.workflow_instances "
            "WHERE definition_code NOT IN (SELECT code FROM workflow.workflow_definitions) "
            "GROUP BY definition_code ORDER BY n DESC")).all()
        if stray:
            found = ", ".join(f"{row.value!r}x{row.n}" for row in stray)
            raise RuntimeError(
                f"workflow.workflow_instances.definition_code names definitions that do "
                f"not exist: {found}. The foreign key would fail on these rows.")
        op.create_foreign_key(DEFINITION_FK, "workflow_instances", "workflow_definitions",
                              ["definition_code"], ["code"],
                              source_schema="workflow", referent_schema="workflow")


def downgrade() -> None:
    # Schema only: this migration wrote no data.
    op.drop_constraint(DEFINITION_FK, "workflow_instances", schema="workflow",
                       type_="foreignkey")
    for table in ("workflow_tasks", "workflow_instances"):
        op.drop_constraint(f"fk_{table}_subject_type_code", table, schema="workflow",
                           type_="foreignkey")
    op.drop_table("subject_type_labels", schema="workflow")
    op.drop_table("subject_type_codes", schema="workflow")
    op.drop_constraint("fk_kernel_jobs_status_code", "kernel_jobs", type_="foreignkey")
    op.drop_table("kernel_job_status_labels")
    op.drop_table("kernel_job_status_codes")
