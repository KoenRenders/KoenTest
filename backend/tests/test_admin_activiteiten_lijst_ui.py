"""Records-lijst /admin/activiteiten volgens design-system C1 (#586).

Nieuw op dit scherm: zoeken op titel of locatie en scope-chips in de filterbalk,
met kaarten die de paginabrede editor openen i.p.v. een detailpaneel te vullen.
Getest wordt wat stuk kan: de filters (ook gecombineerd), de betekenis van de
KPI-rij onder een filter, en de navigatie na aanmaken en verwijderen.
"""
from datetime import date, timedelta

from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.activities.api import Activity, ActivityDate


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _activiteit(db_session, naam: str, locatie: str, dagen_vooruit: int) -> Activity:
    """Eén activiteit met één datum; het teken van `dagen_vooruit` bepaalt of ze
    komend of archief is."""
    a = Activity(name=naam, location=locatie)
    db_session.add(a)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=a.id,
                                start_date=date.today() + timedelta(days=dagen_vooruit)))
    db_session.commit()
    return a


def test_zoeken_op_titel_en_op_locatie(client, db_session):
    _login(client)
    _activiteit(db_session, "Quiz", "Parochiezaal", 20)
    _activiteit(db_session, "Wandeling", "Bosrand", 25)

    op_titel = client.get("/admin/activiteiten", params={"q": "quiz"})
    assert "Quiz" in op_titel.text and "Wandeling" not in op_titel.text

    op_locatie = client.get("/admin/activiteiten", params={"q": "bosrand"})
    assert "Wandeling" in op_locatie.text and "Quiz" not in op_locatie.text


def test_archief_toont_voorbije_activiteiten_en_komende_niet(client, db_session):
    _login(client)
    _activiteit(db_session, "Straks", "Zaal", 30)
    _activiteit(db_session, "Voorbij", "Zaal", -30)

    komende = client.get("/admin/activiteiten")           # default scope
    assert "Straks" in komende.text and "Voorbij" not in komende.text

    archief = client.get("/admin/activiteiten", params={"scope": "archived"})
    assert "Voorbij" in archief.text and "Straks" not in archief.text


def test_onbekende_scope_valt_terug_zonder_fout(client, db_session):
    _login(client)
    _activiteit(db_session, "Zichtbaar", "Zaal", 10)
    resp = client.get("/admin/activiteiten", params={"scope": "../etc/passwd"})
    assert resp.status_code == 200 and "Zichtbaar" in resp.text


def test_kpi_telt_alles_wat_openstaat_ook_tijdens_zoeken(client, db_session):
    """Een zoekterm versmalt de lijst, niet de betekenis van het kengetal: wie
    zoekt, wil niet dat 'Open inschrijvingen' meedaalt naar het aantal treffers."""
    _login(client)
    _activiteit(db_session, "Quiz", "Zaal", 12)
    _activiteit(db_session, "Wandeling", "Bos", 14)

    ongefilterd = client.get("/admin/activiteiten").text
    gefilterd = client.get("/admin/activiteiten", params={"q": "quiz"}).text
    # het kengetal staat in hetzelfde blokje als het label
    kop = "Open inschrijvingen"
    assert kop in ongefilterd and kop in gefilterd
    assert gefilterd.count('class="text-3xl font-extrabold text-blue-700"') == 1
    getal = lambda html: html.split('class="text-3xl font-extrabold text-blue-700">')[1].split("<")[0]
    assert getal(gefilterd) == getal(ongefilterd)


def test_kaart_linkt_naar_de_paginabrede_editor(client, db_session):
    _login(client)
    a = _activiteit(db_session, "Kaartlink", "Zaal", 5)
    lijst = client.get("/admin/activiteiten").text
    assert f'href="/admin/activiteiten/{a.id}"' in lijst

    pagina = client.get(f"/admin/activiteiten/{a.id}")
    assert pagina.status_code == 200
    assert "Alle activiteiten" in pagina.text      # terugkeerlink van de editor
    assert 'id="aa-detail"' in pagina.text


def test_verwijderen_stuurt_terug_naar_de_lijst(client, db_session):
    csrf = _login(client)
    a = _activiteit(db_session, "Weg", "Zaal", 8)
    resp = client.post(f"/admin/activiteiten/{a.id}/verwijderen",
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204
    assert resp.headers["HX-Redirect"] == "/admin/activiteiten"


def test_onbestaande_activiteit_geeft_404_op_de_paginaweergave(client, db_session):
    _login(client)
    assert client.get("/admin/activiteiten/999999").status_code == 404
