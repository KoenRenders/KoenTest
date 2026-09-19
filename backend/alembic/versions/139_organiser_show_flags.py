"""Een organisator kan zijn adres of nummer van de affiche houden (#1032).

`email_override` en `mobile_override` konden dat niet: leeg betekent daar "neem
de waarde uit de ledenfiche", niet "toon niets". Wie bereikbaar wil zijn op gsm
maar zijn privé-mailadres niet op een publiek affiche wil, had geen uitweg.

Twee vlaggen dus, en **standaard `true`**: dan verandert er niets aan wat er
vandaag gedrukt wordt, en is weglaten een bewuste handeling (Koen, 19 september
2026).

De volgorde die erbij hoort staat in de service: de override wint van de
ledenwaarde, en **pas daarna** beslist de vlag of er iets naar buiten gaat. Een
ingevulde override met het vinkje uit betekent dus: niets tonen.

Idempotent: elke kolom wordt alleen toegevoegd als ze ontbreekt.
"""
from alembic import op
import sqlalchemy as sa

revision = "139_2026_09_19_161615"
down_revision = "138_2026_09_19_183000"
branch_labels = None
depends_on = None

KOLOMMEN = ("show_email", "show_mobile")


def _has_column(kolom: str) -> bool:
    return bool(op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = 'activities' "
        "AND table_name = 'activity_organisers' AND column_name = :c"),
        {"c": kolom}).scalar())


def upgrade() -> None:
    for kolom in KOLOMMEN:
        if not _has_column(kolom):
            op.add_column("activity_organisers",
                          sa.Column(kolom, sa.Boolean, nullable=False,
                                    server_default=sa.true()),
                          schema="activities")


def downgrade() -> None:
    for kolom in KOLOMMEN:
        if _has_column(kolom):
            op.drop_column("activity_organisers", kolom, schema="activities")
