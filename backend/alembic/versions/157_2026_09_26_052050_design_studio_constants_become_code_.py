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


# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '157_2026_09_26_052050'
down_revision = '156_2026_09_26_050603'
branch_labels = None
depends_on = None

LIJSTEN = (
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

#: Checks die hetzelfde zeggen als een nieuwe foreign key. `ck_design_focus` en
#: `ck_design_rendition_owner` staan er niet bij: die zeggen iets over twee
#: kolommen samen, en dat kan een lijst niet.
CHECKS = (("designs", "ck_design_status"),
          ("designs", "ck_design_preset"),
          ("designs", "ck_design_inset_corner"),
          ("design_renditions", "ck_design_rendition_layout"),
          ("design_renditions", "ck_design_rendition_variant"),
          ("image_generations", "ck_image_generation_status"))


def upgrade() -> None:
    for naam, codes, kolom in LIJSTEN:
        create_code_list(op, schema="designstudio", name=naam, codes=codes,
                         fk_from=(kolom,), code_length=20, value_length=200)

    inspecteur = sa.inspect(op.get_bind())
    for tabel, constraint in CHECKS:
        bestaand = {c["name"] for c in inspecteur.get_check_constraints(
            tabel, schema="designstudio")}
        if constraint in bestaand:
            op.drop_constraint(constraint, tabel, schema="designstudio",
                               type_="check")


def downgrade() -> None:
    # Schema only: geen ontwerpdata geschreven, geen bestaande waarde veranderd.
    for tabel, constraint, conditie in (
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
        op.create_check_constraint(constraint, tabel, conditie,
                                   schema="designstudio")
    for naam, _codes, kolom in LIJSTEN:
        _schema, tabel, kolomnaam = kolom.split(".")
        op.drop_constraint(f"fk_{tabel}_{kolomnaam}_code", tabel,
                           schema="designstudio", type_="foreignkey")
        op.drop_table(f"{naam}_labels", schema="designstudio")
        op.drop_table(f"{naam}_codes", schema="designstudio")
