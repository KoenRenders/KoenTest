"""One thumbs-up per visitor per photo (#883).

A counter per photo, with at most one thumb per browser. The uniqueness lives **in the
database** and not only in the service: two quick clicks cross each other, and then the
service checks "does a row exist?" twice before either insert lands. A UNIQUE constraint is
the only thing that holds in that race.

**The visitor token is random and meaningless.** No IP, no browser fingerprint, no name —
just a long random value in a first-party cookie. That is a deliberate limit: with an
identifier derived from the visitor you would have built a tracking mechanism for a thumbs-up
on a village photo.

**And no names anywhere.** This table holds who-in-the-sense-of-which-browser only so that
clicking again can remove the thumb; nothing reads it back per visitor. Show who gave a
thumb and you have built a small social network with everything that comes with it.

``tenant_id`` is there because every tenant table carries it (kernel mixin, RLS-ready): a
thumb on a photo of one afdeling has no business showing up at another.
"""
from alembic import op
import sqlalchemy as sa

revision = "113"
down_revision = "112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_thumbs_up",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("asset_id", sa.Integer, nullable=False, index=True),
        # 43 tekens bij 32 bytes urlsafe base64; 64 laat ruimte zonder te knellen.
        sa.Column("visitor_token", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.Integer, nullable=False, server_default="2"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["asset_id"], ["media.media_assets.id"],
                                ondelete="CASCADE"),
        # DE regel van dit issue: hoogstens één rij per (foto, bezoeker). Op DB-niveau,
        # want twee snelle kliks kruisen elkaar en dan is een servicecontrole te laat.
        sa.UniqueConstraint("asset_id", "visitor_token", name="uq_thumb_per_visitor"),
        # Zelfde schema als media_assets, anders vindt de FK haar doel niet.
        schema="media",
    )
    op.create_index("ix_media_thumbs_up_tenant_id", "media_thumbs_up", ["tenant_id"],
                    schema="media")


def downgrade() -> None:
    op.drop_index("ix_media_thumbs_up_tenant_id", table_name="media_thumbs_up",
                  schema="media")
    op.drop_table("media_thumbs_up", schema="media")
