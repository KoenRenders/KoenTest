"""Publiceer `home-intro` en `site-footer`, en haal de footer uit de navigatie (#727).

`is_published` gold niet voor deze twee blokken: `get_page()` haalde ze op ongeacht
de vlag, "voor blokken die de site zelf invult". Het beheerscherm toonde wél een
vinkje "Gepubliceerd" dat niets deed — uitzetten en er gebeurde niets.

De code laat de vlag nu wél gelden. Zonder deze migratie zouden de footer en de
home-intro dus **van de site verdwijnen**: op alle omgevingen staan die twee vandaag
op niet-gepubliceerd. Deze stap bewaart de huidige situatie.

**De tweede regel is geen detail.** Op PROD staat `site-footer` op
`show_in_nav = true`; dat viel nooit op, want de navigatie eist
`is_published AND show_in_nav` en het eerste was onwaar. Publiceer je de footer
zonder het tweede uit te zetten, dan verschijnt er een menu-item **"site-footer"**
in de publieke navigatie — het ene gerepareerd, het andere gebroken.

Beginsituatie op PROD, gemeten vóór deze migratie:

| slug | is_published | show_in_nav |
|---|---|---|
| home-intro | nee | nee |
| site-footer | nee | **ja** |

Idempotent en beperkt tot deze twee slugs: `WHERE` filtert op de slug en op de
kolomwaarde, dus een tweede run raakt geen enkele rij. Andere pagina's blijven
buiten schot — dit is geen algemene publicatieactie.
"""
from alembic import op

revision = "094"
down_revision = "093"
branch_labels = None
depends_on = None

SLUGS = ("home-intro", "site-footer")


def upgrade() -> None:
    op.execute(f"""
        UPDATE cms.cms_pages
           SET is_published = true
         WHERE slug IN {SLUGS}
           AND is_published IS DISTINCT FROM true
    """)
    # Alleen de footer: die hoort nergens als menu-item te staan. `home-intro` staat
    # op alle omgevingen al op false en wordt hier niet aangeraakt.
    op.execute("""
        UPDATE cms.cms_pages
           SET show_in_nav = false
         WHERE slug = 'site-footer'
           AND show_in_nav IS DISTINCT FROM false
    """)


def downgrade() -> None:
    # Terugdraaien zou de blokken van de site halen zonder de code mee terug te
    # draaien — dan is de footer weg en weet niemand waarom. Wie de oude toestand
    # wil, zet het vinkje uit op /admin/paginas; dat werkt sinds #727 ook echt.
    pass
