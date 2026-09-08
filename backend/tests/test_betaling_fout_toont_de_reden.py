"""#723 — de reden van een geweigerde actie kwam aan als "Er ging iets mis".

De servicelaag schrijft een precieze zin — *"Kan niet meer terugbetalen (€ 100.00)
dan er netto ontvangen is (€ 10.00)."* — en die reisde tot vlak vóór het scherm.
Daar werd ze een `HTTPException(400)`, en htmx swapt niet op een 4xx: de globale
foutafhandelaar in `_macros.html` nam over en toont voor élke status behalve 401 en
403 één vaste zin, zonder ooit in het antwoord te kijken. De uitleg werd dus
geschreven, doorgegeven, over de lijn gestuurd en op de laatste meter weggegooid.

Alle vier de mutaties op dat scherm liepen door dezelfde helper en verloren hun
melding op dezelfde manier.

**Waarom de eerste twee asserts in één test staan.** De fout gáát over een
foutmelding, dus "het antwoord is een 200" en "de concrete reden staat erin" zeggen
los van elkaar niets: een 200 zonder reden is nog steeds de generieke zin, en een
reden in een 400 komt nooit op het scherm. Samen zijn ze de bewering.

De laatste test is de tegenproef: zonder haar staat de rest ook groen wanneer
voortaan álles met een 200 antwoordt, en dan is een verdwenen record niet meer van
een invoerfout te onderscheiden.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (lokaal): in
`_uitvoeren` de `BetalingFout`-tak terug op `raise HTTPException(400, ...)` gezet →
de eerste twee tests vallen om (400 in plaats van 200, en geen reden in de tekst),
de andere twee blijven groen.
"""
from decimal import Decimal

import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from app.domains.payment.api import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _make_finance(db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db.flush()


def _betaalde_vordering(db, bedrag="10.00") -> PaymentRecord:
    record = PaymentRecord(payable_type="membership", payable_id=1, type="charge",
                           amount=Decimal(bedrag), amount_paid=Decimal(bedrag),
                           method="transfer", status="paid")
    db.add(record)
    db.flush()
    return record


def test_een_te_hoge_terugbetaling_noemt_het_maximum(client, db_session):
    """Het gemelde geval: € 100,00 terugbetalen op € 10,00 ontvangen."""
    record = _betaalde_vordering(db_session)
    _make_finance(db_session)
    csrf = _login(client)

    resp = client.post(f"/admin/betalingen/{record.id}/refund",
                       data={"amount": "100", "note": ""},
                       headers={"X-CSRF-Token": csrf})

    # Deze twee horen samen — zie de docstring.
    assert resp.status_code == 200, (
        "een 4xx wordt niet geswapt, dus de melding komt nooit op het scherm")
    assert "10.00" in resp.text, (
        "het maximum staat niet in de melding; dan blijft het 'probeer opnieuw'")
    assert "terugbetalen" in resp.text


def test_de_generieke_zin_komt_er_niet_meer_aan_te_pas(client, db_session):
    """De keerzijde: het antwoord moet de lijst zijn, niet de vangnet-melding.

    Zou de route een 4xx blijven geven, dan staat de generieke zin op het scherm en
    de concrete nergens. Deze test toetst dat het antwoord écht het lijstfragment is
    en niet een leeg of generiek antwoord.
    """
    record = _betaalde_vordering(db_session)
    _make_finance(db_session)
    csrf = _login(client)

    resp = client.post(f"/admin/betalingen/{record.id}/refund",
                       data={"amount": "100", "note": ""},
                       headers={"X-CSRF-Token": csrf})

    assert 'role="alert"' in resp.text, "de reden staat niet in de foutbanner"
    assert "Te betalen" in resp.text, "het lijstfragment is niet meegekomen"


def test_een_geslaagde_terugbetaling_toont_geen_banner(client, db_session):
    """Anders zou "er staat altijd een banner" ook groen zijn."""
    record = _betaalde_vordering(db_session, bedrag="25.00")
    _make_finance(db_session)
    csrf = _login(client)

    resp = client.post(f"/admin/betalingen/{record.id}/refund",
                       data={"amount": "10", "note": "Deels terug"},
                       headers={"X-CSRF-Token": csrf})

    assert resp.status_code == 200, resp.text
    assert 'role="alert"' not in resp.text, "een geslaagde actie meldt geen fout"


def test_een_onbestaand_record_blijft_een_404(client, db_session):
    """De tegenproef. Een verdwenen record is geen invoerfout: daar is "herlaad de
    pagina" wél het juiste antwoord, en dat is precies wat een 404 doet."""
    _make_finance(db_session)
    csrf = _login(client)

    resp = client.post("/admin/betalingen/bestaat-niet/refund",
                       data={"amount": "10"}, headers={"X-CSRF-Token": csrf})

    assert resp.status_code == 404
