"""Lege toestanden op de publieke fotoschermen (#637).

De render-gate (#622) dekt de beheerpagina's; deze twee schermen zijn publiek en
vielen erbuiten. Ze schreven hun lege toestand met de hand én in italic — §2.11
verbiedt allebei: één `Empty`-component, niet schuin. De templates importeerden
`_macros.html` zelfs niet, dus dit was niet vergeten maar nooit aangesloten.

De test rendert ze zónder data, want dat is precies de toestand die niemand
handmatig bekijkt.
"""
import pytest

pytestmark = pytest.mark.ui_serverrendered

# De markup van ui.empty_state(): gedempt, klein, gecentreerd — en niet schuin.
LEGE_TOESTAND = 'class="text-gray-500 text-sm py-6 text-center"'


def _schuine_lege_toestand(html: str) -> bool:
    """Staat er een schuine lege-toestandregel op de pagina?

    Niet simpelweg `"italic" not in html`: de publieke schil draagt in haar
    inline-CSS `.cms-content em,.cms-content i{font-style:italic}` — dat is
    gewone cursieve tekst in CMS-inhoud, geen lege toestand. We kijken dus naar
    de combinatie op één regel, net als de lint-gate.
    """
    return any("italic" in regel and ("Geen " in regel or "Nog geen " in regel)
               for regel in html.splitlines())


def test_fotos_zonder_albums_toont_de_lege_toestand(client):
    r = client.get("/fotos")

    assert r.status_code == 200
    assert LEGE_TOESTAND in r.text, "de lege toestand komt niet uit ui.empty_state()"
    assert "Nog geen fotoalbums beschikbaar." in r.text
    assert not _schuine_lege_toestand(r.text), "lege toestand mag niet schuin (§2.11)"


def test_album_zonder_fotos_toont_de_lege_toestand(client, db_session):
    from app.domains.activities.api import Activity

    activiteit = Activity(name="Album zonder foto's")
    db_session.add(activiteit)
    db_session.commit()

    r = client.get(f"/activiteiten/{activiteit.id}/fotos")

    assert r.status_code == 200
    assert LEGE_TOESTAND in r.text, "de lege toestand komt niet uit ui.empty_state()"
    assert "Geen foto's gevonden voor deze activiteit." in r.text
    assert not _schuine_lege_toestand(r.text), "lege toestand mag niet schuin (§2.11)"


def test_beide_schermen_gebruiken_dezelfde_macro(client, db_session):
    """Niet alleen de tekst: de opmaak moet die van de kit zijn, zodat een lege
    lijst er overal hetzelfde uitziet."""
    from app.domains.activities.api import Activity

    activiteit = Activity(name="Nog een album")
    db_session.add(activiteit)
    db_session.commit()

    for pad in ("/fotos", f"/activiteiten/{activiteit.id}/fotos"):
        assert LEGE_TOESTAND in client.get(pad).text, pad
