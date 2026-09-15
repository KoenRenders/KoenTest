"""${message}

Schrijf hier waarom deze migratie bestaat, niet wat ze doet: dat staat
hieronder al. Wie haar over een jaar leest, zoekt de reden.
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    # Herstelt deze downgrade ook de DATA, of alleen het schema? Zeg het
    # hardop. Een halve omkering die zich als een hele voordoet is erger dan een
    # die eerlijk is over wat ze niet doet.
    ${downgrades if downgrades else "pass"}
