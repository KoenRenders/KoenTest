"""the organisation kind ACCOUNT is called Account

The kind of an organisation is its role in the platform: the account that is
the customer, a unit under it, or the platform. The code list gave the code
`ACCOUNT` the word "Rechtspersoon" — a legal nature, not a role — while the
button above the list says "+ Nieuw account" and the approved concept of the
list says "Account" (#1945). Koen, 13 October 2026, to "Klopt het dat het label
"Account" wordt, in plaats van "Rechtspersoon"?": "2xja".

The word of a code lives in its label table, which migration 154 seeded (CR-12
phase 2) — so on a database that has the rows the word changes here, and in the
seed in `mdm/codes.py` for a database that is built from scratch. The stored
code stays `ACCOUNT`: no organisation, no row and no foreign key changes.
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
revision = "203_2026_10_13_093503"
down_revision = "202_2026_10_09_191828"
branch_labels = None
depends_on = None


#: language → (the word before, the word from now on)
WORDS = {"nl": ("Rechtspersoon", "Account"), "en": ("Legal entity", "Account")}


def reword(bind, old: int, new: int) -> None:
    """Replace the label of `ACCOUNT` per language — only where it still carries
    the word it is replaced from, so running it twice changes nothing and a
    word somebody else put there is left alone."""
    for language, words in WORDS.items():
        bind.execute(
            sa.text(
                "UPDATE mdm.organization_type_labels SET value = :new, updated_at = now() "
                "WHERE code = 'ACCOUNT' AND language = :language AND value = :old"
            ),
            {"language": language, "old": words[old], "new": words[new]},
        )


def upgrade() -> None:
    reword(op.get_bind(), 0, 1)


def downgrade() -> None:
    # Restores the data in full: the two labels get their former word back, and
    # nothing else was touched.
    reword(op.get_bind(), 1, 0)
