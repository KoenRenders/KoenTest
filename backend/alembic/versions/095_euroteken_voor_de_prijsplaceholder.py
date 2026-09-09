"""Haal het dubbele euroteken uit de home-intro (#807).

Op de publieke homepage stond **`€€35,00`**. De seedtekst zet een letterlijke `€`
vóór `{{membership_price_full}}`, en die placeholder levert sinds #579 zélf het
euroteken — "het symbool hoort hier en niet in de CMS-tekst: de placeholder levert
een volledig bedrag, zodat een redacteur `€` niet hoeft te typen (en niet kan
vergeten)". De tekst en de renderer spraken elkaar dus tegen, en de bezoeker zag het.

Gemeten vóór deze migratie:

| omgeving | pagina's met een letterlijke euro vóór een placeholder |
|---|---|
| PROD | 1 — `home-intro`, tenant 2 |
| UAT | 1 — `home-intro`, tenant 2 |
| HDEV | 0 (daar is de tekst ooit met de hand bewerkt) |

**Waarom een migratie en niet een correctie met de hand.** De tekst staat per
omgeving en per tenant in de databank, dus met de hand corrigeren lost één omgeving
op. Maar `027_seed_cms_blocks` en `028_cms_home_intro_placeholders` blijven seeden
zoals ze seeden — en een bestaande migratie wijzig je niet — dus elke verse omgeving
en elke nieuwe tenant zou opnieuw met `€€` beginnen. Deze stap draait ná 028: op een
bestaande databank corrigeert ze de rij die er staat, op een verse installatie draait
ze direct na de seed. Eén wijziging dekt beide gevallen.

**Precies genoeg, niet gulziger.** Het patroon eist dat de euro ONMIDDELLIJK vóór een
prijs-placeholder staat (spaties en een harde spatie ertussen toegestaan). Een `€`
elders in de tekst blijft staan — een redacteur mag dat gewoon typen, bijvoorbeeld in
"vanaf € 5 per deelnemer". Daar staat een eigen test op, en dat is de test die
ertoe doet: zonder haar is een te gulzige migratie niet te onderscheiden van een die
het goed doet.

Idempotent: na de eerste run staat er geen euro meer vóór de placeholder, dus een
tweede run vindt niets. De `WHERE` beperkt bovendien tot de rijen die het patroon
echt bevatten.
"""
from alembic import op

revision = "095"
down_revision = "094"
branch_labels = None
depends_on = None

# Zowel `{{membership_price_full}}` als de half-variant, met of zonder spaties in de
# accolades. `\s*` en `&nbsp;` ertussen: een redacteur die "€ {{…}}" typt heeft
# hetzelfde probleem, en een harde spatie is in een WYSIWYG-veld doodnormaal.
PATROON = r'€(\s|&nbsp;)*(\{\{\s*membership_price_(full|half)\s*\}\})'


def schoon_sql(tabel: str = "cms.cms_pages") -> str:
    """De opschoning als losse SQL, zodat een test haar op een eigen rij kan draaien.

    Een migratie draait in de suite vóór er data is, dus wat ze met een bestaande
    tekst doet is anders niet te toetsen — en een datastap die stil niets doet, laat
    precies de rijen staan waarvoor ze geschreven is.
    """
    return f"""
        UPDATE {tabel}
           SET content = regexp_replace(content, '{PATROON}', '\\2', 'g')
         WHERE content ~ '{PATROON}'
    """


def upgrade() -> None:
    op.execute(schoon_sql())


def downgrade() -> None:
    # Het euroteken terugzetten zou de fout herstellen die we net weghalen. Wie de
    # oude tekst wil, bewerkt de pagina op /admin/paginas.
    pass
