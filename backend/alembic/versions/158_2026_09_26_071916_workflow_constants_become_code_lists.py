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


# De id is een tijdstempel en geen volgnummer (#951).
revision = '158_2026_09_26_071916'
down_revision = '157_2026_09_26_052050'
branch_labels = None
depends_on = None

LIJSTEN = (
    ("task_status", TASK_STATUS_CODES, 10, "workflow.workflow_tasks.status"),
    ("run_status", RUN_STATUS_CODES, 10, "workflow.workflow_instances.status"),
    ("task_kind", TASK_KIND_CODES, 100, "workflow.workflow_tasks.kind"),
    # Afgeleid: geen opslagkolom, dus geen foreign key (§B5.3 noot 5).
    ("task_category", TASK_CATEGORY_CODES, 50, None),
)


def upgrade() -> None:
    for naam, codes, lengte, kolom in LIJSTEN:
        create_code_list(op, schema="workflow", name=naam, codes=codes,
                         fk_from=(kolom,) if kolom else (), code_length=lengte)


def downgrade() -> None:
    # Alleen schema: deze migratie schreef geen taakdata en veranderde geen
    # bestaande waarde.
    for naam, _codes, _lengte, kolom in LIJSTEN:
        if kolom:
            _schema, tabel, kolomnaam = kolom.split(".")
            op.drop_constraint(f"fk_{tabel}_{kolomnaam}_code", tabel,
                               schema="workflow", type_="foreignkey")
        op.drop_table(f"{naam}_labels", schema="workflow")
        op.drop_table(f"{naam}_codes", schema="workflow")
