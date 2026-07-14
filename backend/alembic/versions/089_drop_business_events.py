"""Blok O (#407): business_events integraal weg — beslissing Koen 2026-07-14.
De webstatistieken lopen via Umami; het analyse-scherm en de PII-guard
vervallen mee. Dropt de tabel en het (dan lege) analytics-schema.

Revision ID: 089
Revises: 088
"""
from alembic import op

revision = "089"
down_revision = "088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS analytics.business_events")
    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE")


def downgrade() -> None:
    # Bewust geen herstel: de event-data is per beslissing verwijderd.
    op.execute("CREATE SCHEMA IF NOT EXISTS analytics")
