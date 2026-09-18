"""Design Studio (CR-10, #1007): schema ``designstudio``.

Posters and social images made from an activity. A design stores its inputs
(template, colour duo, design text, image choices) — never its renders, and
never a copy of an activity fact. A numbered version holds the renders and a
fingerprint of the facts it used; "verouderd" is computed on read.

No foreign key leaves the schema (`test_schema_boundaries`): ``activity_id``,
``media_asset_id`` and ``ai_call_log_id`` are soft references.

Idempotent: every table is created only when it is missing.
"""
import sqlalchemy as sa
from alembic import op

# The id is a timestamp, not a sequence number (#951): two CLIs that choose
# "the next number" at the same time choose the same one; two that get a
# timestamp cannot collide. The sequence number leads the FILENAME, for
# readability and sorting — alembic does not look at it.
revision = "134_2026_09_18_153000"
down_revision = "133_2026_09_18_141900"
branch_labels = None
depends_on = None

SCHEMA = "designstudio"


def _has_table(schema: str, table: str) -> bool:
    return bool(op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = :s AND table_name = :t"), {"s": schema, "t": table}).scalar())


def _stamp(name: str = "created_at") -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    if not _has_table(SCHEMA, "designs"):
        op.create_table(
            "designs",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("activity_id", sa.Integer, nullable=False, index=True),
            sa.Column("template_key", sa.String(40), nullable=False, server_default="affiche"),
            sa.Column("template_version", sa.Integer, nullable=False, server_default="1"),
            sa.Column("preset", sa.String(20), nullable=False, server_default="illustratie"),
            sa.Column("duo_code", sa.String(60), nullable=False),
            sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
            sa.Column("title_breaks", sa.String(255), nullable=True),
            sa.Column("title_override", sa.String(255), nullable=True),
            sa.Column("show_kicker", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("tagline", sa.String(90), nullable=True),
            sa.Column("subtitle", sa.String(120), nullable=True),
            sa.Column("recurrence_line", sa.String(80), nullable=True),
            sa.Column("welcome_line", sa.String(80), nullable=True),
            sa.Column("price_text", sa.String(60), nullable=True),
            sa.Column("explanation_md", sa.Text, nullable=True),
            sa.Column("practical_md", sa.Text, nullable=True),
            sa.Column("programme_md", sa.Text, nullable=True),
            sa.Column("main_image_id", sa.Integer, nullable=True),
            sa.Column("main_focus_x", sa.Numeric(4, 3), nullable=False, server_default="0.5"),
            sa.Column("main_focus_y", sa.Numeric(4, 3), nullable=False, server_default="0.5"),
            sa.Column("inset_image_id", sa.Integer, nullable=True),
            sa.Column("third_image_id", sa.Integer, nullable=True),
            sa.Column("published_version_id", sa.Integer, nullable=True),
            sa.Column("created_by", sa.String(255), nullable=False, server_default=""),
            _stamp(), _stamp("updated_at"),
            sa.CheckConstraint("status IN ('draft', 'final')", name="ck_design_status"),
            sa.CheckConstraint("preset IN ('beeld', 'tekstflyer', 'illustratie', 'reeks')",
                               name="ck_design_preset"),
            sa.CheckConstraint("main_focus_x BETWEEN 0 AND 1 AND main_focus_y BETWEEN 0 AND 1",
                               name="ck_design_focus"),
            schema=SCHEMA,
        )

    if not _has_table(SCHEMA, "design_highlights"):
        op.create_table(
            "design_highlights",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("design_id", sa.Integer,
                      sa.ForeignKey(f"{SCHEMA}.designs.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("sort_order", sa.Integer, nullable=False),
            sa.Column("icon_code", sa.String(30), nullable=False),
            sa.Column("text", sa.String(90), nullable=False),
            sa.Column("emphasis", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("design_id", "sort_order", name="uq_design_highlight_order"),
            sa.CheckConstraint("sort_order >= 0 AND sort_order < 6", name="ck_design_highlight_order"),
            schema=SCHEMA,
        )

    if not _has_table(SCHEMA, "design_logos"):
        op.create_table(
            "design_logos",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("design_id", sa.Integer,
                      sa.ForeignKey(f"{SCHEMA}.designs.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("media_asset_id", sa.Integer, nullable=False),
            sa.Column("sort_order", sa.Integer, nullable=False),
            sa.UniqueConstraint("design_id", "sort_order", name="uq_design_logo_order"),
            sa.CheckConstraint("sort_order IN (0, 1)", name="ck_design_logo_order"),
            schema=SCHEMA,
        )

    if not _has_table(SCHEMA, "design_versions"):
        op.create_table(
            "design_versions",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("design_id", sa.Integer,
                      sa.ForeignKey(f"{SCHEMA}.designs.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("number", sa.Integer, nullable=False),
            sa.Column("facts_fingerprint", sa.String(64), nullable=False),
            sa.Column("sponsor_asset_ids", sa.String(120), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(255), nullable=False, server_default=""),
            _stamp(),
            sa.UniqueConstraint("design_id", "number", name="uq_design_version_number"),
            schema=SCHEMA,
        )

    if not _has_table(SCHEMA, "design_renditions"):
        op.create_table(
            "design_renditions",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("design_id", sa.Integer,
                      sa.ForeignKey(f"{SCHEMA}.designs.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("version_id", sa.Integer,
                      sa.ForeignKey(f"{SCHEMA}.design_versions.id", ondelete="CASCADE"),
                      nullable=True, index=True),
            sa.Column("layout_code", sa.String(20), nullable=False),
            sa.Column("variant", sa.String(12), nullable=False),
            sa.Column("size_code", sa.String(20), nullable=False, server_default=""),
            sa.Column("media_asset_id", sa.Integer, nullable=False),
            sa.Column("facts_fingerprint", sa.String(64), nullable=True),
            sa.Column("min_effective_dpi", sa.Integer, nullable=True),
            _stamp("rendered_at"),
            sa.CheckConstraint("layout_code IN ('print_a', 'feed_portrait')",
                               name="ck_design_rendition_layout"),
            sa.CheckConstraint("variant IN ('pdf', 'png', 'jpeg', 'svg', 'svg_edited')",
                               name="ck_design_rendition_variant"),
            # A hand-edited SVG belongs to the draft, every other variant to a version.
            sa.CheckConstraint("(variant = 'svg_edited') = (version_id IS NULL)",
                               name="ck_design_rendition_owner"),
            schema=SCHEMA,
        )

    if not _has_table(SCHEMA, "image_generations"):
        op.create_table(
            "image_generations",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("design_id", sa.Integer,
                      sa.ForeignKey(f"{SCHEMA}.designs.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("request_key", sa.String(64), nullable=False, index=True),
            sa.Column("ai_call_log_id", sa.Integer, nullable=True),
            sa.Column("seed", sa.Integer, nullable=True),
            sa.Column("width", sa.Integer, nullable=False),
            sa.Column("height", sa.Integer, nullable=False),
            sa.Column("status", sa.String(12), nullable=False, server_default="requested"),
            sa.Column("failure_reason", sa.Text, nullable=False, server_default=""),
            sa.Column("media_asset_id", sa.Integer, nullable=True),
            sa.Column("reserved_cents", sa.Integer, nullable=False, server_default="0"),
            sa.Column("requested_by", sa.String(255), nullable=False, server_default=""),
            _stamp("requested_at"),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "status IN ('requested', 'fetched', 'picked', 'discarded', 'refused', 'failed')",
                name="ck_image_generation_status"),
            schema=SCHEMA,
        )


def downgrade() -> None:
    for table in ("image_generations", "design_renditions", "design_versions",
                  "design_logos", "design_highlights", "designs"):
        op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.{table}")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
