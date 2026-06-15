"""Tests voor de first-party business-events (#152, laag 2).

Waardecreërende invarianten (geen pro-forma tests):
  - GDPR: NOOIT PII in een event-payload — actief bewaakt door de service en
    geverifieerd op alle écht gelogde events van de kernflows.
  - Datakoppeling: events wijzen naar de juiste entiteit (member/activity) en het
    juiste PaymentRecord.
  - De kernflows (lid worden, inschrijven, hernieuwen, betaling) loggen elk hun
    event in dezelfde transactie als de flow zelf.
"""
import pytest

from app.models.business_event import BusinessEvent
from app.domains.analytics.service import (
    log_business_event,
    PiiInEventError,
    _FORBIDDEN_KEY_FRAGMENTS,
    _EMAIL_RE,
)

from tests.conftest import seed_postal_code, seed_activity_with_product
from tests.test_payment_security import _family_payload
from tests.test_membership_pricing import seed_household
from tests.test_membership_renewal import _headers


def _events(db, event_type=None):
    q = db.query(BusinessEvent)
    if event_type:
        q = q.filter(BusinessEvent.event_type == event_type)
    return q.all()


# ── PII-bewaking (de harde GDPR-invariant) ───────────────────────────────────

def test_log_business_event_rejects_email_in_value(db_session):
    with pytest.raises(PiiInEventError):
        log_business_event(db_session, "test", payload={"foo": "jan@example.com"})


def test_log_business_event_rejects_pii_key(db_session):
    for key in ("contact_name", "last_name", "email", "phone", "adres"):
        with pytest.raises(PiiInEventError):
            log_business_event(db_session, "test", payload={key: "x"})


def test_log_business_event_accepts_clean_payload(db_session):
    ev = log_business_event(db_session, "test", payload={"amount": "35.00", "paid": True})
    assert ev.id is not None or ev in db_session.new


def _assert_no_pii_anywhere(db):
    """Geen enkel gelogd event mag PII in zijn payload hebben."""
    for ev in _events(db):
        if not ev.payload:
            continue
        for key, value in ev.payload.items():
            key_l = str(key).lower()
            assert not any(f in key_l for f in _FORBIDDEN_KEY_FRAGMENTS), (
                f"PII-sleutel '{key}' in event {ev.event_type}"
            )
            if isinstance(value, str):
                assert not _EMAIL_RE.search(value), (
                    f"E-mail in payload van event {ev.event_type}"
                )


# ── Kernflow: lid worden ──────────────────────────────────────────────────────

def test_family_registration_logs_event_linked_to_member(client, db_session):
    seed_postal_code(db_session)
    resp = client.post("/api/v1/families", json=_family_payload(email="event-lid@example.com"))
    assert resp.status_code == 201, resp.text

    from app.models.member import Member
    from app.domains.payment_status.models import PaymentRecord
    member = db_session.query(Member).first()
    rec = db_session.query(PaymentRecord).filter(PaymentRecord.payable_type == "membership").first()

    events = _events(db_session, "lid_worden_voltooid")
    assert len(events) == 1
    ev = events[0]
    assert ev.member_id == member.id                 # juiste koppeling
    assert ev.payment_record_id == rec.id            # juist PaymentRecord
    assert ev.payload["payment_method"] == "transfer"
    assert "amount" in ev.payload
    _assert_no_pii_anywhere(db_session)


# ── Kernflow: activiteit inschrijven ──────────────────────────────────────────

def test_activity_registration_transfer_logs_inschrijving_event(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, price="10.00")
    activity_id = comp.activity_id
    resp = client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "Test", "contact_email": "deelnemer2@example.com",
        "component_id": comp.id, "payment_method": "transfer",
        "items": [{"product_id": product.id, "quantity": 2}],
    })
    assert resp.status_code in (200, 201), resp.text

    events = _events(db_session, "inschrijving_voltooid")
    assert len(events) == 1
    ev = events[0]
    assert ev.activity_id == activity_id
    assert ev.payload["paid"] is True
    assert ev.payment_record_id is not None
    _assert_no_pii_anywhere(db_session)


# ── Kernflow: hernieuwing + betaling (webhook) ────────────────────────────────

def test_renewal_and_payment_success_log_events(client, db_session, mock_mollie):
    email = "event-renew@example.com"
    member, _person = seed_household(db_session, email, with_membership=False)

    resp = client.post("/api/v1/member/household/renew-membership", headers=_headers(email))
    assert resp.status_code == 200, resp.text

    started = _events(db_session, "hernieuwing_gestart")
    assert len(started) == 1
    assert started[0].member_id == member.id
    assert "target_year" in started[0].payload

    # Mollie-webhook bevestigt de betaling -> betaling_succes event.
    hook = client.post("/api/v1/payment-gateway/webhooks/mollie", data={"id": "tr_test_123"})
    assert hook.status_code == 200, hook.text

    success = _events(db_session, "betaling_succes")
    assert len(success) == 1
    ev = success[0]
    assert ev.payment_record_id is not None
    assert ev.payload["payable_type"] == "membership"
    assert "amount" in ev.payload
    _assert_no_pii_anywhere(db_session)
