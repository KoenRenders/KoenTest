"""Organisers of an activity, up to three (#1004, CR-10 §3.9).

An activity has "trekkers": up to three members who carry it. The ones ticked as
contact person go on the poster with their name, e-mail and mobile — with an
override per activity when someone wants to be reached on another address or
number for this one. Nobody ticked: the poster falls back to Raak's own details.

This is a fact about the ACTIVITY, not a design choice: every design shows the
same organisers, and a newsletter or a mail can read them without knowing the
Design Studio exists.

`person_id` is a soft reference to `mdm.persons` — §8 forbids a foreign key
across schemas, so the coupling stays a plain integer, like every other
cross-schema reference in this codebase.

Three of them, and the database says so: `CHECK (sort_order IN (0, 1, 2))`. The
service refuses the fourth with a readable message; this is the net underneath.
The screen merely hides the button — that is not a limit.

Idempotent: the table is only created when it is missing.
"""
from alembic import op
import sqlalchemy as sa

revision = "133_2026_09_18_141900"
down_revision = "132_2026_09_17_104125"
branch_labels = None
depends_on = None


def _has_table(schema: str, table: str) -> bool:
    return bool(op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = :s AND table_name = :t"), {"s": schema, "t": table}).scalar())


def upgrade() -> None:
    if _has_table("activities", "activity_organisers"):
        return
    op.create_table(
        "activity_organisers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
        sa.Column("activity_id", sa.Integer,
                  sa.ForeignKey("activities.activities.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("person_id", sa.Integer, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        # Ticked = on the poster, with name and details. Not ticked = carries the
        # activity but is not published.
        sa.Column("is_contact", sa.Boolean, nullable=False, server_default=sa.false()),
        # Empty = the details from the member's own record.
        sa.Column("email_override", sa.String(255), nullable=True),
        sa.Column("mobile_override", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("activity_id", "person_id",
                            name="uq_activity_organiser_person"),
        sa.UniqueConstraint("activity_id", "sort_order",
                            name="uq_activity_organiser_order"),
        sa.CheckConstraint("sort_order IN (0, 1, 2)",
                           name="ck_activity_organiser_max_three"),
        schema="activities",
    )


def downgrade() -> None:
    op.drop_table("activity_organisers", schema="activities")
