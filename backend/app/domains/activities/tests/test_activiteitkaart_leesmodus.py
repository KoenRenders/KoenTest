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
    """The three sections of the fiche as the READ state of the page renders them.

    Since #1558 reading and editing are two states of the page (`?bewerken=1`),
    not a read layer above a hidden form. The two assertions stay for the reason
    they were written: a cutting function that finds nothing returns an empty
    string, and then every "is not in it" assertion passes without measuring.
    """
    assert 'data-mode="read"' in html, "this is not the read state of the page"
    assert '<form id="aa-act-form"' not in html, "the read state carries no edit form"
    start = html.index('id="aa-section-activity"')
    lees = html[start : html.index("Datums", start)]
    assert "Activiteit</h2>" in lees, "the cut misses the section heading"
    return lees


def _value(lees: str, field: str) -> str:
    """What the read state shows as the value of one field."""
    block = lees[lees.index(f'data-field="{field}"') :]
    return block[block.index("data-value") :].split("</p>", 1)[0].split(">", 1)[1].strip()


# ── 1. De kaart toont wat ze bevat ──────────────────────────────────────────


def test_description_and_internal_note_are_visible_without_clicking(client, db_session, activiteit):
    """The reported case (#1139): what the fiche holds is read without a click.

    Counter-proof at the time: the two read lines removed → both assertions
    fail, while `OMSCHRIJVING in html` stayed true through the hidden form. The
    hidden form is gone; the values are read from the fields' read blocks.
    """
    activiteit.description = OMSCHRIJVING
    activiteit.board_notes = NOTA
    db_session.commit()
    _login(client)

    lees = _leesdeel(_kaart(client, activiteit))
    assert _value(lees, "description") == OMSCHRIJVING
    assert _value(lees, "board_notes") == NOTA


def test_the_internal_note_is_recognisably_internal_in_read_mode(client, db_session, activiteit):
    """De nota mag niet als gewone tekst tussen de rest staan.

    Het veld bestaat omdat de oude `notes`-kolom stil publiek uitleesbaar bleek
    (#1028). Wie de kaart leest, beslist of hij iets doorvertelt — dus staat de
    belofte er ook in leesmodus bij, met dezelfde woorden als bij het veld.
    """
    activiteit.board_notes = NOTA
    db_session.commit()
    _login(client)

    lees = _leesdeel(_kaart(client, activiteit))
    note = lees[lees.index('data-field="board_notes"') :]
    assert "Interne nota" in note
    assert "Alleen het bestuur ziet dit" in note, (
        "the read state does not say this text is internal"
    )
    assert "Intern</h2>" in lees, "and it stands in its own section"


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

    tekst = (
        Path(__file__).resolve().parents[4]
        / "app"
        / "domains"
        / "activities"
        / "templates"
        / "_aa_detail.html"
    ).read_text()
    zin = "Alleen het bestuur ziet dit"
    aantal = tekst.count(zin)
    assert aantal == 1, (
        f"de belofte staat {aantal}x letterlijk in het sjabloon; leid de tweede "
        "plek af uit INTERNE_NOTA_BELOFTE in plaats van hem te herhalen"
    )


# ── 2. Empty is "—", in its place ───────────────────────────────────────────


def test_an_empty_field_shows_a_dash_in_its_own_place(client, db_session, activiteit):
    """Decision 06 (4 October 2026) reverses #1139's "leave an empty field out":
    the read state shows every field the editor has, in the same order, an empty
    one as "—" — so nothing moves when you start editing. The sentence "Nog niets
    ingevuld" went with the card it explained."""
    _login(client)
    lees = _leesdeel(_kaart(client, activiteit))

    assert "Nog niets ingevuld" not in lees
    for field in ("slug", "description", "file", "target_audience", "board_notes"):
        assert _value(lees, field) == "—", field
    assert _value(lees, "name") == "Neteroute" and _value(lees, "location") == "Millegem"
    assert _value(lees, "members_only") == "nee", "a setting reads in words"
    assert "Alleen het bestuur ziet dit" not in lees, "no promise about a note that is not there"


# ── 3. Read whole, edit whole (B7 test 2) ───────────────────────────────────

FIELDS = [
    "name",
    "slug",
    "location",
    "description",
    "file",
    "target_audience",
    "members_only",
    "board_notes",
]


def _fields(html: str) -> list[str]:
    import re

    start = html.index('id="aa-section-activity"')
    return re.findall(r'data-field="(\w+)"', html[start : html.index("Datums", start)])


def test_read_and_edit_show_the_same_fields_in_the_same_order(client, db_session, activiteit):
    """The same sections, the same fields, the same order in both states; the
    edit state holds a control for each and the values that were read.

    Proven red by removing the location field from the template only while
    editing (`{% if not _edit %}` around it): the two lists differ.
    """
    activiteit.description = OMSCHRIJVING
    activiteit.board_notes = NOTA
    db_session.commit()
    _login(client)

    read = _kaart(client, activiteit)
    edit = client.get(f"/admin/activiteiten/{activiteit.id}?bewerken=1").text
    assert _fields(read) == FIELDS
    assert _fields(edit) == FIELDS
    for heading in ("Activiteit</h2>", "Publiek</h2>", "Intern</h2>"):
        assert heading in read and heading in edit
    assert read.index("Activiteit</h2>") < read.index("Publiek</h2>") < read.index("Intern</h2>")

    vorm = edit.split('<form id="aa-act-form"', 1)[1].split("</form>", 1)[0]
    for veld in (
        "name",
        "slug",
        "location",
        "description",
        "board_notes",
        "target_audience",
        "members_only",
    ):
        assert f'name="{veld}"' in vorm, f"{veld} is missing from the edit form"
    assert 'id="upl-file"' in vorm
    assert OMSCHRIJVING in vorm and NOTA in vorm
    # The closed last section comes after everything, in both states.
    for html in (read, edit):
        assert html.index("data-rare-settings") > html.index("Organisatoren")
    assert 'name="poster_url" form="aa-act-form"' in edit
