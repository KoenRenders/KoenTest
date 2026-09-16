"""A registration deadline per activity (#974).

Koen: some activities close registrations before they take place — a bowling night,
a visit to a wine estate — and after that date registering must no longer be
possible. A deadline that only exists on a poster is a promise the form does not
keep.

**Inclusive, and in Belgian time.** `registration_closes_on = 2026-10-01` means you
can still register on 1 October until midnight in Brussels. The column is a DATE and
not a timestamp on purpose: what the board types is a day, and storing an instant
would force a choice of hour that nobody made. The time zone is applied where the
rule is evaluated (`activities.service.registration_state`), not here.

**Nullable**, because most activities have no deadline, and without one everything
behaves exactly as before.

On the activity and not on the component: a deadline per component arrives when an
activity needs one, and not before.

Idempotent, like every migration here: running it twice changes nothing.
"""
from alembic import op
import sqlalchemy as sa

revision = "128"
down_revision = "127"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bestaat = op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'activities' AND table_name = 'activities' "
        "AND column_name = 'registration_closes_on'")).scalar()
    if not bestaat:
        op.add_column("activities",
                      sa.Column("registration_closes_on", sa.Date, nullable=True),
                      schema="activities")


def downgrade() -> None:
    op.drop_column("activities", "registration_closes_on", schema="activities")
