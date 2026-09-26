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


# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '156_2026_09_26_050603'
down_revision = '155_2026_09_26_045108'
branch_labels = None
depends_on = None

LIJSTEN = (
    ("subscriber_status", SUBSCRIBER_STATUS_CODES, "newsletter.subscribers.status"),
    ("subscriber_source", SUBSCRIBER_SOURCE_CODES, "newsletter.subscribers.source"),
    ("audience", AUDIENCE_CODES, "newsletter.newsletters.audience"),
    ("letter_status", LETTER_STATUS_CODES, "newsletter.newsletters.status"),
    ("reply_to_mode", REPLY_TO_MODE_CODES, "newsletter.newsletters.reply_to_mode"),
    ("delivery_kind", DELIVERY_KIND_CODES, "newsletter.deliveries.kind"),
    ("delivery_status", DELIVERY_STATUS_CODES, "newsletter.deliveries.status"),
    ("message_role", MESSAGE_ROLE_CODES, "newsletter.drafting_messages.role"),
)

#: De CHECK-constraints van migratie 129 die hetzelfde zeggen als de nieuwe
#: foreign keys. `ck_newsletters_audience_when_sending` blijft: die zegt iets
#: ánders — dat een brief niet zonder doelgroep verstuurd kan worden — en dat
#: is een regel over twee kolommen samen, geen lijst.
CHECKS = (("subscribers", "ck_newsletter_subscriber_status"),
          ("subscribers", "ck_newsletter_subscriber_source"),
          ("newsletters", "ck_newsletter_audience"),
          ("newsletters", "ck_newsletter_status"),
          ("deliveries", "ck_newsletter_delivery_kind"),
          ("deliveries", "ck_newsletter_delivery_status"),
          ("drafting_messages", "ck_newsletter_message_role"))


def upgrade() -> None:
    for naam, codes, kolom in LIJSTEN:
        create_code_list(op, schema="newsletter", name=naam, codes=codes,
                         fk_from=(kolom,), code_length=20)

    inspecteur = sa.inspect(op.get_bind())
    for tabel, constraint in CHECKS:
        bestaand = {c["name"] for c in inspecteur.get_check_constraints(
            tabel, schema="newsletter")}
        if constraint in bestaand:
            op.drop_constraint(constraint, tabel, schema="newsletter",
                               type_="check")


def downgrade() -> None:
    # Schema only: geen nieuwsbriefdata geschreven, geen bestaande waarde
    # veranderd.
    for tabel, constraint, conditie in (
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
        op.create_check_constraint(constraint, tabel, conditie, schema="newsletter")
    for naam, _codes, kolom in LIJSTEN:
        _schema, tabel, kolomnaam = kolom.split(".")
        op.drop_constraint(f"fk_{tabel}_{kolomnaam}_code", tabel,
                           schema="newsletter", type_="foreignkey")
        op.drop_table(f"{naam}_labels", schema="newsletter")
        op.drop_table(f"{naam}_codes", schema="newsletter")
