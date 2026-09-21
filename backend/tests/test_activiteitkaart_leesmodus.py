"""#1139: de activiteitkaart toont in leesmodus wat ze bevat.

Tot deze wijziging toonde die kaart in leesmodus precies één ding: een
verwijzing naar de affiche, of de zin dat er nog geen affiche is. Al het
andere zat in het formulier eronder achter `x-show="edit"`, dus je zag de
omschrijving en de interne nota alleen terwijl je ze bewerkte. Koens
schermafdruk: een kaart met een titel, een knop en één zin.

**Waarom deze tests op het LEESDEEL kijken en niet op de hele pagina.** De
omschrijving stond altijd al in het antwoord — als `value` van een invoerveld
in de bewerkvorm. Een test die `"tekst" in resp.text` doet, staat dus groen
zonder dat er iets in leesmodus zichtbaar is. Dat is precies hoe dit zo lang
kon blijven staan, en het is de reden dat `_leesdeel()` hieronder knipt.
"""
from __future__ import annotations

import pytest

from app.domains.activities.api import Activity
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

OMSCHRIJVING = "Twee dagen wandelen langs de Nete, met soep onderweg."
NOTA = "Sleutel van de zaal ligt bij de buur. Frigobox meenemen."


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


@pytest.fixture
def activiteit(db_session):
    act = Activity(name="Neteroute", location="Millegem")
    db_session.add(act)
    db_session.commit()
    return act


def _kaart(client, activiteit) -> str:
    respons = client.get(f"/admin/activiteiten/{activiteit.id}")
    assert respons.status_code == 200
    return respons.text


def _leesdeel(html: str) -> str:
    """Het deel van de activiteitkaart dat in leesmodus zichtbaar is.

    Geknipt vóór `<form id="aa-act-form"`, de bewerkvorm met `x-show="edit"`.
    Wat daarna komt ziet de gebruiker pas na een klik op Bewerken.

    De twee asserties zijn er omdat een knipfunctie die niets vindt een lege
    string teruggeeft — en dan slaagt élke "staat er niet in"-assertie zonder
    dat er iets gemeten is.
    """
    merk = '<form id="aa-act-form"'
    assert merk in html, "de bewerkvorm staat niet in het antwoord; knippen heeft geen zin"
    lees = html.split(merk)[0]
    assert "Activiteit</h2>" in lees, "het leesdeel bevat de kaartkop niet — verkeerd geknipt"
    return lees


# ── 1. De kaart toont wat ze bevat ──────────────────────────────────────────

def test_description_and_internal_note_are_visible_without_clicking(
        client, db_session, activiteit):
    """Het gemelde geval.

    Tegenproef: de twee leesregels uit `_aa_detail.html` gehaald → beide
    asserties falen. Tegelijk bleef `OMSCHRIJVING in html` (dus zónder knippen)
    gewoon waar, want de tekst staat als `value` in de bewerkvorm — dat is de
    test die dit issue niet zou hebben gevonden.
    """
    activiteit.description = OMSCHRIJVING
    activiteit.board_notes = NOTA
    db_session.commit()
    _login(client)

    lees = _leesdeel(_kaart(client, activiteit))
    assert OMSCHRIJVING in lees, "de omschrijving staat niet in de leesweergave"
    assert NOTA in lees, "de interne nota staat niet in de leesweergave"


def test_the_internal_note_is_recognisably_internal_in_read_mode(
        client, db_session, activiteit):
    """De nota mag niet als gewone tekst tussen de rest staan.

    Het veld bestaat omdat de oude `notes`-kolom stil publiek uitleesbaar bleek
    (#1028). Wie de kaart leest, beslist of hij iets doorvertelt — dus staat de
    belofte er ook in leesmodus bij, met dezelfde woorden als bij het veld.
    """
    activiteit.board_notes = NOTA
    db_session.commit()
    _login(client)

    lees = _leesdeel(_kaart(client, activiteit))
    assert "Interne nota" in lees
    assert "Alleen het bestuur ziet dit" in lees, (
        "de leesweergave zegt niet dat deze tekst intern is")


def test_the_promise_about_the_internal_note_lives_in_one_place():
    """Die belofte staat nu op twee schermplaatsen, dus op één plek in de bron.

    #1077 heeft de tekst al een keer moeten bijstellen — "niet in een export"
    werd onwaar toen het veld in de rapportering kwam. Met twee kopieën vergeet
    de volgende bijstelling er één, en dan belooft het scherm iets wat niet meer
    klopt. Dat is erger dan geen belofte, want dit veld bestaat juist om zo'n
    stilzwijgend lek te voorkomen.

    Rood bewezen door de zin een tweede keer letterlijk in het sjabloon te
    zetten: de test faalde met 2.
    """
    from pathlib import Path

    tekst = (Path(__file__).resolve().parents[1] / "app" / "domains" / "activities"
             / "templates" / "_aa_detail.html").read_text()
    zin = "Alleen het bestuur ziet dit"
    aantal = tekst.count(zin)
    assert aantal == 1, (
        f"de belofte staat {aantal}x letterlijk in het sjabloon; leid de tweede "
        "plek af uit INTERNE_NOTA_BELOFTE in plaats van hem te herhalen")


# ── 2. Leeg blijft leeg, en zegt dat ────────────────────────────────────────

def test_an_empty_card_says_so_instead_of_showing_blank_rows(
        client, db_session, activiteit):
    """Zonder omschrijving, nota of affiche: één zin, geen lege labelregels.

    Een leeg veld als lege regel tonen maakt de kaart opnieuw een kader zonder
    inhoud — precies de klacht waar F33 (#996) al op stuitte.
    """
    _login(client)
    lees = _leesdeel(_kaart(client, activiteit))

    assert "Nog niets ingevuld" in lees
    assert "Omschrijving:" not in lees, "een leeg veld hoort weggelaten, niet leeg getoond"
    assert "Interne nota:" not in lees


def test_a_card_with_content_drops_the_empty_state_sentence(
        client, db_session, activiteit):
    """De terugvalzin hoort bij de KAART, niet bij de affiche.

    Vroeger stond "Nog geen affiche" er ook wanneer de kaart verder vol stond;
    met een omschrijving erin is de kaart niet leeg en is die zin ruis. Zonder
    deze test zou een terugvalzin die altijd meekomt ook groen staan.
    """
    activiteit.description = OMSCHRIJVING
    db_session.commit()
    _login(client)

    lees = _leesdeel(_kaart(client, activiteit))
    assert OMSCHRIJVING in lees
    assert "Nog niets ingevuld" not in lees


# ── 3. De bewerkmodus verandert niet ────────────────────────────────────────

def test_edit_mode_keeps_the_same_fields_in_the_same_places(
        client, db_session, activiteit):
    """Buiten scope van #1139, dus hier vastgepind.

    De leesweergave is ernaast gezet, niet in de plaats van: dezelfde velden,
    dezelfde vorm, dezelfde waarden.
    """
    activiteit.description = OMSCHRIJVING
    activiteit.board_notes = NOTA
    db_session.commit()
    _login(client)

    html = _kaart(client, activiteit)
    vorm = html.split('<form id="aa-act-form"', 1)[1]
    for veld in ("name", "slug", "location", "description", "board_notes", "poster_url"):
        assert f'id="{veld}"' in vorm, f"{veld} verdween uit de bewerkvorm"
    # En de waarden staan er nog in, niet alleen de velden.
    assert OMSCHRIJVING in vorm and NOTA in vorm
