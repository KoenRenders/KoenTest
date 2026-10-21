"""a delivery can be marked as bounced

A sent letter can be marked as bounced by hand and sent again (#2188). The
mailbox, not the platform, learns of a bounce, so the status is set by a person.
The status is a row in the code list the deliveries point at.
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
revision = "319_2026_10_21_085617"
down_revision = "318_2026_10_19_154158"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO newsletter.delivery_status_codes (code, sort_order, is_active, created_at) "
            "VALUES ('bounced', 50, true, now()) ON CONFLICT (code) DO NOTHING"
        )
    )
    for language, value in (("nl", "Teruggekomen"), ("en", "Bounced")):
        bind.execute(
            sa.text(
                "INSERT INTO newsletter.delivery_status_labels "
                "(code, language, value, created_at, updated_at) "
                "VALUES ('bounced', :language, :value, now(), now()) "
                "ON CONFLICT (code, language) DO NOTHING"
            ),
            {"language": language, "value": value},
        )


def downgrade() -> None:
    # Restores the schema, and the data as far as it can be: a bounced delivery
    # goes back to `sent`, which is what the platform thought of it before.
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE newsletter.deliveries SET status = 'sent' WHERE status = 'bounced'")
    )
    bind.execute(sa.text("DELETE FROM newsletter.delivery_status_labels WHERE code = 'bounced'"))
    bind.execute(sa.text("DELETE FROM newsletter.delivery_status_codes WHERE code = 'bounced'"))
