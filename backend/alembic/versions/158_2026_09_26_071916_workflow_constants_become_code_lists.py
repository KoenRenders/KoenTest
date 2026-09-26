"""workflow constants become code lists

CR-12 phase 4, the workflow domain. Three stored lists — the task status, the
run status and the task kind — and one **derived** list, the category of a
kind.

The category is the part before the dot in `payment.webhook_mismatch`. It is
computed and never stored, so it gets a code table and labels but **no column
and no foreign key** (§B5.3 note 5). That is what lets `CAT_LABELS` disappear
from `workflow/ui.py` while the workbench still heads its group *Betalingen*
instead of `payment`.

The price of a derived list is that the foreign key cannot guarantee
completeness: add a kind in a category that has no row and `code_label()`
falls back to the code. `tests/test_codes_phase4.py` carries the test that
closes that gap.

No data change: every value these three columns hold is already one of the
codes, and the helper counts the rows before it adds each key.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.workflow.codes import (
    RUN_STATUS_CODES,
    TASK_CATEGORY_CODES,
    TASK_KIND_CODES,
    TASK_STATUS_CODES,
)
from app.kernel.codes import create_code_list


# The id is a timestamp, not a sequence number (#951).
revision = '158_2026_09_26_071916'
down_revision = '157_2026_09_26_052050'
branch_labels = None
depends_on = None

LISTS = (
    ("task_status", TASK_STATUS_CODES, 10, "workflow.workflow_tasks.status"),
    ("run_status", RUN_STATUS_CODES, 10, "workflow.workflow_instances.status"),
    ("task_kind", TASK_KIND_CODES, 100, "workflow.workflow_tasks.kind"),
    # Derived: no storing column, so no foreign key (§B5.3 note 5).
    ("task_category", TASK_CATEGORY_CODES, 50, None),
)


def upgrade() -> None:
    for name, codes, length, column in LISTS:
        create_code_list(op, schema="workflow", name=name, codes=codes,
                         fk_from=(column,) if column else (), code_length=length)


def downgrade() -> None:
    # Schema only: this migration wrote no task data and changed no existing
    # value.
    for name, _codes, _length, column in LISTS:
        if column:
            _schema, table, column_name = column.split(".")
            op.drop_constraint(f"fk_{table}_{column_name}_code", table,
                               schema="workflow", type_="foreignkey")
        op.drop_table(f"{name}_labels", schema="workflow")
        op.drop_table(f"{name}_codes", schema="workflow")
