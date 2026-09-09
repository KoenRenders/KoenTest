"""De gedeelde Caddy-config: PROD-routing en de domeinvariabelen (#572).

Twee dingen die niet stil mogen terugkomen, allebei met een prijskaartje dat we
kennen.

**De routing.** Tijdens de v1.14→v2.0-cutover stond PROD hier bewust nog op
`prod-frontend:3000` (de expand-fase), omdat één gedeelde Caddy UAT én PROD bedient
en die twee tijdelijk op verschillende versies stonden. Sinds de contract-stap gaat
alles naar `prod-backend:8000` en bestaat de frontend-container niet meer. Komt die
verwijzing terug, dan proxyt Caddy naar een container die er niet is en is PROD weg.

**De variabelen.** Een `{$VAR}` die niet in `.env.caddy` op de server staat, expandeert
tot een LEEG site-adres, en dan is de hele gedeelde config ongeldig — Caddy start dan
niet meer op, mét PROD erin. Dat is niet hypothetisch: `PLATFORM_DOMAIN` en
`PLATFORM_WWW_DOMAIN` (#406) stonden op master terwijl ze op de server ontbraken.
Deze test kan niet in de `.env.caddy` van de server kijken, maar wel afdwingen dat elke
gebruikte variabele in `.env.caddy.example` gedocumenteerd staat — dat is de lijst die
iemand naast de server legt.

Sinds #801 staan de platform-blokken er wél in — één naam per omgeving, allebei
subdomeinen die naar deze server wijzen. De guard is daarom omgekeerd: van "ze mogen
er niet in" naar "ze staan er, met hun variabele gedocumenteerd". Weglaten zou de
bescherming hebben weggenomen die voorkomt dat een variabele zonder waarde de config
ongeldig maakt.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `prod-backend`
teruggezet op `prod-frontend`; een `{$NIEUW_DOMAIN}`-blok zonder regel in het
voorbeeldbestand; `{$PLATFORM_PROD_DOMAIN}` vervangen door het omgevingsloze
`{$PLATFORM_DOMAIN}`; en `PLATFORM_WWW_DOMAIN` terug in het voorbeeldbestand.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
CADDY = ROOT / "caddy"
PROD = (CADDY / "parts" / "sites-prod.caddy").read_text()
VOORBEELD = (ROOT / ".env.caddy.example").read_text()


def _zonder_commentaar(tekst: str) -> str:
    """Commentaarregels eruit: daarin staan variabelen die (nog) niet live zijn."""
    return "\n".join(r for r in tekst.splitlines() if not r.lstrip().startswith("#"))


def test_prod_gaat_rechtstreeks_naar_de_backend():
    """De contract-stap, en de expand-vorm mag niet terugkomen."""
    config = _zonder_commentaar(PROD)

    assert "reverse_proxy prod-backend:8000" in config
    assert "prod-frontend" not in config, (
        "PROD wordt weer naar de frontend-container gestuurd; die bestaat niet meer "
        "sinds de React-exit (#405) en de site valt dan stil")


def test_elke_domeinvariabele_staat_in_het_voorbeeldbestand():
    """Anders bereikt een nieuwe variabele de server zonder dat iemand het merkt.

    De prijs van vergeten is niet "dat ene domein doet het niet" maar "Caddy start
    niet op", want een leeg site-adres maakt de héle config ongeldig — inclusief de
    sites die er niets mee te maken hebben.
    """
    bestanden = list((CADDY / "parts").glob("*.caddy")) + [CADDY / "Caddyfile.shared"]
    assert len(bestanden) >= 4, f"de glob vindt te weinig bestanden: {bestanden}"

    gebruikt = set()
    for pad in bestanden:
        gebruikt |= set(re.findall(r"\{\$([A-Z_]+)\}", _zonder_commentaar(pad.read_text())))
    assert gebruikt, "er wordt geen enkele variabele gevonden — kijkt deze test wel ergens?"

    ontbreekt = sorted(v for v in gebruikt if not re.search(rf"^{v}=", VOORBEELD, re.M))
    assert not ontbreekt, (
        "deze variabelen staan in de Caddy-config maar niet in .env.caddy.example, "
        f"dus niemand weet dat ze op de server moeten staan: {ontbreekt}")


def test_het_platform_heeft_een_eigen_naam_per_omgeving():
    """#801 — de blokken mochten landen zodra hun DNS naar deze server wees.

    Twee namen, niet één: zo is het platform op UAT te bekijken vóór PROD volgt,
    terwijl beide blokken in dezelfde tag zitten. Eén naam zonder omgeving náást een
    naam mét zou de val zijn — dan is `PLATFORM_DOMAIN` "de prod-variant, behalve
    als je aan UAT denkt".

    Géén www-variant: het zijn subdomeinen, dus die vorm bestaat niet (gecontroleerd
    vanaf de server: ze resolveert niet). De variabele is dáárom verdwenen en niet
    leeggezet — zie de test hieronder.
    """
    uat = _zonder_commentaar((CADDY / "parts" / "sites-uat.caddy").read_text())
    prod = _zonder_commentaar(PROD)

    assert "{$PLATFORM_UAT_DOMAIN}" in uat and "uat-backend:8000" in uat
    assert "{$PLATFORM_PROD_DOMAIN}" in prod and "prod-backend:8000" in prod
    assert "{$PLATFORM_DOMAIN}" not in uat + prod, (
        "de omgevingsloze naam is terug; dan is niet meer te zien welke omgeving "
        "hij bedient")


def test_er_is_geen_www_variabele_meer_voor_het_platform():
    """De reden staat in het bestand en hoort er te blijven staan.

    Een blok uitschakelen door zijn variabele leeg te laten is precies wat je hier
    NIET moet doen: een lege waarde expandeert tot een leeg site-adres en maakt de
    hele gedeelde config ongeldig. Gemeten met `caddy validate`: "server block
    without any key is global configuration". Weg is veilig, leeg is fataal — en dat
    onderscheid moet in het bestand staan, niet alleen in een issue.
    """
    # Zonder commentaar: het bestand mag de naam wél NOEMEN om uit te leggen waarom
    # ze weg is. Wat niet mag, is een blok dat haar nog gebruikt.
    alles = "".join(_zonder_commentaar((CADDY / "parts" / f).read_text())
                    for f in ("sites-uat.caddy", "sites-prod.caddy"))

    assert "PLATFORM_WWW_DOMAIN" not in alles
    assert "PLATFORM_WWW_DOMAIN" not in VOORBEELD, (
        "de variabele staat nog in .env.caddy.example terwijl geen enkel blok haar "
        "gebruikt — dan zet iemand haar op de server en denkt dat het iets doet")
    assert "leeg is fataal" in PROD, (
        "de reden waarom je zo'n variabele niet leegzet staat niet in het bestand")
