"""Fase 4a-4 (#402): admin-activiteitenbeheer server-rendered (htmx)."""
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_admin_activiteiten_requires_session(client):
    assert client.get("/admin/activiteiten").status_code == 401


def test_admin_activiteit_aanmaken_en_detail(client, db_session):
    csrf = _login(client)
    resp = client.post("/admin/activiteiten",
                       data={"name": "Zomerbar", "start_date": "2031-07-01",
                             "location": "Millegem"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and "Zomerbar" in resp.text

    from app.domains.activities.api import Activity
    activity = db_session.query(Activity).filter(Activity.name == "Zomerbar").one()
    detail = client.get(f"/admin/activiteiten/{activity.id}")
    assert detail.status_code == 200 and "Millegem" in detail.text and "Datums" in detail.text


def test_admin_onderdeel_en_product_flow(client, db_session):
    csrf = _login(client)
    client.post("/admin/activiteiten",
                data={"name": "Kermis", "start_date": "2031-08-01"},
                headers={"X-CSRF-Token": csrf})
    from app.domains.activities.api import Activity
    activity = db_session.query(Activity).filter(Activity.name == "Kermis").one()

    comp = client.post(f"/admin/activiteiten/{activity.id}/onderdelen",
                       data={"name": "Eetstand", "max_participants": "50"},
                       headers={"X-CSRF-Token": csrf})
    assert comp.status_code == 200 and "Eetstand" in comp.text

    db_session.expire_all()
    component = activity.sub_registrations[0]
    prod = client.post(f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}/producten",
                       data={"name": "Pannenkoeken", "price": "5,00"},
                       headers={"X-CSRF-Token": csrf})
    assert prod.status_code == 200 and "Pannenkoeken" in prod.text and "5.00" in prod.text


def test_product_afrekening_keuze(client, db_session):
    """#507: de expliciete 'Afrekening'-keuze (Betalend/Gratis/Ter plaatse) zet
    is_free/pay_on_site; de prijs blijft los invulbaar."""
    from app.domains.activities.api import ActivityProduct

    activity, component, _p = seed_activity_with_product(db_session, price="10.00")
    csrf = _login(client)
    base = f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}/producten"

    client.post(base, data={"name": "Gratis drankje", "price": "3,00", "afrekening": "gratis"},
                headers={"X-CSRF-Token": csrf})
    client.post(base, data={"name": "Frietjes", "price": "4,00", "afrekening": "ter_plaatse"},
                headers={"X-CSRF-Token": csrf})
    client.post(base, data={"name": "Pintje", "price": "2,50", "afrekening": "betalend"},
                headers={"X-CSRF-Token": csrf})
    db_session.expire_all()

    def _prod(naam):
        return db_session.query(ActivityProduct).filter(ActivityProduct.name == naam).one()

    assert _prod("Gratis drankje").is_free is True and _prod("Gratis drankje").pay_on_site is False
    assert _prod("Frietjes").pay_on_site is True and _prod("Frietjes").is_free is False
    assert _prod("Pintje").is_free is False and _prod("Pintje").pay_on_site is False


def test_activiteit_affiche_upload_in_edit_modus(client, db_session):
    """#503: het affiche-upload-blok zit in de edit-vorm (x-show="edit"), niet in
    read-modus; de activiteitkaart heeft een Annuleren-affordance naast Opslaan."""
    import re

    activity, component, _p = seed_activity_with_product(db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert ">Annuleren<" in html
    # De affiche-upload-form is gegated op x-show="edit" (staat niet in read-modus).
    assert re.search(r'x-show="edit"[^<]*?/affiche"', html)


def test_admin_inschrijvingen_en_export(client, db_session):
    activity, component, product = seed_activity_with_product(db_session, price="10.00", is_free=False)
    csrf = _login(client)
    # publieke flow maakt een inschrijving
    client.post(f"/activiteiten/{activity.id}/inschrijven/{component.id}",
                data={"contact_name": "Jef", "contact_email": "jef@example.com",
                      "phone": "047", f"product_{product.id}": "1",
                      "payment_method": "OVERSCHRIJVING"})
    lijst = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen")
    assert lijst.status_code == 200 and "Jef" in lijst.text
    # #510: elke rij heeft nu een "Bewerken" die de gedeelde editor in-lijn laadt
    # (detail_disclosure → /admin/inschrijvingen/{id}), naast "Verwijder".
    from app.domains.activities.api import Registration
    reg = db_session.query(Registration).filter(Registration.contact_name == "Jef").one()
    assert ">Bewerken<" in lijst.text
    assert f'hx-get="/admin/inschrijvingen/{reg.id}"' in lijst.text
    assert ">Verwijder<" in lijst.text

    export = client.get(f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}/export")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("application/vnd.oasis")


def test_admin_mutatie_zonder_csrf_geweigerd(client, db_session):
    _login(client)
    resp = client.post("/admin/activiteiten", data={"name": "X", "start_date": "2031-01-01"})
    assert resp.status_code == 403
