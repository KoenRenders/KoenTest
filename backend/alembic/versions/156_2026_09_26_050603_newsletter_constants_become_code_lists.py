"""newsletter constants become code lists

CR-12 phase 3, the newsletter. Eight lists, all of them module constants until
now: a tuple of valid values in `models.py`, and a dictionary of Dutch words in
`admin_ui.py` twenty lines further on in another file. Those two drifted by
construction — nothing tied them together.

Four `CHECK` constraints go with them, for the reason this change request has
now met four times: a check that lists the values says exactly what the foreign
key says, and with it in place a new value costs a row *and* a migration.

No data change. Every value the columns hold is in its list; `create_code_list`
counts the rows before it adds each key and aborts naming what does not fit.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.newsletter.codes import (
    AUDIENCE_CODES,
    DELIVERY_KIND_CODES,
    DELIVERY_STATUS_CODES,
    LETTER_STATUS_CODES,
    MESSAGE_ROLE_CODES,
    REPLY_TO_MODE_CODES,
    SUBSCRIBER_SOURCE_CODES,
    SUBSCRIBER_STATUS_CODES,
)
from app.kernel.codes import create_code_list


# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that are handed a
# timestamp cannot collide. The sequence number leads the FILE NAME, for
# reading and sorting — alembic does not look at it.
revision = '156_2026_09_26_050603'
down_revision = '155_2026_09_26_045108'
branch_labels = None
depends_on = None

LISTS = (
    ("subscriber_status", SUBSCRIBER_STATUS_CODES, "newsletter.subscribers.status"),
    ("subscriber_source", SUBSCRIBER_SOURCE_CODES, "newsletter.subscribers.source"),
    ("audience", AUDIENCE_CODES, "newsletter.newsletters.audience"),
    ("letter_status", LETTER_STATUS_CODES, "newsletter.newsletters.status"),
    ("reply_to_mode", REPLY_TO_MODE_CODES, "newsletter.newsletters.reply_to_mode"),
    ("delivery_kind", DELIVERY_KIND_CODES, "newsletter.deliveries.kind"),
    ("delivery_status", DELIVERY_STATUS_CODES, "newsletter.deliveries.status"),
    ("message_role", MESSAGE_ROLE_CODES, "newsletter.drafting_messages.role"),
)

#: The CHECK constraints from migration 129 that say the same as the new
#: foreign keys. `ck_newsletters_audience_when_sending` stays: it says something
#: *else* — that a letter cannot be sent without an audience — and that is a
#: rule about two columns together, not a list.
CHECKS = (("subscribers", "ck_newsletter_subscriber_status"),
          ("subscribers", "ck_newsletter_subscriber_source"),
          ("newsletters", "ck_newsletter_audience"),
          ("newsletters", "ck_newsletter_status"),
          ("deliveries", "ck_newsletter_delivery_kind"),
          ("deliveries", "ck_newsletter_delivery_status"),
          ("drafting_messages", "ck_newsletter_message_role"))


def upgrade() -> None:
    for name, codes, column in LISTS:
        create_code_list(op, schema="newsletter", name=name, codes=codes,
                         fk_from=(column,), code_length=20)

    inspector = sa.inspect(op.get_bind())
    for table, constraint in CHECKS:
        existing = {c["name"] for c in inspector.get_check_constraints(
            table, schema="newsletter")}
        if constraint in existing:
            op.drop_constraint(constraint, table, schema="newsletter",
                               type_="check")


def downgrade() -> None:
    # Schema only: no newsletter data written, no existing value
    # changed.
    for table, constraint, condition in (
            ("subscribers", "ck_newsletter_subscriber_status",
             "status IN ('pending', 'confirmed', 'unsubscribed')"),
            ("subscribers", "ck_newsletter_subscriber_source",
             "source IN ('public_form', 'import', 'admin')"),
            ("newsletters", "ck_newsletter_audience",
             "audience IS NULL OR audience IN ('members', 'non_members', 'both')"),
            ("newsletters", "ck_newsletter_status",
             "status IN ('draft', 'sending', 'sent')"),
            ("deliveries", "ck_newsletter_delivery_kind",
             "kind IN ('member', 'subscriber')"),
            ("deliveries", "ck_newsletter_delivery_status",
             "status IN ('queued', 'sent', 'failed', 'skipped')"),
            ("drafting_messages", "ck_newsletter_message_role",
             "role IN ('author', 'raakje')")):
        op.create_check_constraint(constraint, table, condition, schema="newsletter")
    for name, _codes, column in LISTS:
        _schema, table, column_name = column.split(".")
        op.drop_constraint(f"fk_{table}_{column_name}_code", table,
                           schema="newsletter", type_="foreignkey")
        op.drop_table(f"{name}_labels", schema="newsletter")
        op.drop_table(f"{name}_codes", schema="newsletter")
