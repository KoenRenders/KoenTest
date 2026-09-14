"""MDM (#924, derde omschakeling): de contactgegevens komen uit de organisatie.

Koen, na het bekijken van HDEV: *"volgens mij is dat een contactblok in de
footer-pagina"* en *"op privacy pagina staat naam, adres, mailadres ook,
mailadres zelfs meermaals. Dat mag ook vervangen worden."*

Er is geen contactpagina — nagemeten op HDEV: `home-intro`, `kerstradio`,
`privacy`, `site-footer`, `werking`. Wat er wél is sinds omschakeling 2, is een
footer die alles dubbel toont: bovenaan het blok uit de organisatie, eronder de
oude CMS-tekst met dezelfde naam, hetzelfde adres, hetzelfde rekeningnummer. Dat
was toen de juiste keuze — een migratie kan een adresblok niet van vrije tekst
onderscheiden, dus de vraag werd uitgesteld tot iemand naar een echte omgeving
keek. Dat is gebeurd, en dit is het antwoord.

**Dit is de enige stap in de reeks die bestaande tekst WEGHAALT.** Bij de eerste
twee stond de oude bron in een instellingenscherm; hier staat ze in een pagina die
Koen zelf geschreven heeft. Vandaar de vorm van de opruiming:

- **Per blok en niet per voorkomen.** Een e-mailadres staat in een link twee keer —
  één keer in `mailto:` en één keer als linktekst — dus tellen en vervangen breekt
  de link. Er wordt gekeken naar wat een alinea *is*, niet naar hoe vaak er iets in
  staat.
- **Alleen alinea's die niets ánders bevatten.** Haal de bekende waarden en hun
  etiketten weg; blijft er nog tekst over, dan blijft de alinea staan. Een
  achtergebleven zin is een schoonheidsfoutje; een weggegooide alinea van Koen is
  dat niet.
- **Koppen blijven altijd.** Een `<h2>` met de naam van de vereniging erin is een
  titel, geen contactregel.
- **Idempotent**: na de eerste run staan de waarden er niet meer, dus een tweede
  run herkent niets en verandert niets.
"""
import html
import re

import sqlalchemy as sa
from alembic import op

revision = "121"
down_revision = "120"
branch_labels = None
depends_on = None

SLUGS = ("site-footer", "privacy")

# Etiketten die om de waarden heen staan. Ze tellen niet mee als "eigen tekst":
# een alinea die alleen "E-mail: bestuur@..." is, is een contactregel.
ETIKETTEN = ("e-mail", "email", "mail", "adres", "telefoon", "tel", "gsm",
             "rekeningnummer", "rekening", "iban", "bic", "btw",
             "ondernemingsnummer", "website", "contact", "vzw",
             "feitelijke vereniging", "bedrijf")

BLOK = re.compile(r"<(p|div)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def _kale_tekst(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment))


def _rest_na_de_waarden(tekst: str, waarden: list[str]) -> str:
    """Wat er van een alinea overblijft als je de contactgegevens wegdenkt."""
    rest = tekst.lower()
    # Langste eerst, en dat is geen netheid maar een reparatie. "Raak Voorbeeld"
    # zonder spaties zit ín "bestuur@raakvoorbeeld.example": wie de korte waarde
    # eerst wegneemt, houdt "bestuur@.example" over en herkent het e-mailadres
    # daarna niet meer. De alinea bleef dan staan — de veilige kant op, maar wel fout.
    for waarde in sorted(waarden, key=len, reverse=True):
        if not waarde:
            continue
        rest = rest.replace(waarde.lower(), " ")
        # Een IBAN wordt met en zonder spaties geschreven; beide vormen tellen.
        compact = waarde.replace(" ", "").lower()
        if len(compact) > 6:
            rest = rest.replace(compact, " ")
    for etiket in ETIKETTEN:
        rest = rest.replace(etiket, " ")
    return re.sub(r"[^a-z0-9]", "", rest)


def _opgeruimd(content: str, waarden: list[str]) -> str:
    """Blokken die enkel contactgegevens zijn, verdwijnen. De rest blijft."""
    def vervang(match: re.Match) -> str:
        tekst = _kale_tekst(match.group(0))
        if not _rest_na_de_waarden(tekst, waarden).strip():
            return ""
        return match.group(0)

    return BLOK.sub(vervang, content)


def upgrade() -> None:
    op.add_column("organizations", sa.Column("payment_bic", sa.String(20),
                                             nullable=True), schema="mdm")

    bind = op.get_bind()
    organisaties = bind.execute(sa.text(
        "SELECT o.id, o.name, o.email, o.phone, o.payment_iban, o.payment_bic, "
        "       a.street, a.house_number, a.bus_number, p.postal_code, "
        "       p.municipality "
        "FROM mdm.organizations o "
        "LEFT JOIN mdm.addresses a ON a.organization_id = o.id "
        "                         AND a.deleted_at IS NULL "
        "LEFT JOIN mdm.postal_codes p ON p.id = a.postal_code_id "
        "WHERE o.deleted_at IS NULL")).mappings().all()

    opgeruimd = 0
    for rij in organisaties:
        waarden = [rij["name"], rij["email"], rij["phone"], rij["payment_iban"],
                   rij["payment_bic"]]
        if rij["street"]:
            nummer = f"{rij['street']} {rij['house_number']}"
            waarden += [nummer, rij["street"]]
            if rij["bus_number"]:
                waarden.append(f"{nummer} bus {rij['bus_number']}")
        if rij["postal_code"]:
            waarden += [f"{rij['postal_code']} {rij['municipality']}",
                        rij["municipality"]]
        waarden = [w for w in waarden if w]
        if not waarden:
            continue
        for slug in SLUGS:
            pagina = bind.execute(sa.text(
                "SELECT id, content FROM cms.cms_pages "
                "WHERE slug = :slug AND tenant_id = :t"),
                {"slug": slug, "t": rij["id"]}).mappings().first()
            if pagina is None or not pagina["content"]:
                continue
            nieuw = _opgeruimd(pagina["content"], waarden)
            if nieuw != pagina["content"]:
                bind.execute(sa.text(
                    "UPDATE cms.cms_pages SET content = :c, updated_at = now() "
                    "WHERE id = :id"), {"c": nieuw, "id": pagina["id"]})
                opgeruimd += 1
    print(f"  #924: {opgeruimd} pagina('s) ontdubbeld; de contactgegevens komen "
          "voortaan uit de organisatie.")


def downgrade() -> None:
    # De weggehaalde tekst komt niet terug: ze staat nu in de organisatie. Wie
    # terug wil, zet de kolommen om in tekst — dat is een keuze en geen omkering.
    op.drop_column("organizations", "payment_bic", schema="mdm")
