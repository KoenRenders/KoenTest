"""one main member per household

A household has one main member. The rule lives in the service
(`require_one_main_member`, #1821) and since #1832 the member import does not
load an address group that would break it. This constraint is the last net
under both: a writer that forgets to ask, or two requests at the same moment,
cannot leave a household with two.

An exclusion constraint and not a unique index, because it is checked when the
transaction ends (`DEFERRABLE INITIALLY DEFERRED`) and an index is checked at
every statement. Measured while building: the member import passes through two
main members on its way to a right end state — the report puts a new main
member in front of the old one and makes the old one a partner, or the old
main member moves out in a later address group. An index refused those runs
half-way; what must hold is what is committed.

It counts the living links only (`deleted_at IS NULL`). A softly deleted link
is a link that is gone: a household whose main member was removed gets a new
one, and the old row may not stand in his way. The other side of that choice
is deliberate too — bringing a deleted main member's link back while the
household has another is refused by the database.

Measured before this migration was written (9 October 2026, counts only, on
every environment): no household with more than one main-member link, neither
among the living links nor with the softly deleted ones counted in. Should an
environment hold one all the same, adding the constraint fails on it and the
deploy stops there: give that household one main member first.
"""

from alembic import op

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
revision = "200_2026_10_09_070019"
down_revision = "199_2026_10_09_034931"
branch_labels = None
depends_on = None

CONSTRAINT = "ex_member_persons_one_main_member"


def upgrade() -> None:
    # Idempotent: dropped first, so a second run ends where the first did.
    op.execute(f"ALTER TABLE mdm.member_persons DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
    op.execute(
        f"ALTER TABLE mdm.member_persons ADD CONSTRAINT {CONSTRAINT} "
        f"EXCLUDE (member_id WITH =) "
        f"WHERE (relation_type = 'HOOFDLID' AND deleted_at IS NULL) "
        f"DEFERRABLE INITIALLY DEFERRED"
    )


def downgrade() -> None:
    # Schema only, and that is the whole of it: the constraint holds no data.
    op.execute(f"ALTER TABLE mdm.member_persons DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
