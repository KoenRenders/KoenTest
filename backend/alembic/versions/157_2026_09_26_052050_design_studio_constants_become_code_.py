"""design studio constants become code lists

CR-12 phase 3, the design studio. Seven lists that were module constants.

**The brand assets are deliberately not among them** (§B4.10, and the issue
names them so it does not happen by accident): the icons, the colour duos, the
paper sizes and the template keys carry a *payload* — an SVG path, two
house-style colours, a filename part — and change with the house-style guide
rather than with a translator. They stay in `brand.py` and `icons.py`, and the
mappings that turn a layout into a filename (`FILE_LAYOUT_LABELS`,
`FILE_SIZE_LABELS`) stay too: they are not labels, whatever their name says.

Five `CHECK` constraints go with the new keys, for the reason this change
request has now met five times. Two checks stay, because they say something a
list cannot: `ck_design_rendition_owner` ties the variant to whether there is a
version, and `ck_design_focus` bounds two numbers.

No data change.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.designstudio.codes import (
    DESIGN_STATUS_CODES,
    DRAWING_STYLE_CODES,
    GENERATION_STATUS_CODES,
    INSET_CORNER_CODES,
    LAYOUT_CODES,
    PRESET_CODES,
    RENDER_VARIANT_CODES,
)
from app.kernel.codes import create_code_list


# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that are handed a
# timestamp cannot collide. The sequence number leads the FILE NAME, for
# reading and sorting — alembic does not look at it.
revision = '157_2026_09_26_052050'
down_revision = '156_2026_09_26_050603'
branch_labels = None
depends_on = None

LISTS = (
    ("design_status", DESIGN_STATUS_CODES, "designstudio.designs.status"),
    ("layout", LAYOUT_CODES, "designstudio.design_renditions.layout_code"),
    ("render_variant", RENDER_VARIANT_CODES,
     "designstudio.design_renditions.variant"),
    ("generation_status", GENERATION_STATUS_CODES,
     "designstudio.image_generations.status"),
    ("preset", PRESET_CODES, "designstudio.designs.preset"),
    ("inset_corner", INSET_CORNER_CODES, "designstudio.designs.inset_corner"),
    ("drawing_style", DRAWING_STYLE_CODES, "designstudio.image_generations.style"),
)

#: Checks that say the same as a new foreign key. `ck_design_focus` and
#: `ck_design_rendition_owner` are not among them: they say something about two
#: columns together, and a list cannot.
CHECKS = (("designs", "ck_design_status"),
          ("designs", "ck_design_preset"),
          ("designs", "ck_design_inset_corner"),
          ("design_renditions", "ck_design_rendition_layout"),
          ("design_renditions", "ck_design_rendition_variant"),
          ("image_generations", "ck_image_generation_status"))


def upgrade() -> None:
    for name, codes, column in LISTS:
        create_code_list(op, schema="designstudio", name=name, codes=codes,
                         fk_from=(column,), code_length=20, value_length=200)

    inspector = sa.inspect(op.get_bind())
    for table, constraint in CHECKS:
        existing = {c["name"] for c in inspector.get_check_constraints(
            table, schema="designstudio")}
        if constraint in existing:
            op.drop_constraint(constraint, table, schema="designstudio",
                               type_="check")


def downgrade() -> None:
    # Schema only: no design data written, no existing value changed.
    for table, constraint, condition in (
            ("designs", "ck_design_status", "status IN ('draft', 'final')"),
            ("designs", "ck_design_preset",
             "preset IN ('beeld', 'tekst', 'eenvoudig')"),
            ("designs", "ck_design_inset_corner",
             "inset_corner IN ('top_left', 'top_right', 'bottom_left', "
             "'bottom_right')"),
            ("design_renditions", "ck_design_rendition_layout",
             "layout_code IN ('print_a', 'feed_portrait')"),
            ("design_renditions", "ck_design_rendition_variant",
             "variant IN ('pdf', 'png', 'jpeg', 'svg', 'svg_edited')"),
            ("image_generations", "ck_image_generation_status",
             "status IN ('requested', 'fetched', 'picked', 'discarded', "
             "'refused', 'failed')")):
        op.create_check_constraint(constraint, table, condition,
                                   schema="designstudio")
    for name, _codes, column in LISTS:
        _schema, table, column_name = column.split(".")
        op.drop_constraint(f"fk_{table}_{column_name}_code", table,
                           schema="designstudio", type_="foreignkey")
        op.drop_table(f"{name}_labels", schema="designstudio")
        op.drop_table(f"{name}_codes", schema="designstudio")
