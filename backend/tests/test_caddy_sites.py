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

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `prod-backend`
teruggezet op `prod-frontend` → de eerste valt om; een `{$NIEUW_DOMAIN}`-blok
toegevoegd zonder regel in het voorbeeldbestand → de tweede.
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


def test_de_platformblokken_staan_er_nog_niet_in():
    """#572 — bewust weggelaten, en met een reden die in het bestand hoort te staan.

    De twee platform-namen zijn doorstuurrecords die niet naar deze server wijzen.
    Een site-blok ervoor levert ACME-aanvragen op die nooit kunnen slagen, eindeloos
    herhaald, tot Let's Encrypt gaat rate-limiten — en dat raakt dan ook de
    certificaten van de sites die het wél doen.

    De verleiding is groot om ze "even" terug te halen uit commit `e375866`, waar ze
    in staan. Deze test is de rem, en het commentaar in het bestand legt uit waarom.
    """
    config = _zonder_commentaar(PROD)

    assert "PLATFORM_DOMAIN" not in config and "PLATFORM_WWW_DOMAIN" not in config, (
        "de platform-blokken staan live terwijl hun DNS niet hierheen wijst")
    assert "rate-limiting" in PROD or "rate-limit" in PROD, (
        "de reden staat niet in het bestand; dan haalt de volgende ze gewoon terug")
