"""Fase 4a-4 (#402): admin-activiteitenbeheer server-rendered (htmx)."""

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product, sent_to_sign_in


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_admin_activiteiten_requires_session(client):
    assert sent_to_sign_in(client, "/admin/activiteiten")


def test_admin_activiteit_aanmaken_en_detail(client, db_session):
    csrf = _login(client)
    # Sinds #586 opent aanmaken meteen de paginabrede editor (HX-Redirect), want
    # een verse activiteit heeft daar nog datums en onderdelen nodig.
    resp = client.post(
        "/admin/activiteiten",
        data={"name": "Zomerbar", "start_date": "2031-07-01", "location": "Millegem"},
        headers={"X-CSRF-Token": csrf},
    )
    from app.domains.activities.api import Activity

    activity = db_session.query(Activity).filter(Activity.name == "Zomerbar").one()
    assert resp.status_code == 204
    assert resp.headers["HX-Redirect"] == f"/admin/activiteiten/{activity.id}"
    detail = client.get(f"/admin/activiteiten/{activity.id}")
    assert detail.status_code == 200 and "Millegem" in detail.text and "Datums" in detail.text


def test_activiteit_geneste_producten_paneel(client, db_session):
    """#509: products stand under their component, indented behind a line — since
    #1559 as the child group of the kit's repeating group (no nested card)."""
    activity, component, product = seed_activity_with_product(db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert ">Onderdelen</h2>" in html
    components = html[html.index('id="aa-group-components"') :]
    child = components[components.index(f'data-repeating-group="p_order.{component.id}"') :]
    assert 'class="group-child"' in child.split(">", 1)[0] + ">"
    assert ">Producten</h3>" in child
    assert product.name in child


def test_activiteit_affiche_upload_in_edit_modus(client, db_session):
    """#503/#623, since #1558: the file field sits in the same form as name,
    location and description, so one "Opslaan" keeps them all — and that form
    exists only in the edit state of the page (`?bewerken=1`). The read state
    carries no form and no file field; the edit state carries "Annuleren" beside
    "Opslaan"."""
    activity, component, _p = seed_activity_with_product(db_session)
    _login(client)
    read = client.get(f"/admin/activiteiten/{activity.id}").text
    assert 'id="aa-act-form"' not in read and 'id="upl-file"' not in read

    html = client.get(f"/admin/activiteiten/{activity.id}?bewerken=1").text
    assert ">Annuleren<" in html and ">Opslaan<" in html
    form = html.split('<form id="aa-act-form"', 1)[1].split("</form>", 1)[0]
    assert 'type="file"' in form, "the file field belongs in that form"
    assert 'name="name"' in form and 'name="description"' in form
    # The poster address sits in the closed last section, outside the form
    # element, and names the form it belongs to.
    assert 'name="poster_url" form="aa-act-form"' in html


def test_admin_inschrijvingen_en_export(client, db_session):
    activity, component, product = seed_activity_with_product(
        db_session, price="10.00", is_free=False
    )
    _login(client)
    # publieke flow maakt een inschrijving
    client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={
            "contact_name": "Jef",
            "contact_email": "jef@example.com",
            "phone": "047",
            f"product_{product.id}": "1",
            "payment_method": "transfer",
        },
    )
    # Ronde 2 (15 sep): één tabpagina, per onderdeel gegroepeerd — de
    # #650-waarborg (zien waarvoor iemand ingeschreven is) zit in de groepskop.
    lijst = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen")
    assert lijst.status_code == 200 and "Jef" in lijst.text
    # #1636 (K6, #1560 before it): the row is the way in — its name links to
    # the page in READ mode, where the Bewerken opener stands, with
    # Verwijderen in its cluster. No "Details" button, no "Bewerken" and no
    # direct Verwijderen in the row, and the row unfolds nowhere.
    from app.domains.activities.api import Registration

    reg = db_session.query(Registration).filter(Registration.contact_name == "Jef").one()
    assert (
        ">Details<" not in lijst.text
        and ">Bewerken<" not in lijst.text.split("data-table-frame")[1]
    )
    assert f'data-row-key="{reg.id}"' in lijst.text and "data-row-toggle=" not in lijst.text
    assert f'<a href="/admin/inschrijvingen/{reg.id}?terug=' in lijst.text
    assert "bewerk=1" not in lijst.text
    # The rows have no delete; the head's Acties menu has the activity's (#1561).
    assert ">Verwijderen<" not in lijst.text.split("data-table-frame")[1]
    # B2 (golf 4): de recordnaam zelf opent de pagina (leesmodus), met A7 —
    # de terugweg is sinds ronde 2 de tab-URL mét sorteerstand (ge-encodeerd).
    assert f'href="/admin/inschrijvingen/{reg.id}?terug=' in lijst.text

    export = client.get(f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}/export")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("application/vnd.oasis")


def test_admin_mutatie_zonder_csrf_geweigerd(client, db_session):
    _login(client)
    resp = client.post("/admin/activiteiten", data={"name": "X", "start_date": "2031-01-01"})
    assert resp.status_code == 403
