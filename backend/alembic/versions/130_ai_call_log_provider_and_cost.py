"""Provider, API and cost per outbound AI call (#978).

`ai.ai_call_log` (migration 118) was written for one provider and counted tokens
only. CR-10 (Design Studio) adds a second provider that bills per image, and the
AI budget per department counts from this table — so the table learns which
provider and API were called, how it went, how long it took and what it cost.
A separate cost log would put the same fact in a second place.

Purely additive: every new column has a default or is nullable, so the release
still running during a deploy keeps writing rows without knowing about them.

`cost_credits` is the cost as the provider reports it, in its own unit (Black
Forest Labs: credits, 1 credit = $0.01). `cost_amount` + `cost_currency` is the
same cost in money (ISO 4217), so a sum never adds credits to euros.

Existing rows: every call so far went to Mistral — the only provider the seam
has known — and a filled `blocked_reason` is what "blocked" meant. The backfill
keys on `model` anyway, so a row written by the mock provider in a test
database stays unlabelled rather than being called Mistral.

Idempotent: a column is only added when it is missing.
"""
from alembic import op
import sqlalchemy as sa

revision = "130_2026_09_17_070503"
down_revision = "129_2026_09_16_221108"
branch_labels = None
depends_on = None

COLUMNS = [
    sa.Column("provider", sa.String(32), nullable=False, server_default=""),
    sa.Column("endpoint", sa.String(128), nullable=False, server_default=""),
    sa.Column("provider_request_id", sa.String(128), nullable=False, server_default=""),
    sa.Column("status", sa.String(16), nullable=False, server_default=""),
    sa.Column("duration_ms", sa.Integer, nullable=True),
    sa.Column("cost_credits", sa.Numeric(12, 4), nullable=True),
    sa.Column("cost_amount", sa.Numeric(12, 6), nullable=True),
    sa.Column("cost_currency", sa.CHAR(3), nullable=True),
    sa.Column("output_megapixels", sa.Numeric(6, 2), nullable=True),
]

# Separate statements, so a test can run them on rows it made itself: the suite
# migrates an empty database.
BACKFILL_SQL = [
    "UPDATE ai.ai_call_log SET provider = 'mistral' "
    "WHERE provider = '' AND model ILIKE 'mistral%'",
    "UPDATE ai.ai_call_log SET status = CASE WHEN blocked_reason <> '' "
    "THEN 'blocked' ELSE 'ok' END WHERE status = ''",
]


def _has_column(table: str, column: str) -> bool:
    return bool(op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'ai' AND table_name = :t AND column_name = :c"),
        {"t": table, "c": column}).scalar())


def upgrade() -> None:
    for column in COLUMNS:
        if not _has_column("ai_call_log", column.name):
            op.add_column("ai_call_log", column.copy(), schema="ai")
    for statement in BACKFILL_SQL:
        op.execute(statement)
    # The cost question is "this department, this period": one index on both.
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_call_log_tenant_created "
               "ON ai.ai_call_log (tenant_id, created_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ai.ix_ai_call_log_tenant_created")
    for column in reversed(COLUMNS):
        if _has_column("ai_call_log", column.name):
            op.drop_column("ai_call_log", column.name, schema="ai")
