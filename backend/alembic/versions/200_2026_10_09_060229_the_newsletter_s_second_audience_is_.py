"""the newsletter's second audience is called Abonnees

The newsletter knows two lists: the members of the working year, and the people
who subscribed and confirmed. The second was called "Niet-leden" where a letter's
audience is chosen and listed, and "Abonnees" on the send screen, on the
subscribers' screen and at the public sign-up — two words for one list (#1834).
Koen, 9 October 2026, asked whether "Abonnees" is the word: "Abonnees is goed".
It says who they are, where "Niet-leden" said only who they are not.

The word of a code lives in its label table, which a migration seeded (CR-12
phase 3) — so the word changes here, and in the seed in `newsletter/codes.py`
for a database that is built from scratch. The stored code stays `non_members`:
no letter, no row and no foreign key changes.
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
revision = "200_2026_10_09_060229"
down_revision = "200_2026_10_09_070019"
branch_labels = None
depends_on = None

#: language → (the word before, the word from now on)
WORDS = {"nl": ("Niet-leden", "Abonnees"), "en": ("Non-members", "Subscribers")}


def reword(bind, old: int, new: int) -> None:
    """Replace the label of `non_members` per language — only where it still
    carries the word it is replaced from, so running it twice changes nothing
    and a word somebody else put there is left alone."""
    for language, words in WORDS.items():
        bind.execute(
            sa.text(
                "UPDATE newsletter.audience_labels SET value = :new, updated_at = now() "
                "WHERE code = 'non_members' AND language = :language AND value = :old"
            ),
            {"language": language, "old": words[old], "new": words[new]},
        )


def upgrade() -> None:
    reword(op.get_bind(), 0, 1)


def downgrade() -> None:
    # Restores the data in full: the two labels get their former word back, and
    # nothing else was touched.
    reword(op.get_bind(), 1, 0)
