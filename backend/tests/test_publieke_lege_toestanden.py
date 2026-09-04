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


def test_fotos_zonder_albums_toont_de_lege_toestand(client):
    r = client.get("/fotos")

    assert r.status_code == 200
    assert "Nog geen fotoalbums beschikbaar." in r.text
    assert "italic" not in r.text, "lege toestand mag niet schuin (§2.11)"


def test_album_zonder_fotos_toont_de_lege_toestand(client, db_session):
    from app.domains.activities.api import Activity

    activiteit = Activity(name="Album zonder foto's")
    db_session.add(activiteit)
    db_session.commit()

    r = client.get(f"/activiteiten/{activiteit.id}/fotos")

    assert r.status_code == 200
    assert "Geen foto's gevonden voor deze activiteit." in r.text
    assert "italic" not in r.text, "lege toestand mag niet schuin (§2.11)"


def test_beide_schermen_gebruiken_dezelfde_macro(client, db_session):
    """Niet alleen de tekst: de opmaak moet die van de kit zijn, zodat een lege
    lijst er overal hetzelfde uitziet."""
    from app.domains.activities.api import Activity

    activiteit = Activity(name="Nog een album")
    db_session.add(activiteit)
    db_session.commit()

    for pad in ("/fotos", f"/activiteiten/{activiteit.id}/fotos"):
        r = client.get(pad)
        # De markup van ui.empty_state(): gedempt, klein, gecentreerd.
        assert 'class="text-gray-500 text-sm py-6 text-center"' in r.text, pad
