"""export kind and history operation become code lists

CR-12 phase 4, the last two lists that need no decision about data.

- **`reporting.export_kind`**: what an export took out. The §B5.3 catalogue had
  two of the three codes; `ad-hoc` — every export that is not a saved report —
  was missing, and a key without it would have refused the most common export
  there is. The column had no CHECK.
- **`public.kernel_operation`**: insert, update or delete, as every `*_history`
  table records it. A code table and labels with **no key**: the history
  exemption of §B4.10 / F4. It lives in `public`, next to `kernel_jobs`,
  because every domain with a history table writes it.

No data change.
"""
from alembic import op

from app.domains.reporting.codes import EXPORT_KIND_CODES
from app.kernel.codes import create_code_list
from app.kernel.operations import OPERATION_CODES


# The id is a timestamp, not a sequence number (#951).
revision = '162_2026_09_26_131713'
down_revision = '161_2026_09_26_130003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_code_list(op, schema="reporting", name="export_kind",
                     codes=EXPORT_KIND_CODES,
                     fk_from=("reporting.export_log.kind",), code_length=20)
    create_code_list(op, schema="public", name="kernel_operation",
                     codes=OPERATION_CODES, code_length=10)


def downgrade() -> None:
    # Schema only: this migration wrote no export or history data.
    op.drop_constraint("fk_export_log_kind_code", "export_log",
                       schema="reporting", type_="foreignkey")
    op.drop_table("export_kind_labels", schema="reporting")
    op.drop_table("export_kind_codes", schema="reporting")
    op.drop_table("kernel_operation_labels", schema="public")
    op.drop_table("kernel_operation_codes", schema="public")
