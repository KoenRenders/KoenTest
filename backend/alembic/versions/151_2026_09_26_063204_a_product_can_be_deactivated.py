"""A product can be taken off the public registration form (#1191).

Eight people join an activity for free and there was no way to keep a product out
of the public form other than **deleting** it. Deleting is a soft delete, and the
global filter reaches relationship loads too, so the consequences land on the
registrations that already sit on that product: the line keeps its quantity but
loses its name on screen, and the .ods door list loses the whole column, because
both read the LIVING products of the component. The amount due falls back to zero
for the same reason.

So the flag is not a convenience. It is the difference between "this product is no
longer offered" and "this product never existed", and only the first one keeps the
bookings readable.

**Off means gone from the public form, NOT closed** (Koen, 26 September 2026). The
board must still be able to put someone on an inactive product from the back
office; that is the entire point. The refusal therefore lives in the service layer
of the public entrance and not in the template, and not on this column.

**Default true, and existing rows come along as true**, so nothing changes about
what can be booked today. Idempotent: the column is only added when it is missing.
"""
from alembic import op
import sqlalchemy as sa


# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '151_2026_09_26_063204'
down_revision = '151_2026_09_26_061026'
branch_labels = None
depends_on = None

COLUMN = "is_active"


def _has_column() -> bool:
    return bool(op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'activities' AND table_name = 'activity_products' "
        "AND column_name = :k"), {"k": COLUMN}).scalar())


def upgrade() -> None:
    if not _has_column():
        # server_default sets the existing rows to true in the same step; without
        # it NOT NULL would fail on a populated table.
        op.add_column("activity_products",
                      sa.Column(COLUMN, sa.Boolean, nullable=False,
                                server_default=sa.true()),
                      schema="activities")


def downgrade() -> None:
    """Schema only. Which products were deactivated is lost: after this downgrade
    every product is back on the public form. Existing registrations are untouched —
    they hang on the product, not on this flag."""
    if _has_column():
        op.drop_column("activity_products", COLUMN, schema="activities")
