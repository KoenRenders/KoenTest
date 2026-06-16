"""media_assets.component_id voor poster/reglement-uploads (#223)

Eén kolom volstaat: affiches (kind=activity_poster) hangen aan een activiteit
(bestaande activity_id), info/reglement (kind=component_info) aan een onderdeel
(nieuwe component_id). Beide met ondelete CASCADE zodat de blob mee verdwijnt.
Geen soft delete op media (bewust, #166).

Revision ID: 057
Revises: 056
"""
from alembic import op
import sqlalchemy as sa

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("media_assets", sa.Column("component_id", sa.Integer(), nullable=True))
    op.create_index("ix_media_assets_component_id", "media_assets", ["component_id"])
    op.create_foreign_key(
        "fk_media_assets_component_id", "media_assets",
        "activity_sub_registrations", ["component_id"], ["id"], ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint("fk_media_assets_component_id", "media_assets", type_="foreignkey")
    op.drop_index("ix_media_assets_component_id", table_name="media_assets")
    op.drop_column("media_assets", "component_id")
