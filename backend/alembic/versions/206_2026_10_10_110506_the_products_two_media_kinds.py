"""The product's two media kinds (CR-21, phase 1).

Why this exists: a product shows pictures and documents (R3) that live in the
media library. `product_photo` is a picture, re-encoded like every upload;
`product_document` is a size chart or the like, kept lossless. Neither is a
library kind — they are added on the article itself and never appear in the
library's tree or the picker (Koen, 10 October 2026: "a").

The suite stays green without this migration: migration 164 reads
`MEDIA_KIND_CODES` from the code, so a fresh database already gets the two rows
at 164. Only a database that existed before fails, with a foreign-key violation
on the first upload — so this upsert is checked by reading, and by one step down
and up on a database that stood at the parent revision.
"""

from alembic import op

from app.domains.media.codes import MEDIA_KIND_CODES
from app.kernel.codes import create_code_list

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: the head is what `alembic heads` says.
revision = "206_2026_10_10_110506"
down_revision = "205_2026_10_10_105206"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: the rows are upserted, the tables and the foreign key already
    # exist from migration 164 and are left alone.
    create_code_list(
        op,
        schema="media",
        name="media_kind",
        codes=MEDIA_KIND_CODES,
        fk_from=("media.media_assets.kind",),
        code_length=20,
    )


def downgrade() -> None:
    # Schema and data: the two new kinds go, and any row that stored them. This
    # migration added nothing else.
    op.execute(
        "DELETE FROM media.media_kind_labels WHERE code IN ('product_photo', 'product_document')"
    )
    op.execute(
        "DELETE FROM media.media_kind_codes WHERE code IN ('product_photo', 'product_document')"
    )
