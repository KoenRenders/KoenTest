"""Add missing indexes for common query patterns

Revision ID: 007
Revises: 006
Create Date: 2026-06-05
"""
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_activities_date", "activities", ["date"])
    op.create_index("ix_activities_is_archived", "activities", ["is_archived"])
    op.create_index("ix_registrations_activity_id", "registrations", ["activity_id"])
    op.create_index("ix_memberships_member_id", "memberships", ["member_id"])
    op.create_index("ix_memberships_year", "memberships", ["year"])


def downgrade():
    op.drop_index("ix_memberships_year", "memberships")
    op.drop_index("ix_memberships_member_id", "memberships")
    op.drop_index("ix_registrations_activity_id", "registrations")
    op.drop_index("ix_activities_is_archived", "activities")
    op.drop_index("ix_activities_date", "activities")
