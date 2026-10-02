"""target audience families becomes everyone (#1451)

Koen, 2 October 2026: the target audience "Gezinnen" (code `families`) is
"Iedereen". The code changes, not only the label — a code `families` labelled
"Iedereen" is the mismatch that confuses the next reader. So a new code
`everyone` takes the old one's place in the list (sort_order 10), every
activity that had `families` moves to it, and `families` leaves the list.

The order is the foreign key's: `activities.activities.target_audience` points
at `activities.target_audience_codes.code`, so the new code exists before an
activity points at it, and the old one is deleted only when nothing points at
it any more. The repoint covers every row, soft-deleted ones included: a
foreign key does not know `deleted_at`. No CHECK stands on the column (migration
180 checked, and none was added since).

The reporting views read the label through the code
(`target_audience_labels`), and no seeded report names the code or the label,
so nothing else follows.

Idempotent: the insert skips an existing code or label, the repoint and the
delete touch nothing on a second run. On a fresh database migration 180 already
seeds `everyone` (it reads the list from `codes.py`), and this one then finds
nothing to move.
"""

import sqlalchemy as sa
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
revision = "184_2026_10_02_045500"
down_revision = "183_2026_10_01_150044"
branch_labels = None
depends_on = None

CODES = "activities.target_audience_codes"
LABELS = "activities.target_audience_labels"


def _swap(old: str, new: str, labels: dict[str, str]) -> None:
    """Insert `new`, move every activity from `old` to it, delete `old`."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"INSERT INTO {CODES} (code, sort_order, is_active) "
            "VALUES (:code, 10, true) ON CONFLICT (code) DO NOTHING"
        ),
        {"code": new},
    )
    for language, value in labels.items():
        bind.execute(
            sa.text(
                f"INSERT INTO {LABELS} (code, language, value) "
                "VALUES (:code, :language, :value) ON CONFLICT (code, language) DO NOTHING"
            ),
            {"code": new, "language": language, "value": value},
        )
    bind.execute(
        sa.text(
            "UPDATE activities.activities SET target_audience = :new WHERE target_audience = :old"
        ),
        {"new": new, "old": old},
    )
    bind.execute(sa.text(f"DELETE FROM {LABELS} WHERE code = :old"), {"old": old})
    bind.execute(sa.text(f"DELETE FROM {CODES} WHERE code = :old"), {"old": old})


def upgrade() -> None:
    _swap("families", "everyone", {"nl": "Iedereen", "en": "Everyone"})


def downgrade() -> None:
    # The data comes back as far as it can: every activity on `everyone` goes to
    # `families` — also one that was set to "Iedereen" after the upgrade, since
    # the two cannot be told apart then.
    _swap("everyone", "families", {"nl": "Gezinnen", "en": "Families"})
