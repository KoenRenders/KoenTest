"""the order confirmation mail joins the e-mail types

CR-21 phase 2, commit 7: an order places its confirmation mail, and that mail
needs its own type in the e-mail log. The list is seeded through the one helper
that creates it idempotently, so only the new code is written.
"""

from alembic import op

from app.domains.mail.codes import EMAIL_TYPE_CODES
from app.kernel.codes import create_code_list

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
revision = "311_2026_10_16_123616"
down_revision = "310_2026_10_16_104128"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_code_list(
        op,
        schema="mail",
        name="email_type",
        codes=EMAIL_TYPE_CODES,
        fk_from=("mail.email_log.email_type",),
        code_length=40,
    )


def downgrade() -> None:
    # The log is the record of what was sent (#328): its rows stay. The old app
    # reads `email_type` through the enum and refuses an unknown code, so the rows
    # of the new type are re-typed to `other` before the code and its labels go —
    # as migration 160 kept every row.
    op.execute(
        "UPDATE mail.email_log SET email_type = 'other' WHERE email_type = 'order_confirmation'"
    )
    op.execute("DELETE FROM mail.email_type_labels WHERE code = 'order_confirmation'")
    op.execute("DELETE FROM mail.email_type_codes WHERE code = 'order_confirmation'")
