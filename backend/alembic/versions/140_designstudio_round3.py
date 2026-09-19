"""Design Studio, Koen's HDEV round 3 (19 September 2026, #1007).

"We zijn te fel doorgeslagen": eight design-text columns go — the deviating
title, the line breaks, the recurrence line, the price, the welcome line,
the kicker tick, practical and programme. What stays on the design is the
colour duo, the preset, the subtitle bar, the handwritten line, the
highlights, the images, the logo strip and one "Omschrijving anders"
(``explanation_md``), which is empty when the activity's own description is
used.

The image generations remember what was asked (``scene``) and in which
style (``style``: ``lijn`` or ``kleur``), so a variant can be redone with
"wat wil je anders?" on top of it. A third preset ``eenvoudig`` (one big
picture over the full width — the Bowlen poster) joins the CHECK.

Idempotent: columns are dropped only if present, added only if missing.
"""
import sqlalchemy as sa
from alembic import op

revision = "140_2026_09_19_190000"
down_revision = "139_2026_09_19_161615"
branch_labels = None
depends_on = None

DROPPED = ("title_breaks", "title_override", "show_kicker", "recurrence_line", "welcome_line",
           "price_text", "practical_md", "programme_md")


def _has_column(table: str, column: str) -> bool:
    return bool(op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'designstudio' AND table_name = :t AND column_name = :c"),
        {"t": table, "c": column}).scalar())


def upgrade() -> None:
    for column in DROPPED:
        if _has_column("designs", column):
            op.drop_column("designs", column, schema="designstudio")
    if not _has_column("image_generations", "scene"):
        op.add_column("image_generations", sa.Column("scene", sa.Text, nullable=False, server_default=""),
                      schema="designstudio")
    op.execute("ALTER TABLE designstudio.designs DROP CONSTRAINT IF EXISTS ck_design_preset")
    op.create_check_constraint("ck_design_preset", "designs", "preset IN ('beeld', 'tekst', 'eenvoudig')",
                               schema="designstudio")
    if not _has_column("image_generations", "style"):
        op.add_column("image_generations", sa.Column("style", sa.String(10), nullable=False, server_default="lijn"),
                      schema="designstudio")


def downgrade() -> None:
    for column, kind in (("title_breaks", sa.String(255)), ("title_override", sa.String(255)),
                         ("recurrence_line", sa.String(80)), ("welcome_line", sa.String(80)),
                         ("price_text", sa.String(60)), ("practical_md", sa.Text), ("programme_md", sa.Text)):
        if not _has_column("designs", column):
            op.add_column("designs", sa.Column(column, kind, nullable=True), schema="designstudio")
    if not _has_column("designs", "show_kicker"):
        op.add_column("designs", sa.Column("show_kicker", sa.Boolean, nullable=False, server_default=sa.false()),
                      schema="designstudio")
    for column in ("scene", "style"):
        if _has_column("image_generations", column):
            op.drop_column("image_generations", column, schema="designstudio")
