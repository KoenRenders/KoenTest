"""language codes carry the labels of every list

CR-12 phase 0. Every label table this change request builds is keyed on
``(code, language)``, so before the first list can exist there has to be a list
of languages — and a real one, with a foreign key, or the first ``nl_BE`` or
``NL`` typed into a label row becomes a label nobody ever reads while nothing
complains.

It lives in ``mdm`` because every domain uses it, which is the definition of
master data (§B4.1). That makes it the named exception to "no cross-schema
foreign keys": a label table in any schema points here. ``mdm`` depends on no
business domain, so the exception cannot create a cycle.

Language **codes**, not locales. The tenant setting stays ``nl_BE`` — it also
decides how a date reads — and the label lookup takes the language part of it.
Two rows today; a third language is a row plus a translator, not a release.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.mdm.codes import LANGUAGE_CODES
from app.kernel.codes import create_code_list


# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '151_2026_09_25_230812'
down_revision = '150_2026_09_21_224043'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The helper writes both tables in the one shape of §B4.2 and upserts the
    # rows, so the shape gate has nothing to argue about and a second run on a
    # second environment changes nothing.
    create_code_list(op, schema="mdm", name="language", codes=LANGUAGE_CODES,
                     code_length=5)


def downgrade() -> None:
    # Reverses the schema AND the data, because the only data here is the two
    # seed rows this migration wrote itself — there is no user content to lose.
    # Every other label table holds a foreign key to `language_codes`, so this
    # runs cleanly only once the lists above it are gone; alembic walks the
    # chain in that order.
    op.drop_table("language_labels", schema="mdm")
    op.drop_table("language_codes", schema="mdm")
