"""Every outbound AI call, logged at the seam (#917, CR-07 §6.4).

One row per call to a language model, written **at the provider seam** and not in
the capability that triggered it. That placement is the whole point: the public
Raakje and the back-office assistant are two toolsets on one loop, so a log at the
seam covers both — and covers whatever the assistant learns to do next, without
new plumbing. It also answers "wat kost de AI deze maand?" in one query, for both
surfaces at once, because `tokens_*` is recorded here rather than discarded as it
is today.

**The payload is stored verbatim, and that is a promise being made checkable.**
The screen shows a per-answer "wat zag Mistral" fold-out reading straight from
this column. An assurance the admin cannot inspect is not assurance; this table is
what turns "no personal data leaves the building" from a claim into something a
board member can look at.

What it holds is what LEFT, never a rawer copy: the question as it was sent
(scrubbed, once phase 2 lands) and tool results as they were sent (tokenised).
That is deliberate — a log holding the unscrubbed original would create exactly
the store of personal data the mechanism exists to avoid.

Append-only, like reporting's `export_log` and for the same reason: rows handed to
a third party are data leaving the system, and a record of that may not be
editable by the process it records. `blocked_reason` is filled when the seam guard
refused to send (§5.8) — a blocked call is the row you most want to keep.

The `ai` schema is the chatbot domain's own (migration 084).
"""
from alembic import op
import sqlalchemy as sa

revision = "118"
down_revision = "117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_call_log",
        sa.Column("id", sa.Integer, primary_key=True),
        # Welke schil belde: "public" (Raakje op de site) of "admin" (de
        # assistent). Eén kolom, want het antwoord op "wat kost wat" mag geen
        # afleiding uit een ander veld vergen.
        sa.Column("surface", sa.String(32), nullable=False),
        # De capability-pack binnen die schil ("reporting"), zodat een tweede pack
        # straks apart telbaar is zonder migratie.
        sa.Column("capability", sa.String(32), nullable=False, server_default=""),
        # Wie het vroeg: het e-mailadres uit de sessie bij de beheerderskant, leeg
        # bij de publieke bot — die heeft geen gebruiker en mag er geen krijgen.
        sa.Column("actor", sa.String(255), nullable=False, server_default=""),
        sa.Column("model", sa.String(64), nullable=False, server_default=""),
        # Wat er werkelijk vertrok, als JSON-tekst. Text en geen JSONB: dit is een
        # afschrift, geen bevraagbare structuur — er wordt in gelezen, niet in
        # gezocht.
        sa.Column("payload", sa.Text, nullable=False, server_default=""),
        sa.Column("tokens_prompt", sa.Integer, nullable=True),
        sa.Column("tokens_completion", sa.Integer, nullable=True),
        # Gevuld als de naadwachter de oproep tegenhield; leeg als ze doorging.
        sa.Column("blocked_reason", sa.Text, nullable=False, server_default=""),
        sa.Column("tenant_id", sa.Integer, nullable=False, server_default="2"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        schema="ai",
    )
    op.create_index("ix_ai_call_log_tenant_id", "ai_call_log", ["tenant_id"],
                    schema="ai")
    # De twee vragen die dit logboek krijgt: "wat is er vandaag gebeurd" en "wat
    # kostte deze maand". Beide lezen op tijd, dus één index daarop.
    op.create_index("ix_ai_call_log_created_at", "ai_call_log", ["created_at"],
                    schema="ai")


def downgrade() -> None:
    op.drop_index("ix_ai_call_log_created_at", table_name="ai_call_log", schema="ai")
    op.drop_index("ix_ai_call_log_tenant_id", table_name="ai_call_log", schema="ai")
    op.drop_table("ai_call_log", schema="ai")
