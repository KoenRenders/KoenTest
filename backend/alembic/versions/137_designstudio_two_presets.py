"""Design Studio: two presets instead of four (#1007, Koen's HDEV round of
19 September 2026).

The four presets of CR-10 §3.4 (beeld, tekstflyer, illustratie, reeks) were
three times the same flow; nobody could tell them apart. Two remain: ``beeld``
(a picture right, highlights left) and ``tekst`` (text over the full width).
Existing rows map onto them; the CHECK follows. Idempotent.
"""
from alembic import op

revision = "137_2026_09_19_160000"
down_revision = "136_2026_09_18_153000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE designstudio.designs SET preset = 'beeld' WHERE preset IN ('illustratie', 'reeks')")
    op.execute("UPDATE designstudio.designs SET preset = 'tekst' WHERE preset = 'tekstflyer'")
    op.execute("ALTER TABLE designstudio.designs DROP CONSTRAINT IF EXISTS ck_design_preset")
    op.execute("ALTER TABLE designstudio.designs ALTER COLUMN preset SET DEFAULT 'beeld'")
    op.create_check_constraint("ck_design_preset", "designs", "preset IN ('beeld', 'tekst')", schema="designstudio")


def downgrade() -> None:
    op.execute("ALTER TABLE designstudio.designs DROP CONSTRAINT IF EXISTS ck_design_preset")
    op.create_check_constraint("ck_design_preset", "designs",
                               "preset IN ('beeld', 'tekstflyer', 'illustratie', 'reeks')", schema="designstudio")
