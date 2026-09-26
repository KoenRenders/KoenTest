"""${message}

Write here why this migration exists, not what it does: the code below
already says that. Whoever reads it a year from now is looking for the reason.
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    # Does this downgrade restore the DATA too, or only the schema? Say so out
    # loud. A partial reversal that passes itself off as a whole one is worse
    # than one that is honest about what it does not do.
    ${downgrades if downgrades else "pass"}
