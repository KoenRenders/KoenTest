"""#792 — de volledige eerste datumrij bij het aanmaken, en de samenhangregel.

Bij #623 kreeg het aanmaakscherm één datumveld: *"naam en eerste datum volstaan;
datums, onderdelen en producten vul je daarna aan"*. Verdedigbaar, maar Koen heeft in
de praktijk gemerkt dat die eerste rij bijna altijd meteen volledig is (9 september
2026), dus de omweg via de editor was de regel geworden in plaats van de uitzondering.
**Dit herziet die keuze bewust** — lees het niet als een terugval en maak het formulier
niet opnieuw smal.

Er ontbrak niets om het te kunnen: `ActivityDate` heeft de vier velden,
`ActivityDateCreate` aanvaardt ze, en de editor vulde ze al in. Het aanmaakpad gooide
ze weg.

**De samenhangregel hoort daarbij en staat op het object.** Vandaag controleert niets
dat een einddatum na de begindatum ligt — via de editor kon je een rij opslaan die van
20 september tot 18 september liep. Dat gat bestond al; dit issue zet die velden op het
aanmaakpad, waar élke activiteit langskomt, dus het wordt van randgeval een hoofdweg.
Volgens de plaatsingsregel van CR-04 kijkt deze regel naar meerdere velden van
hetzelfde object, dus hoort ze op het object: `ActivityDate.valideer_samenhang`, met
mapper-events zodat élke ingang haar erft.

**De tweede test hieronder is het bewijs van die plaatsing**, en daarom staan alle
ingangen erin. Een controle die alleen in het nieuwe formulier zit, laat de editor het
gat houden — en dan zijn er twee waarheden over dezelfde rij.

`assert status >= 400` staat er bewust NIET: dat slaagt ook op een CSRF-fout of een
ontbrekende rol, en zo bleef #680 groen terwijl de geldrem eronder verdwenen was. Elke
weigering wordt getoetst op haar melding.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: de drie extra velden
weer weggegooid in `activiteit_aanmaken` → de eerste test valt om; het mapper-event
weggehaald → alle drie de ingangen van de tweede test vallen om (en dát is het bewijs
dat ze niet elk hun eigen controle hebben).
"""
import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "ADMIN" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _laatste_activiteit(db):
    from app.domains.activities.api import Activity

    return db.query(Activity).order_by(Activity.id.desc()).first()


def test_het_aanmaakscherm_toont_de_vier_velden(client, db_session):
    _login(client, db_session)

    html = client.get("/admin/activiteiten/nieuw").text

    for veld in ('id="start_date"', 'id="end_date"', 'id="start_time"', 'id="end_time"'):
        assert veld in html, f"{veld} ontbreekt; de eerste rij is niet volledig invulbaar"


def test_aanmaken_bewaart_de_volledige_eerste_rij(client, db_session):
    """Op de code van vóór dit issue rood: de drie extra waarden werden weggegooid."""
    from datetime import date, time

    headers = _login(client, db_session)

    resp = client.post("/admin/activiteiten", headers=headers, data={
        "name": "Proefactiviteit", "start_date": "2026-09-20",
        "end_date": "2026-09-21", "start_time": "19:30", "end_time": "23:00"})

    assert resp.status_code == 204, resp.text
    rij = _laatste_activiteit(db_session).dates[0]
    assert rij.start_date == date(2026, 9, 20)
    assert rij.end_date == date(2026, 9, 21), "de einddatum is weggegooid"
    assert rij.start_time == time(19, 30), "het beginuur is weggegooid"
    assert rij.end_time == time(23, 0), "het einduur is weggegooid"


def test_de_uren_mogen_leeg_blijven(client, db_session):
    """Alleen de begindatum is verplicht, net als in de editor."""
    headers = _login(client, db_session)

    resp = client.post("/admin/activiteiten", headers=headers, data={
        "name": "Alleen een begindatum", "start_date": "2026-09-20",
        "end_date": "", "start_time": "", "end_time": ""})

    assert resp.status_code == 204, resp.text
    rij = _laatste_activiteit(db_session).dates[0]
    assert rij.end_date is None and rij.start_time is None and rij.end_time is None


