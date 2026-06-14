"""activity_dates — meerdere datums per activiteit (#122)

Stap 1: maak activity_dates tabel aan.
Stap 2: migreer bestaande date/date_end/time/time_end naar activity_dates.
Stap 3: verwijder de oude kolommen van activities.

Idempotent: controleert of de tabel al bestaat / de kolommen nog aanwezig zijn.

Revision ID: 043
Revises: 042
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    table_exists = conn.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name='activity_dates')"
    )).scalar()

    if not table_exists:
        op.create_table(
            "activity_dates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("start_time", sa.Time(), nullable=True),
            sa.Column("end_time", sa.Time(), nullable=True),
        )
        op.create_index("ix_activity_dates_activity_id", "activity_dates", ["activity_id"])
        op.create_index("ix_activity_dates_start_date", "activity_dates", ["start_date"])

    date_col_exists = conn.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='activities' AND column_name='date')"
    )).scalar()

    if date_col_exists:
        conn.execute(text(
            "INSERT INTO activity_dates (activity_id, start_date, end_date, start_time, end_time) "
            "SELECT id, date, date_end, time, time_end FROM activities "
            "WHERE id NOT IN (SELECT DISTINCT activity_id FROM activity_dates)"
        ))

        op.drop_column("activities", "date")
        op.drop_column("activities", "date_end")
        op.drop_column("activities", "time")
        op.drop_column("activities", "time_end")


def downgrade():
    conn = op.get_bind()

    op.add_column("activities", sa.Column("date", sa.Date(), nullable=True))
    op.add_column("activities", sa.Column("date_end", sa.Date(), nullable=True))
    op.add_column("activities", sa.Column("time", sa.Time(), nullable=True))
    op.add_column("activities", sa.Column("time_end", sa.Time(), nullable=True))

    conn.execute(text(
        "UPDATE activities a SET "
        "date = ad.start_date, date_end = ad.end_date, "
        "time = ad.start_time, time_end = ad.end_time "
        "FROM ("
        "  SELECT DISTINCT ON (activity_id) activity_id, start_date, end_date, start_time, end_time "
        "  FROM activity_dates ORDER BY activity_id, start_date ASC"
        ") ad "
        "WHERE a.id = ad.activity_id"
    ))

    op.alter_column("activities", "date", nullable=False)

    op.drop_table("activity_dates")
