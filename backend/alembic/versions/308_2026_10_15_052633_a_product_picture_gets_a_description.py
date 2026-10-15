"""a product picture gets a description

S1 of CR-21: a picture on an article gets a "Beschrijving" (the public page's
`alt`), a document gets a "Titel" (the link's text). Both live on the article's
own link to the file (`product_attachments`), not on the shared media file.
"""

import sqlalchemy as sa
from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
# `repr` with double quotes (#781): the generated file must already be what
# `ruff format` writes, or every new migration turns CI red. A `repr` still, not
# a bare string, because `down_revision` is a tuple for a merge and None for the
# first migration.
revision = "308_2026_10_15_052633"
down_revision = "307_2026_10_12_143408"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = [c["name"] for c in inspector.get_columns("product_attachments", schema="product")]
    if "description" not in columns:
        op.add_column(
            "product_attachments",
            sa.Column("description", sa.String(length=255), nullable=True),
            schema="product",
        )


def downgrade() -> None:
    # Drops the description column; the titles (already on the table) stay.
    inspector = sa.inspect(op.get_bind())
    columns = [c["name"] for c in inspector.get_columns("product_attachments", schema="product")]
    if "description" in columns:
        op.drop_column("product_attachments", "description", schema="product")
