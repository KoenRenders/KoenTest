"""ai capability activity drafting

#1604: Raakje proposes name, location, description and date for an activity.
Every model call is registered in `ai.ai_call_log`, and its `capability` has a
foreign key to the code list — so a proposer of its own needs a code of its
own, or its calls would be counted under the newsletter's on the cost screen.

The issue said "no migration"; measured while building: the rows of a code
list only arrive through a migration. The master CLI chose the code over
borrowing another one (5 October 2026).

Additive: one code row and its two labels. The running application never
reads a capability it does not write, so the old code is not affected.
"""

from alembic import op

from app.domains.chatbot.codes import AI_CAPABILITY_CODES
from app.kernel.codes import create_code_list

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
# `repr` with double quotes (#781): the generated file must already be what
# `ruff format` writes, or every new migration turns CI red. A `repr` still, not
# a bare string, because `down_revision` is a tuple for a merge and None for the
# first migration.
revision = "197_2026_10_05_075704"
down_revision = "196_2026_10_04_130503"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The list exists (migration 163); the helper is idempotent and adds only
    # the row that is missing.
    create_code_list(
        op,
        schema="ai",
        name="ai_capability",
        codes=AI_CAPABILITY_CODES,
        fk_from=("ai.ai_call_log.capability",),
        code_length=32,
    )


def downgrade() -> None:
    # Removes the code again. Where a proposal was asked, the call log holds
    # rows with this capability and the foreign key refuses — and that is
    # right: a downgrade must not orphan a registered cost in silence.
    op.execute("DELETE FROM ai.ai_capability_labels WHERE code = 'activity_drafting'")
    op.execute("DELETE FROM ai.ai_capability_codes WHERE code = 'activity_drafting'")
