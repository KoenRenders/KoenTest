"""${message}

Write here why this migration exists, not what it does: the code below
already says that. Whoever reads it a year from now is looking for the reason.
"""

import sqlalchemy as sa
from alembic import op
% if imports:
${imports}
% endif

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
revision = ${repr(up_revision).replace("'", '"')}
down_revision = ${repr(down_revision).replace("'", '"')}
branch_labels = ${repr(branch_labels).replace("'", '"')}
depends_on = ${repr(depends_on).replace("'", '"')}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    # Does this downgrade restore the DATA too, or only the schema? Say so out
    # loud. A partial reversal that passes itself off as a whole one is worse
    # than one that is honest about what it does not do.
    ${downgrades if downgrades else "pass"}