def _maak_activiteit(client, db, headers):
    client.post("/admin/activiteiten", headers=headers,
                data={"name": "Te bewerken", "start_date": "2026-09-20"})
    return _laatste_activiteit(db)


# De drie schermingangen, elk als eigen test: een afgewezen schrijfactie draait de
# transactie terug, en in deze suite is die transactie een SAVEPOINT rond de hele
# test — dus alles wat ervóór aangemaakt is, verdwijnt mee. In productie heeft elk
# verzoek zijn eigen sessie; dit is een eigenaardigheid van de opstelling, geen
# gedrag van de applicatie.
OMGEKEERD = {"start_date": "2026-09-20", "end_date": "2026-09-18"}


def _post_aanmaken(client, db, headers):
    return client.post("/admin/activiteiten", headers=headers,
                       data={"name": "Omgekeerd", **OMGEKEERD})


def _post_datum_toevoegen(client, db, headers):
    activiteit = _maak_activiteit(client, db, headers)
    return client.post(f"/admin/activiteiten/{activiteit.id}/datums",
                       headers=headers, data=OMGEKEERD)


def _post_datum_bewerken(client, db, headers):
    activiteit = _maak_activiteit(client, db, headers)
    pad = f"/admin/activiteiten/{activiteit.id}/datums/{activiteit.dates[0].id}"
    return client.post(pad, headers=headers, data=OMGEKEERD)


@pytest.mark.parametrize("ingang", [_post_aanmaken, _post_datum_toevoegen,
                                    _post_datum_bewerken],
                         ids=["aanmaken", "datum toevoegen", "datum bewerken"])
def test_een_einddatum_voor_de_begindatum_wordt_overal_geweigerd(client, db_session, ingang):
    """De kern: de regel staat op het object, dus alle ingangen erven haar.

    Zou ze in het aanmaakformulier staan, dan slaagt de eerste en falen de andere
    twee — precies het "twee waarheden over dezelfde rij" dat dit moet voorkomen.
    """
    headers = _login(client, db_session)

    resp = ingang(client, db_session, headers)

    assert resp.status_code == 422, f"{resp.status_code} — {resp.text[:200]}"
    assert "einddatum ligt vóór de begindatum" in resp.text, (
        f"geweigerd om een andere reden dan de samenhangregel: {resp.text[:200]}")


def test_een_einduur_voor_het_beginuur_op_dezelfde_dag_wordt_geweigerd(client, db_session):
    headers = _login(client, db_session)

    resp = client.post("/admin/activiteiten", headers=headers, data={
        "name": "Achteruit", "start_date": "2026-09-20",
        "start_time": "22:00", "end_time": "19:00"})

    assert resp.status_code == 422, resp.text
    assert "einduur ligt niet na het beginuur" in resp.text


def test_een_nacht_over_twee_dagen_mag(client, db_session):
    """De tegenproef die de vorige bruikbaar maakt: zonder haar zou "alles met een
    vroeger einduur weigeren" ook groen staan, en dat is fout — een fuif van 20:00 tot
    02:00 duurt gewoon een nacht."""
    from datetime import time

    headers = _login(client, db_session)

    resp = client.post("/admin/activiteiten", headers=headers, data={
        "name": "Fuif", "start_date": "2026-09-20", "end_date": "2026-09-21",
        "start_time": "20:00", "end_time": "02:00"})

    assert resp.status_code == 204, resp.text
    assert _laatste_activiteit(db_session).dates[0].end_time == time(2, 0)


def test_de_json_api_erft_dezelfde_regel(client, admin_headers):
    """De vierde ingang. Een regel die alleen de schermen kent, is geen regel op het
    object — en deze route is precies hoe #720/#727/#733 ontstonden."""
    resp = client.post("/api/v1/activities", headers=admin_headers, json={
        "name": "Via de API", "dates": [
            {"start_date": "2026-09-20", "end_date": "2026-09-18"}]})

    assert resp.status_code == 422, resp.text
    assert "einddatum ligt vóór de begindatum" in resp.text
