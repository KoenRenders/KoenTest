"""external number source becomes a code list

CR-12 phase 5 (#1182), the last entry of the last ratchet. Koen decided on 28
September 2026: `mdm.external_numbers.source` is our list, with one code today
(`ledenadministratie`). The unique key on (source, external_id) exists so that
a second source can come; that will be a row here, not a code change.

The key is a constraint of its own on `source`. It leaves the partial unique
index on (source, external_id) of migration 053 as it is.

Counted read-only before this was written, soft-deleted rows included: every
environment holds only `ledenadministratie`. The helper counts again before it
adds the key and stops naming any other value.

No data change.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.mdm.codes import EXTERNAL_SOURCE_CODES
from app.kernel.codes import create_code_list


# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
revision = '166_2026_09_28_043139'
down_revision = '165_2026_09_27_170441'
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_code_list(op, schema="mdm", name="external_source",
                     codes=EXTERNAL_SOURCE_CODES,
                     fk_from=("mdm.external_numbers.source",))


def downgrade() -> None:
    # Schema only: this migration wrote no data.
    op.drop_constraint("fk_external_numbers_source_code", "external_numbers",
                       schema="mdm", type_="foreignkey")
    op.drop_table("external_source_labels", schema="mdm")
    op.drop_table("external_source_codes", schema="mdm")
