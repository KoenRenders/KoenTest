"""The two Design Studio media kinds (#1005, CR-10 §3.11).

`design_image` is the picture that goes INTO a poster; `design_render` is the
rendered poster of one version.

**The issue expected no migration** — `kind` is a string column. Measured while
building: there is a CHECK on that column (`ck_media_assets_kind_valid`, added
in 040 and widened in 057, 123 and 131), so a new kind without a migration ends
in a CheckViolation on the first upload. Hence this one; it is the same
widening those three did.

Idempotent: the constraint is rebuilt from the full list, so running it twice
leaves the same state.
"""
from alembic import op

revision = "134_2026_09_18_145500"
down_revision = "133_2026_09_18_141900"
branch_labels = None
depends_on = None

_KINDS_NEW = ("kind IN ('sponsor','activity_photo','activity_poster',"
              "'component_info','tenant_logo','newsletter_file',"
              "'design_image','design_render')")
_KINDS_OLD = ("kind IN ('sponsor','activity_photo','activity_poster',"
              "'component_info','tenant_logo','newsletter_file')")


def _herbouw(voorwaarde: str) -> None:
    op.drop_constraint("ck_media_assets_kind_valid", "media_assets",
                       type_="check", schema="media")
    op.create_check_constraint("ck_media_assets_kind_valid", "media_assets",
                               voorwaarde, schema="media")


def upgrade() -> None:
    _herbouw(_KINDS_NEW)


def downgrade() -> None:
    # The design media go: the old CHECK would refuse them, and a poster version
    # without its render is not a poster. That is what a downgrade costs.
    op.execute("DELETE FROM media.media_assets "
               "WHERE kind IN ('design_image','design_render')")
    _herbouw(_KINDS_OLD)
