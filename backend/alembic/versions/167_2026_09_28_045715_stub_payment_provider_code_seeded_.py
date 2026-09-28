"""stub payment provider code seeded retired

#1274: the e2e tests of the online payment chain need a stand-in provider, and a
stub payment stored in development carries `provider = 'stub'`, which the foreign
key on `gateway_payments.provider` would refuse without a row.

The row goes in on **every** environment, PROD included, because a migration
runs the same everywhere — and it goes in **retired** (`is_active = false`), so
no list ever offers it. The brake that matters is in the code: the stub cannot
be chosen outside development and the tests (`config.PAYMENT_STUB_ENVIRONMENTS`),
and its pages are not even registered there.

No data change beyond the one code row and its two labels.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.payment.codes import PAYMENT_PROVIDER_CODES
from app.kernel.codes import create_code_list


# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
revision = '167_2026_09_28_045715'
down_revision = '166_2026_09_28_043139'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The list exists (migration of #1178); the helper is idempotent and adds
    # only the row that is missing. The seed says `is_active=False`.
    create_code_list(op, schema="payment", name="payment_provider",
                     codes=PAYMENT_PROVIDER_CODES,
                     fk_from=("payment.gateway_payments.provider",), code_length=20)


def downgrade() -> None:
    # Removes the row again. On an environment where a stub payment was stored
    # (development only), the foreign key refuses — and that is right: a
    # downgrade must not orphan a payment silently.
    op.execute("DELETE FROM payment.payment_provider_labels WHERE code = 'stub'")
    op.execute("DELETE FROM payment.payment_provider_codes WHERE code = 'stub'")
