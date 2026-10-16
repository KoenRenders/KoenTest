"""Letters to the people registered for earlier activities (CR-36, #2026).

A fourth audience (*Eerdere deelnemers*), a third delivery kind and a fourth
subscriber source — rows of three code lists, with their Dutch and English words —
and the table that holds the earlier activities a letter is addressed to. The
activity is a soft reference across the schema line (its name and its last date are
copied when the send starts), so the table has no foreign key to `activities`.

Downgrade removes the table and the code rows, the rows that use them first: a letter
with this audience loses it (it becomes a draft without audience if it is one), a
delivery of the new kind is deleted with its letter's archive line, a subscriber row of
the new source becomes an import (the opt-out stays).
"""

import sqlalchemy as sa
from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
# `repr` with double quotes (#781): the generated file must already be what
# `ruff format` writes, or every new migration turns CI red. A `repr` still, not
# a bare string, because `down_revision` is a tuple for a merge and None for the
# first migration.
revision = "213_2026_10_15_205117"
down_revision = "212_2026_10_15_172727"
branch_labels = None
depends_on = None


CODES = (
    (
        "newsletter.audience",
        "audience",
        "participants",
        40,
        "Eerdere deelnemers",
        "Earlier participants",
    ),
    (
        "newsletter.delivery_kind",
        "delivery_kind",
        "participant",
        30,
        "Eerdere deelnemer",
        "Earlier participant",
    ),
    (
        "newsletter.subscriber_source",
        "subscriber_source",
        "participant",
        40,
        "Via brief aan eerdere deelnemers",
        "Via a letter to earlier participants",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    for _list, table, code, order, nl, en in CODES:
        bind.execute(
            sa.text(
                f"INSERT INTO newsletter.{table}_codes (code, sort_order, is_active, created_at) "
                "VALUES (:code, :order, true, now()) ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "order": order},
        )
        for language, value in (("nl", nl), ("en", en)):
            bind.execute(
                sa.text(
                    f"INSERT INTO newsletter.{table}_labels "
                    "(code, language, value, created_at, updated_at) "
                    "VALUES (:code, :language, :value, now(), now()) "
                    "ON CONFLICT (code, language) DO NOTHING"
                ),
                {"code": code, "language": language, "value": value},
            )
    inspector = sa.inspect(bind)
    if "audience_activities" not in inspector.get_table_names(schema="newsletter"):
        op.create_table(
            "audience_activities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column(
                "newsletter_id",
                sa.Integer(),
                sa.ForeignKey("newsletter.newsletters.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("activity_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("last_date", sa.Date(), nullable=True),
            sa.UniqueConstraint("newsletter_id", "activity_id", name="uq_audience_activity"),
            schema="newsletter",
        )
        op.create_index(
            "ix_newsletter_audience_activities_id",
            "audience_activities",
            ["id"],
            schema="newsletter",
        )
        op.create_index(
            "ix_newsletter_audience_activities_tenant_id",
            "audience_activities",
            ["tenant_id"],
            schema="newsletter",
        )
        op.create_index(
            "ix_newsletter_audience_activities_newsletter_id",
            "audience_activities",
            ["newsletter_id"],
            schema="newsletter",
        )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("audience_activities", schema="newsletter")
    bind.execute(sa.text("DELETE FROM newsletter.deliveries WHERE kind = 'participant'"))
    bind.execute(
        sa.text("UPDATE newsletter.newsletters SET audience = NULL WHERE audience = 'participants'")
    )
    bind.execute(
        sa.text("UPDATE newsletter.subscribers SET source = 'import' WHERE source = 'participant'")
    )
    for _list, table, code, *_rest in CODES:
        bind.execute(sa.text(f"DELETE FROM newsletter.{table}_labels WHERE code = :c"), {"c": code})
        bind.execute(sa.text(f"DELETE FROM newsletter.{table}_codes WHERE code = :c"), {"c": code})
