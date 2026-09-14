"""MDM (#924, tweede omschakeling): de footer leest de organisatie.

De sociale links stonden in `kernel_tenant_settings`. Ze horen bij de organisatie
— de beslisregel uit het issue: *zou dit nog waar zijn als de organisatie geen
website had?* Een Facebook-pagina van een vereniging bestaat los van haar site, dus
ja.

**De rijen verhuizen en verdwijnen**, net als de betaalgegevens in migratie 119.
Blijven ze staan "voor het geval dat", dan is er een tweede bewerkbare bron gebouwd
in plaats van er één weggenomen.

**Aan het CMS-blok wordt niet geraakt, en dat is met opzet.** `site-footer` is een
vrije CMS-pagina: een migratie kan een adresblok niet onderscheiden van een zin die
iemand geschreven heeft. Het organisatieblok wordt uit de entiteit gerenderd en wat
de tenant schreef blijft eronder staan — dan verdwijnt er bij de deploy niets. Of
dat blok daarna weg mag, is een beslissing ná het bekijken van een omgeving en niet
iets wat een migratie blind kan nemen.
"""
import sqlalchemy as sa
from alembic import op

revision = "120"
down_revision = "119"
branch_labels = None
depends_on = None

SLEUTELS = ("facebook_url", "instagram_url", "tiktok_url")


def upgrade() -> None:
    bind = op.get_bind()
    for sleutel in SLEUTELS:
        bind.execute(sa.text(
            f"UPDATE mdm.organizations o SET {sleutel} = s.value "
            "FROM kernel_tenant_settings s "
            "WHERE s.tenant_id = o.id AND s.key = :k "
            "  AND COALESCE(s.value, '') <> ''"), {"k": sleutel})
    verplaatst = bind.execute(sa.text(
        "SELECT COUNT(*) FROM kernel_tenant_settings WHERE key = ANY(:k)"),
        {"k": list(SLEUTELS)}).scalar()
    bind.execute(sa.text(
        "DELETE FROM kernel_tenant_settings WHERE key = ANY(:k)"),
        {"k": list(SLEUTELS)})
    print(f"  #924: {verplaatst} sociale link(s) verhuisd naar de organisatie "
          "en uit kernel_tenant_settings verwijderd.")


def downgrade() -> None:
    pass
