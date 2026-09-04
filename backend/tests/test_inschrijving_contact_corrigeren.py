"""Admin corrigeert de contactgegevens van een inschrijving (#624).

Een tikfout in het e-mailadres betekent dat de bevestiging en elke verdere
communicatie niet aankomen. Dat was alleen recht te zetten door de inschrijving te
verwijderen en opnieuw in te voeren — met een nieuwe betaling en een nieuwe OGM tot
gevolg.

De invariant die telt is niet dat de velden bewaard worden, maar dat dit **geen geld
raakt** en dat de correctie **verklaarbaar** blijft in het audit-logboek.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.domains.activities.api import Registration
from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for, make_session_value)
from app.domains.payment.api import PaymentRecord, get_records_for
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_agnostisch


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _inschrijving(client, db):
    activity, comp, product = seed_activity_with_product(db, is_free=False)
    resp = client.post(f"/api/v1/activities/{activity.id}/register", json={
        "contact_name": "An Janssens", "contact_email": "fout@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 1}]})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def test_contactgegevens_worden_bewaard_en_genormaliseerd(client, db_session):
    reg_id = _inschrijving(client, db_session)
    hdr = _login(client)

    resp = client.post(f"/admin/inschrijvingen/{reg_id}/opslaan", headers=hdr, data={
        "contact_name": "An Peeters", "contact_email": "juist@example.com",
        "phone": "   ", "remarks": ""})
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    reg = db_session.get(Registration, reg_id)
    assert reg.contact_name == "An Peeters"
    assert reg.contact_email == "juist@example.com"
    assert reg.phone is None, "enkel witruimte hoort NULL te worden"


def test_ongeldig_e_mailadres_wordt_geweigerd(client, db_session):
    """Vorm hoort in het schema: een leesbare fout, niet stil bewaren."""
    reg_id = _inschrijving(client, db_session)
    hdr = _login(client)

    resp = client.post(f"/admin/inschrijvingen/{reg_id}/opslaan", headers=hdr, data={
        "contact_name": "An", "contact_email": "geen-adres", "phone": "", "remarks": ""})
    assert resp.status_code == 422, resp.text

    db_session.expire_all()
    assert db_session.get(Registration, reg_id).contact_email == "fout@example.com"


def test_de_correctie_staat_in_het_auditlogboek(client, db_session):
    """Zonder spoor is een stille correctie op iemands contactgegevens niet te
    verklaren — het logboek toont oud → nieuw."""
    from app.domains.audit.api import all_changes_since

    reg_id = _inschrijving(client, db_session)
    hdr = _login(client)
    client.post(f"/admin/inschrijvingen/{reg_id}/opslaan", headers=hdr, data={
        "contact_name": "An Janssens", "contact_email": "juist@example.com",
        "phone": "", "remarks": ""})
    client.post(f"/admin/inschrijvingen/{reg_id}/opslaan", headers=hdr, data={
        "contact_name": "An Janssens", "contact_email": "nogjuister@example.com",
        "phone": "", "remarks": ""})

    rijen = [r for r in all_changes_since(db_session, date.today())
             if r["entity"] == "Inschrijving" and r["entity_id"] == reg_id]
    assert rijen, "geen audit-rij voor de correctie"
    samen = " ".join(r["summary"] for r in rijen)
    assert "juist@example.com" in samen and "nogjuister@example.com" in samen
    assert "→" in samen, "oud → nieuw hoort zichtbaar te zijn"


def test_de_correctie_raakt_het_geld_niet(client, db_session):
    """Bedrag, OGM en bestelregels blijven ongewijzigd — dit is geen geldwijziging."""
    reg_id = _inschrijving(client, db_session)
    hdr = _login(client)

    voor = get_records_for(db_session, "registration", reg_id)
    bedragen = [(r.id, r.amount, r.structured_communication) for r in voor]
    aantal_regels = len(db_session.get(Registration, reg_id).items)

    client.post(f"/admin/inschrijvingen/{reg_id}/opslaan", headers=hdr, data={
        "contact_name": "Andere Naam", "contact_email": "ander@example.com",
        "phone": "0470000000", "remarks": "nota"})

    db_session.expire_all()
    na = get_records_for(db_session, "registration", reg_id)
    assert [(r.id, r.amount, r.structured_communication) for r in na] == bedragen
    assert len(db_session.get(Registration, reg_id).items) == aantal_regels


def test_alleen_de_opmerking_posten_laat_de_contactgegevens_staan(client, db_session):
    """De oude #283-aanroep blijft werken: wat niet meegestuurd wordt, verandert niet."""
    from app.domains.activities.router import update_registration_remarks
    from app.schemas.activity import RegistrationContactUpdate
    from app.domains.auth.api import User

    reg_id = _inschrijving(client, db_session)
    reg = db_session.get(Registration, reg_id)
    admin = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()

    update_registration_remarks(reg.activity_id, reg_id,
                                RegistrationContactUpdate(remarks="enkel dit"),
                                db=db_session, admin=admin)

    db_session.expire_all()
    reg = db_session.get(Registration, reg_id)
    assert reg.remarks == "enkel dit"
    assert reg.contact_email == "fout@example.com", "niet meegestuurd = ongewijzigd"
