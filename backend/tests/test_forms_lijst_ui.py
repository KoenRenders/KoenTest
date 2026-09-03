"""Lijst-index /admin/formulieren volgens design-system C1 (#585).

Het scherm werd een lijst-index: geen permanent "Nieuw formulier"-veld en geen
master-detail meer, wél zoeken, een statusfilter en kaarten die de paginabrede
form-builder openen. Deze tests dekken wat kapot kán: de filters (inclusief een
gemanipuleerde status), de navigatie na aanmaken/verwijderen, en de toegangs-
grens — niet de opmaak.
"""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.forms.models import Form


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _maak(db_session, titel: str, status: str, token: str) -> Form:
    form = Form(title=titel, status=status, share_token=token)
    db_session.add(form)
    db_session.commit()
    return form


def test_lijst_vereist_sessie(client):
    assert client.get("/admin/formulieren").status_code == 401


def test_zoeken_filtert_op_naam(client, db_session):
    _login(client)
    _maak(db_session, "Inschrijving zomerkamp", "open", "zomer-1")
    _maak(db_session, "Evaluatie winterfeest", "draft", "winter-1")

    alles = client.get("/admin/formulieren")
    assert "Inschrijving zomerkamp" in alles.text and "Evaluatie winterfeest" in alles.text

    gezocht = client.get("/admin/formulieren", params={"q": "winter"})
    assert "Evaluatie winterfeest" in gezocht.text
    assert "Inschrijving zomerkamp" not in gezocht.text


def test_statusfilter_toont_enkel_die_status(client, db_session):
    _login(client)
    _maak(db_session, "Open formulier", "open", "open-1")
    _maak(db_session, "Concept formulier", "draft", "concept-1")

    concepten = client.get("/admin/formulieren", params={"status": "draft"})
    assert "Concept formulier" in concepten.text
    assert "Open formulier" not in concepten.text


def test_onbekende_status_filtert_niet(client, db_session):
    """Een gemanipuleerde querystring mag niet leiden tot een 500 of een lege lijst."""
    _login(client)
    _maak(db_session, "Zichtbaar formulier", "open", "zicht-1")

    resp = client.get("/admin/formulieren", params={"status": "'; drop table forms; --"})
    assert resp.status_code == 200
    assert "Zichtbaar formulier" in resp.text


def test_aanmaken_stuurt_door_naar_de_builder(client, db_session):
    csrf = _login(client)
    resp = client.post("/admin/formulieren", data={"title": "Nieuw kamp"},
                       headers={"X-CSRF-Token": csrf})
    form = db_session.query(Form).filter(Form.title == "Nieuw kamp").one()
    assert resp.status_code == 204
    assert resp.headers["HX-Redirect"] == f"/admin/formulieren/{form.id}"


def test_verwijderen_stuurt_terug_naar_de_lijst(client, db_session):
    """Voorheen kwam er een lijstfragment terug voor een element dat op de
    builder-pagina niet bestaat — de gebruiker zag niets gebeuren."""
    csrf = _login(client)
    form = _maak(db_session, "Weg hiermee", "draft", "weg-1")

    resp = client.post(f"/admin/formulieren/{form.id}/verwijderen",
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204
    assert resp.headers["HX-Redirect"] == "/admin/formulieren"
    assert db_session.query(Form).filter(Form.id == form.id).first() is None


def test_lijst_heeft_geen_permanent_naamveld_meer(client, db_session):
    """C1: de naam vraag je in de modal bij het aanmaken, niet in een veld dat
    altijd bovenaan de lijst staat."""
    _login(client)
    _maak(db_session, "Bestaand formulier", "open", "best-1")

    html = client.get("/admin/formulieren").text
    assert "+ Nieuw formulier" in html
    assert "Formaat (voor AI)" in html
    assert 'name="q"' in html and 'name="status"' in html
    # het formulier zit in de modal, die pas op klik opent (x-show)
    assert 'id="f-title"' in html and "x-data" in html
    # de kaarten linken naar de paginabrede editor
    assert 'href="/admin/formulieren/' in html
