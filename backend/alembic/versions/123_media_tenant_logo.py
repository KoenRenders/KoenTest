"""Mediasoort `tenant_logo` (#258): het logo van de vereniging zelf.

De vergader-PDF zette tot nu het woordmerk als tekst in zijn kop. Koen, bij het
nakijken van het eerste echte verslag: *"De Raak zou ik uit een logo nemen."*

Een mediasoort en geen tenant-instelling: een logo is bytes, en die horen waar de
andere bytes al staan — met dezelfde upload, dezelfde back-up en dezelfde
bibliotheek. De instellingenschermen bewaren sleutel-waardeparen en zouden voor
één binair veld een bestandsupload moeten leren.

Een eigen migratie en géén aanpassing van 122: 122 is misschien al gedraaid op een
omgeving waar dit spoor getest wordt, en een migratie die al ergens liep, wijzig
je niet meer — dan zou de verruiming daar nooit toegepast worden.
"""
from alembic import op

revision = "123"
down_revision = "122"
branch_labels = None
depends_on = None

_KINDS_NEW = ("kind IN ('sponsor','activity_photo','activity_poster',"
              "'component_info','tenant_logo')")
_KINDS_OLD = ("kind IN ('sponsor','activity_photo','activity_poster',"
              "'component_info')")


def upgrade() -> None:
    op.drop_constraint("ck_media_assets_kind_valid", "media_assets",
                       type_="check", schema="media")
    op.create_check_constraint("ck_media_assets_kind_valid", "media_assets",
                               _KINDS_NEW, schema="media")


def downgrade() -> None:
    # Eerst de rijen weg die de oude CHECK niet zou toelaten; anders faalt het
    # terugdraaien op een omgeving waar al een logo staat.
    op.execute("DELETE FROM media.media_assets WHERE kind = 'tenant_logo'")
    op.drop_constraint("ck_media_assets_kind_valid", "media_assets",
                       type_="check", schema="media")
    op.create_check_constraint("ck_media_assets_kind_valid", "media_assets",
                               _KINDS_OLD, schema="media")
