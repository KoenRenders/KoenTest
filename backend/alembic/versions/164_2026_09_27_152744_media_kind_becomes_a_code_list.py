"""media kind becomes a code list

CR-12 phase 4, the media domain. `media.media_assets.kind` was a free string
guarded by `ck_media_assets_kind_valid` — the CHECK that migrations 057, 131, 134
and 151 each had to rebuild to add a kind. It gets its code list, a label table
per language and a foreign key; the CHECK goes, because the key says the same.

The helper counts the rows before it adds the key and aborts naming what does
not fit, so an environment holding a kind that is in neither list stops here
instead of losing it. `scripts/cr12-preflight.sql` asks the same question
read-only, before the deploy.

No data change.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.media.codes import MEDIA_KIND_CODES
from app.kernel.codes import create_code_list


# The id is a timestamp, not a sequence number (#951).
revision = '164_2026_09_27_152744'
down_revision = '163_2026_09_26_144116'
branch_labels = None
depends_on = None

#: What the CHECK said as of migration 151, for the downgrade.
KINDS_CHECK = ("kind IN ('sponsor','activity_photo','activity_poster',"
               "'component_info','tenant_logo','newsletter_file',"
               "'design_image','design_render','page_image')")


def upgrade() -> None:
    create_code_list(op, schema="media", name="media_kind", codes=MEDIA_KIND_CODES,
                     fk_from=("media.media_assets.kind",), code_length=20)
    existing = {c["name"] for c in sa.inspect(op.get_bind())
                .get_check_constraints("media_assets", schema="media")}
    if "ck_media_assets_kind_valid" in existing:
        op.drop_constraint("ck_media_assets_kind_valid", "media_assets",
                           schema="media", type_="check")


def downgrade() -> None:
    # Schema only: this migration wrote no media data.
    op.create_check_constraint("ck_media_assets_kind_valid", "media_assets",
                               KINDS_CHECK, schema="media")
    op.drop_constraint("fk_media_assets_kind_code", "media_assets",
                       schema="media", type_="foreignkey")
    op.drop_table("media_kind_labels", schema="media")
    op.drop_table("media_kind_codes", schema="media")
