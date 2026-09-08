"""#716 — de ploegnaam is corrigeerbaar bij het bewerken van een inschrijving.

Ze stond wél in de kop van het paneel ("Koen RENDERS (A-team 1)") maar had geen
invoerveld. Een tikfout was daardoor enkel recht te zetten door de inschrijving te
verwijderen en opnieuw in te voeren — met een nieuwe betaling en OGM tot gevolg.
Dezelfde impasse die #624 voor het e-mailadres wegnam.

Getoetst wordt de BEWAARDE inschrijving, niet de statuscode: opslaan slaagde
vandaag ook, het bewaarde de ploegnaam alleen niet. Een test op `status_code == 200`
zou dus groen blijven staan met de bug erin (#680).

Dat deze correctie geen geld raakt, staat al in
`test_inschrijving_contact_corrigeren.py::test_de_correctie_raakt_het_geld_niet`:
dezelfde route, dezelfde servicefunctie, en die vergelijkt de records veld per veld
in plaats van enkel hun som. Hier nog eens een zwakkere variant zetten voegt niets
toe — een som over een lege lijst is aan beide kanten 0 en slaagt dan zonder iets
te toetsen.

Kapotgemaakt om te controleren dat deze tests rood kunnen:
  * `team_name` uit de veldenlijst in `update_registration_contact` gehaald →
    test_de_ploegnaam_wordt_bewaard faalt op de oude waarde;
  * `team_name` uit de lijst in `inschrijving_opslaan` gehaald → dezelfde test faalt;
  * `toon_ploegnaam` hard op False → de twee scherm-tests falen.
"""
import pytest

from app.domains.activities.api import Registration
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_agnostisch


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _inschrijving(client, db, *, ploegnaam="A-team 1", vraagt_ploegnaam=True):
    activity, comp, product = seed_activity_with_product(db, is_free=False)
    comp.team_name_required = vraagt_ploegnaam
    db.flush()
    payload = {"contact_name": "An Janssens", "phone": "0470000000", "contact_email": "an@example.com",
               "component_id": comp.id, "payment_method": "TRANSFER",
               "items": [{"product_id": product.id, "quantity": 1}]}
    if ploegnaam is not None:
        payload["team_name"] = ploegnaam
    resp = client.post(f"/api/v1/activities/{activity.id}/register", json=payload)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def test_de_ploegnaam_wordt_bewaard(client, db_session):
    reg_id = _inschrijving(client, db_session)
    hdr = _login(client)

    resp = client.post(f"/admin/inschrijvingen/{reg_id}/opslaan", headers=hdr, data={
        "contact_name": "An Janssens", "phone": "0470000000", "contact_email": "an@example.com",
        "team_name": "B-team 2", "remarks": ""})
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    assert db_session.get(Registration, reg_id).team_name == "B-team 2"


def test_leeg_opslaan_wordt_null(client, db_session):
    """Zoals de andere velden: enkel witruimte is geen ploegnaam.

    Op een onderdeel dat er GEEN vraagt — sinds #733 weigert de server een lege
    ploegnaam waar het onderdeel er wél een vraagt, en dat is precies de reden dat
    deze test die kant op moest.
    """
    reg_id = _inschrijving(client, db_session, vraagt_ploegnaam=False)
    hdr = _login(client)

    client.post(f"/admin/inschrijvingen/{reg_id}/opslaan", headers=hdr, data={
        "contact_name": "An Janssens", "phone": "0470000000", "contact_email": "an@example.com",
        "team_name": "   ", "remarks": ""})

    db_session.expire_all()
    assert db_session.get(Registration, reg_id).team_name is None


def test_het_veld_staat_er_als_het_onderdeel_een_ploegnaam_vraagt(client, db_session):
    """Het veld hangt aan het ONDERDEEL, niet aan een bewaarde waarde.

    De inschrijving wordt daarom zonder ploegnaam gemaakt op een onderdeel dat er
    geen vraagt, waarna de vlag aangaat — sinds #733 kan zo'n inschrijving niet meer
    rechtstreeks aangemaakt worden, en dat is juist de bedoeling.
    """
    from app.domains.activities.api import ActivitySubRegistration

    reg_id = _inschrijving(client, db_session, ploegnaam=None, vraagt_ploegnaam=False)
    reg = db_session.get(Registration, reg_id)
    db_session.get(ActivitySubRegistration, reg.component_id).team_name_required = True
    db_session.flush()
    _login(client)
    html = client.get(f"/admin/inschrijvingen/{reg_id}").text
    assert 'name="team_name"' in html, "geen invoerveld voor de ploegnaam (#716)"


def test_het_veld_staat_er_ook_als_de_vlag_intussen_af_staat(client, db_session):
    """De vlag kan later afgezet worden; de bewaarde ploegnaam blijft dan in de kop
    staan en moet corrigeerbaar blijven."""
    reg_id = _inschrijving(client, db_session, ploegnaam="Blijft staan")
    from app.domains.activities.api import ActivitySubRegistration
    reg = db_session.get(Registration, reg_id)
    db_session.get(ActivitySubRegistration, reg.component_id).team_name_required = False
    db_session.flush()

    _login(client)
    html = client.get(f"/admin/inschrijvingen/{reg_id}").text
    assert 'name="team_name"' in html, (
        "een bewaarde ploegnaam is onbewerkbaar zodra de vlag afgaat (#716)")
    assert "Blijft staan" in html


def test_zonder_vlag_en_zonder_waarde_geen_veld(client, db_session):
    """Anders krijgt elk onderdeel een veld dat het niet gebruikt."""
    reg_id = _inschrijving(client, db_session, ploegnaam=None, vraagt_ploegnaam=False)
    _login(client)
    html = client.get(f"/admin/inschrijvingen/{reg_id}").text
    assert 'name="team_name"' not in html
