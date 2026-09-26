"""AI call log vocabularies become code lists

CR-12 phase 4, the AI domain. Four columns of `ai.ai_call_log` held free
strings: `surface`, `capability`, `status` and `provider`. Each gets its code
list and a foreign key.

**One data change: an empty capability becomes `chat`.** The public bot and the
back-office chat logged `''`, and the cost screen turned that into the word
"Chat". A foreign key cannot point an empty string at a word, so the word
becomes a code. Measured before this migration was written (26 September
2026): 2 rows on PROD, 0 on UAT. The migration prints the counts before and
after and refuses to lose a row.

**`provider` becomes nullable, and `''` becomes NULL.** "No provider" is an
absence, not a code. No environment holds an empty provider today (measured on
UAT and PROD the same day); the UPDATE stays as a safety net for HDEV and dev.
`capability` and `provider` lose their `''` server default, which would now
violate the key.

No CHECK constraint to drop: these columns never had one.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.chatbot.codes import (
    AI_CAPABILITY_CODES,
    AI_PROVIDER_CODES,
    AI_STATUS_CODES,
    AI_SURFACE_CODES,
)
from app.kernel.codes import add_code_fk, create_code_list


# The id is a timestamp, not a sequence number (#951).
revision = '163_2026_09_26_144116'
down_revision = '162_2026_09_26_131713'
branch_labels = None
depends_on = None

LISTS = (
    ("ai_surface", AI_SURFACE_CODES, 32, "ai.ai_call_log.surface"),
    ("ai_capability", AI_CAPABILITY_CODES, 32, "ai.ai_call_log.capability"),
    ("ai_status", AI_STATUS_CODES, 16, "ai.ai_call_log.status"),
    ("ai_provider", AI_PROVIDER_CODES, 32, "ai.ai_call_log.provider"),
)


# Separate statements, so a test can run them on rows it wrote itself: the
# suite migrates an empty database.
CAPABILITY_BACKFILL = "UPDATE ai.ai_call_log SET capability = 'chat' WHERE capability = ''"
PROVIDER_BACKFILL = "UPDATE ai.ai_call_log SET provider = NULL WHERE provider = ''"


def _counts(bind, column: str) -> dict[str, int]:
    rows = bind.execute(sa.text(
        f"SELECT coalesce({column}, '<NULL>') AS value, count(*) AS n "
        f"FROM ai.ai_call_log GROUP BY 1 ORDER BY 1")).all()
    return {row.value: row.n for row in rows}


def upgrade() -> None:
    bind = op.get_bind()

    # The lists first, without their keys: the data has to fit before a key
    # can go on, and the guard inside `add_code_fk` is what proves it does.
    for name, codes, length, _column in LISTS:
        create_code_list(op, schema="ai", name=name, codes=codes, code_length=length)

    # ── The one data change: '' → 'chat' ─────────────────────────────────────
    before = _counts(bind, "capability")
    print(f"[CR-12 phase 4] ai.ai_call_log.capability before: {before}")
    bind.execute(sa.text(CAPABILITY_BACKFILL))
    after = _counts(bind, "capability")
    print(f"[CR-12 phase 4] ai.ai_call_log.capability after:  {after}")
    if sum(before.values()) != sum(after.values()):
        raise RuntimeError(
            f"ai.ai_call_log.capability: {sum(before.values())} rows before and "
            f"{sum(after.values())} after — an UPDATE may not lose a row")
    op.alter_column("ai_call_log", "capability", schema="ai", server_default=None)

    # ── No provider is NULL, not '' ──────────────────────────────────────────
    op.alter_column("ai_call_log", "provider", schema="ai",
                    nullable=True, server_default=None)
    emptied = bind.execute(sa.text(PROVIDER_BACKFILL)).rowcount
    print(f"[CR-12 phase 4] ai.ai_call_log.provider: {emptied} empty row(s) set to NULL")

    for name, codes, _length, column in LISTS:
        add_code_fk(op, column, "ai", name, {seed.code for seed in codes})


def downgrade() -> None:
    # Schema and data both: the keys and tables go, provider is NOT NULL with
    # '' again, and every `chat` row goes back to ''. That last step is exact
    # only because nothing wrote `chat` before this migration.
    bind = op.get_bind()
    for name, _codes, _length, column in reversed(LISTS):
        _schema, table, column_name = column.split(".")
        op.drop_constraint(f"fk_{table}_{column_name}_code", table,
                           schema="ai", type_="foreignkey")
        op.drop_table(f"{name}_labels", schema="ai")
        op.drop_table(f"{name}_codes", schema="ai")
    bind.execute(sa.text(
        "UPDATE ai.ai_call_log SET provider = '' WHERE provider IS NULL"))
    op.alter_column("ai_call_log", "provider", schema="ai",
                    nullable=False, server_default="")
    bind.execute(sa.text(
        "UPDATE ai.ai_call_log SET capability = '' WHERE capability = 'chat'"))
    op.alter_column("ai_call_log", "capability", schema="ai", server_default="")
