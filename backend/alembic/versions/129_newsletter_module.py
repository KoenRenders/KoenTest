"""The newsletter module (CR-05, #984).

Koen, 17 September 2026, putting the newsletter on v2.5: the monthly member
letter and the half-yearly letter to about 800 non-members move from a personal
Gmail account with Bcc into the portal, one mail per recipient, with Raakje
drafting alongside.

A schema of its own, `newsletter`, because the lawful basis and the lifecycle
differ from everything in `membership` and `mdm`:

- ``subscribers`` holds only non-members — members are derived from their
  membership and never copied here (CR-05 §3.3). No soft delete: erasure has to
  be real.
- ``newsletters`` is one letter; ``deliveries`` is its queue and its archive,
  one row per address, written when sending starts.
- ``drafting_messages`` is the conversation with Raakje about one draft,
  removed when the letter is sent.

No foreign key leaves the schema (`test_schema_boundaries`): the person a
subscriber turns out to be, and the activities and meeting points a draft is
about, are soft references.

Idempotent: every table is created only when it is missing.
"""
from alembic import op
import sqlalchemy as sa

# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = "129_2026_09_16_221108"
down_revision = "128"
branch_labels = None
depends_on = None


def _has_table(schema: str, table: str) -> bool:
    return bool(op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = :s AND table_name = :t"), {"s": schema, "t": table}).scalar())


def _stamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS newsletter")

    if not _has_table("newsletter", "subscribers"):
        op.create_table(
            "subscribers",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("first_name", sa.String(100), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("source", sa.String(20), nullable=False),
            sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("confirm_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("confirm_token", sa.String(64), nullable=True, unique=True),
            sa.Column("unsubscribe_token", sa.String(64), nullable=False, unique=True),
            sa.Column("person_id", sa.Integer, nullable=True),
            *_stamps(),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "email", name="uq_newsletter_subscriber_email"),
            sa.CheckConstraint("status IN ('pending', 'confirmed', 'unsubscribed')",
                               name="ck_newsletter_subscriber_status"),
            sa.CheckConstraint("source IN ('public_form', 'import', 'admin')",
                               name="ck_newsletter_subscriber_source"),
            # A lower-case address is what makes the unique constraint mean
            # "one row per person" instead of "one row per spelling".
            sa.CheckConstraint("email = lower(email)",
                               name="ck_newsletter_subscriber_email_lower"),
            schema="newsletter",
        )

    if not _has_table("newsletter", "newsletters"):
        op.create_table(
            "newsletters",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("subject", sa.String(500), nullable=False, server_default=""),
            sa.Column("body_html", sa.Text, nullable=False, server_default=""),
            sa.Column("audience", sa.String(20), nullable=True),
            sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
            sa.Column("copied_from_id", sa.Integer,
                      sa.ForeignKey("newsletter.newsletters.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("created_by", sa.String(255), nullable=True),
            sa.Column("draft_activity_ids", sa.JSON, nullable=False,
                      server_default=sa.text("'[]'::json")),
            sa.Column("draft_meeting_item_ids", sa.JSON, nullable=False,
                      server_default=sa.text("'[]'::json")),
            sa.Column("reply_to_mode", sa.String(20), nullable=True),
            sa.Column("reply_to_address", sa.String(255), nullable=True),
            sa.Column("link_base", sa.String(255), nullable=True),
            sa.Column("sent_by", sa.String(255), nullable=True),
            sa.Column("send_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("send_finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
            *_stamps(),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("audience IS NULL OR audience IN ('members', 'non_members', 'both')",
                               name="ck_newsletter_audience"),
            sa.CheckConstraint("status IN ('draft', 'sending', 'sent')",
                               name="ck_newsletter_status"),
            # A letter cannot leave without a chosen audience (CR-05 §3.2) —
            # the screen refuses it, and so does the database.
            sa.CheckConstraint("status = 'draft' OR audience IS NOT NULL",
                               name="ck_newsletter_sent_has_audience"),
            schema="newsletter",
        )

    if not _has_table("newsletter", "deliveries"):
        op.create_table(
            "deliveries",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("newsletter_id", sa.Integer,
                      sa.ForeignKey("newsletter.newsletters.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("subscriber_id", sa.Integer,
                      sa.ForeignKey("newsletter.subscribers.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("status", sa.String(10), nullable=False, server_default="queued",
                      index=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.Column("error", sa.Text, nullable=True),
            *_stamps(),
            sa.UniqueConstraint("newsletter_id", "email", name="uq_newsletter_delivery_email"),
            sa.CheckConstraint("kind IN ('member', 'subscriber')",
                               name="ck_newsletter_delivery_kind"),
            sa.CheckConstraint("status IN ('queued', 'sent', 'failed', 'skipped')",
                               name="ck_newsletter_delivery_status"),
            schema="newsletter",
        )

    if not _has_table("newsletter", "drafting_messages"):
        op.create_table(
            "drafting_messages",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("newsletter_id", sa.Integer,
                      sa.ForeignKey("newsletter.newsletters.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("role", sa.String(10), nullable=False),
            sa.Column("text", sa.Text, nullable=False, server_default=""),
            sa.Column("proposal", sa.JSON, nullable=True),
            *_stamps(),
            sa.CheckConstraint("role IN ('author', 'raakje')",
                               name="ck_newsletter_message_role"),
            schema="newsletter",
        )


def downgrade() -> None:
    # Only the schema, and the data with it: a downgrade removes every
    # subscriber, letter and delivery. There is no way back to "the list lived
    # in a Gmail account" — restore from a dump if that is what you need.
    op.execute("DROP SCHEMA IF EXISTS newsletter CASCADE")
