"""Golf 5 (#913, P13/A5): relatienavigatie — relatiebalk, scope-regel, spronglinks.

De chip op de inschrijvingspagina opent het GEWONE betalingenscherm in een
zichtbare recordscope ("Voor inschrijving: X" + "Alle bekijken"); de scope
overleeft filterwijzigingen via een hidden field en de server hercontroleert
het id. Een onzichtbaar voorfilter is precies wat het patroon verbiedt — het
bestaande `?record=` (#704) krijgt daarom dezelfde zichtbare regel.
"""
import pytest
pytestmark = pytest.mark.ui_serverrendered

from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.auth.api import User, UserRole


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _make_finance(db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db.flush()


def _twee_inschrijvingen(client, db_session):
    """Twee inschrijvingen met elk een betaalrecord, via het echte publieke pad."""
    activity, component, product = seed_activity_with_product(
        db_session, price="10.00", is_free=False)
    for naam in ("Scope Anna", "Scope Bert"):
        client.post(f"/activiteiten/{activity.id}/inschrijven/{component.id}",
                    data={"contact_name": naam, "contact_email": "s@example.com",
                          "phone": "047", f"product_{product.id}": "1",
                          "payment_method": "OVERSCHRIJVING"})
    from app.domains.activities.api import Registration
    regs = {r.contact_name: r for r in db_session.query(Registration).filter(
        Registration.contact_name.like("Scope %"))}
    return regs["Scope Anna"], regs["Scope Bert"]


def test_scope_toont_enkel_de_betalingen_van_de_inschrijving(client, db_session):
    anna, bert = _twee_inschrijvingen(client, db_session)
    _make_finance(db_session)
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/betalingen?inschrijving={anna.id}").text

    assert "Voor inschrijving:" in html and "Scope Anna" in html
    assert "Scope Bert" not in html, "de scope hoort Berts betaling te verbergen"
    # De expliciete uitgang, en het hidden field dat de scope laat overleven.
    assert 'href="/admin/betalingen"' in html and "Alle bekijken" in html
    assert f'name="inschrijving" value="{anna.id}"' in html


def test_scope_overleeft_een_filterwijziging(client, db_session):
    """Het fragment-verzoek dat de filterbalk stuurt draagt de scope mee — en de
    scope-regel staat ook in het fragmentantwoord, dus ze blijft in beeld."""
    anna, bert = _twee_inschrijvingen(client, db_session)
    _make_finance(db_session)
    db_session.commit()
    _login(client)
    frag = client.get(f"/admin/betalingen/lijst?inschrijving={anna.id}&status=paid").text
    assert "Voor inschrijving:" in frag
    assert "Scope Bert" not in frag


def test_vervalst_of_onbestaand_id_lekt_niets(client, db_session):
    anna, bert = _twee_inschrijvingen(client, db_session)
    _make_finance(db_session)
    db_session.commit()
    _login(client)
    # Geen cijfers → geen scope: de volledige lijst, zonder scope-regel.
    los = client.get("/admin/betalingen?inschrijving=1;DROP--").text
    assert "Voor inschrijving:" not in los
    assert "Scope Anna" in los and "Scope Bert" in los
    # Onbestaand id → de scope blijft zichtbaar (met het nummer) en de lijst is
    # leeg, in plaats van stil alles te tonen.
    leeg = client.get("/admin/betalingen?inschrijving=999999").text
    assert "Voor inschrijving:" in leeg and "#999999" in leeg
    assert "Scope Anna" not in leeg and "Scope Bert" not in leeg


def test_record_deeplink_krijgt_dezelfde_zichtbaarheid(client, db_session):
    """#704 toonde één kaart zonder te zeggen dát er gefilterd werd — het
    onzichtbare voorfilter dat P13 verbiedt."""
    anna, bert = _twee_inschrijvingen(client, db_session)
    _make_finance(db_session)
    db_session.commit()
    _login(client)
    from app.domains.payment.api import get_records_for
    rec = get_records_for(db_session, "registration", anna.id)[0]
    html = client.get(f"/admin/betalingen?record={rec.id}").text
    assert "Eén betaling uitgelicht" in html and "Alle bekijken" in html


def test_export_draagt_de_scope_mee(client, db_session):
    """Een gescopeerd scherm dat álles exporteert is een stille afwijking tussen
    beeld en bestand — de exportknop en de exportroute kennen de scope dus ook."""
    anna, bert = _twee_inschrijvingen(client, db_session)
    _make_finance(db_session)
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/betalingen?inschrijving={anna.id}").text
    assert f"&amp;inschrijving={anna.id}" in html  # in de exportknop-href
    export = client.get(f"/admin/betalingen/export?inschrijving={anna.id}")
    assert export.status_code == 200
    # .ods is een zip; de celinhoud zit in content.xml — Anna's OGM erin, Berts niet.
    import io
    import zipfile
    inhoud = zipfile.ZipFile(io.BytesIO(export.content)).read("content.xml").decode()
    assert "Scope Anna" in inhoud and "Scope Bert" not in inhoud


def test_relatiebalk_op_de_inschrijvingspagina(client, db_session):
    import re

    anna, bert = _twee_inschrijvingen(client, db_session)
    _login(client)
    html = client.get(f"/admin/inschrijvingen/{anna.id}").text
    assert f'href="/admin/betalingen?inschrijving={anna.id}"' in html
    # De chip: label + aantal (één betaalrecord uit het publieke pad).
    assert re.search(r"Betalingen\s*<span[^>]*>1</span>", html)


def test_wijzigingen_object_springt_naar_de_inschrijving(client, db_session):
    """De dode object-cel op het logboek wordt een spronglink — alleen voor
    entiteiten met een eigen pagina; de sprong draagt de weg terug (P3)."""
    from app.domains.audit.api import snapshot_registration

    anna, bert = _twee_inschrijvingen(client, db_session)
    # Expliciet een audit-rij zaaien, zoals test_wijzigingen_scherm: zo toetst
    # dit de spronglink en niet óf het publieke pad toevallig snapshot.
    snapshot_registration(db_session, anna, operation="insert",
                          action="registration_created", source="test",
                          actor="tester@example.com")
    db_session.commit()
    _login(client)
    html = client.get("/admin/ledenwijzigingen?since=2000-01-01").text
    assert f'href="/admin/inschrijvingen/{anna.id}?terug=' in html
    # De arrow-up-right van ui.spronglink (svg-pad; de naam staat niet in de output).
    assert 'd="M7 7h10v10"' in html
