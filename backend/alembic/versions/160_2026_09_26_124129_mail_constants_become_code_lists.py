"""mail constants become code lists

CR-12 phase 4, the mail domain. Two lists that were module tuples: the e-mail
type and the mail status.

`ck_email_log_status` goes: the foreign key says the same. It is the CHECK of
migration 062, rewritten by migration 087 to add `logged` — the status the
Python tuple never learned about, which is why the status filter never offered
it. One more example of two guards on one value drifting apart.

The e-mail type never had a CHECK. The helper counts the rows before it adds
each key and aborts naming what does not fit; an environment with a type that
is in neither list stops here instead of losing it.

No data change.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.mail.codes import EMAIL_TYPE_CODES, MAIL_STATUS_CODES
from app.kernel.codes import create_code_list


# The id is a timestamp, not a sequence number (#951).
revision = '160_2026_09_26_124129'
down_revision = '159_2026_09_26_073514'
branch_labels = None
depends_on = None

LISTS = (
    ("email_type", EMAIL_TYPE_CODES, 40, "mail.email_log.email_type"),
    ("mail_status", MAIL_STATUS_CODES, 20, "mail.email_log.status"),
)

#: The CHECK that says what the new foreign key says.
CHECKS = (("email_log", "ck_email_log_status"),)


def upgrade() -> None:
    for name, codes, length, column in LISTS:
        create_code_list(op, schema="mail", name=name, codes=codes,
                         fk_from=(column,), code_length=length)

    inspector = sa.inspect(op.get_bind())
    for table, constraint in CHECKS:
        existing = {c["name"] for c in
                    inspector.get_check_constraints(table, schema="mail")}
        if constraint in existing:
            op.drop_constraint(constraint, table, schema="mail", type_="check")


def downgrade() -> None:
    # Schema only: this migration wrote no mail data.
    op.create_check_constraint(
        "ck_email_log_status", "email_log",
        "status IN ('sent', 'failed', 'skipped', 'logged')", schema="mail")
    for name, _codes, _length, column in LISTS:
        _schema, table, column_name = column.split(".")
        op.drop_constraint(f"fk_{table}_{column_name}_code", table,
                           schema="mail", type_="foreignkey")
        op.drop_table(f"{name}_labels", schema="mail")
        op.drop_table(f"{name}_codes", schema="mail")
