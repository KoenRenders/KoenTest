"""A page image is a media kind of its own (#1173).

`page_image` is an image placed in the text of a CMS page — a screenshot on a
how-to page. It needs a kind of its own because it belongs to no activity and
because it is stored losslessly (lettering, see `LOSSLESS_KINDS`).

**The issue expected no migration**, and that is the second time for this exact
column: #1005 wrote the same sentence in migration 134. `media_assets.kind` looks
like a plain string column with a list in the code, but it carries a CHECK
(`ck_media_assets_kind_valid`, added in 040 and widened in 057, 123, 131 and
134). A new kind without this migration ends in a CheckViolation on the first
upload — measured, not reasoned: the picker tests failed on it.

So this is the same widening those four did, and nothing more.

Idempotent: the constraint is rebuilt from the full list, so running it twice
leaves the same state.
"""
from alembic import op


# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '151_2026_09_26_061026'
down_revision = '150_2026_09_21_224043'
branch_labels = None
depends_on = None

_KINDS_NEW = ("kind IN ('sponsor','activity_photo','activity_poster',"
              "'component_info','tenant_logo','newsletter_file',"
              "'design_image','design_render','page_image')")
_KINDS_OLD = ("kind IN ('sponsor','activity_photo','activity_poster',"
              "'component_info','tenant_logo','newsletter_file',"
              "'design_image','design_render')")


def _rebuild(condition: str) -> None:
    op.drop_constraint("ck_media_assets_kind_valid", "media_assets",
                       type_="check", schema="media")
    op.create_check_constraint("ck_media_assets_kind_valid", "media_assets",
                               condition, schema="media")


def upgrade() -> None:
    _rebuild(_KINDS_NEW)


def downgrade() -> None:
    # Data as well as schema, and it is a real loss: the page images go, because
    # the old CHECK would refuse them. A page that showed one keeps an <img> to a
    # media id that no longer resolves — the text stays, the picture 404s. That is
    # what this downgrade costs, and it is the same price migrations 131 and 134
    # pay for their kinds.
    op.execute("DELETE FROM media.media_assets WHERE kind = 'page_image'")
    _rebuild(_KINDS_OLD)
