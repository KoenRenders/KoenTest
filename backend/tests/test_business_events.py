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


def _seed_payment(db, *, amount, amount_paid, type="charge", method="transfer",
                  status="paid", paid_at=None, payable_type="registration", payable_id=1):
    """Maak een PaymentRecord aan voor de omzet-/event-tests."""
    from decimal import Decimal
    from datetime import datetime, timezone
    from app.domains.payment_status.models import PaymentRecord
    rec = PaymentRecord(
        payable_type=payable_type, payable_id=payable_id,
        amount=Decimal(amount),
        amount_paid=(Decimal(amount_paid) if amount_paid is not None else None),
        method=method, status=status, type=type,
        paid_at=(paid_at if paid_at is not None
                 else (datetime.now(timezone.utc) if amount_paid is not None else None)),
    )
    db.add(rec)
    db.flush()
    return rec


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

    from app.domains.mdm.api import Member
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


# ── Admin-rapport over de business-events ─────────────────────────────────────

def test_business_event_stats_counts_per_type(client, db_session, admin_headers):
    """Het admin-rapport telt de events per type (conversie-/funnelinzicht)."""
    log_business_event(db_session, "betaling_succes", payload={"amount": "35.00"})
    log_business_event(db_session, "betaling_succes", payload={"amount": "10.00"})
    log_business_event(db_session, "betaling_geannuleerd", payload={"amount": "5.00"})
    log_business_event(db_session, "inschrijving_voltooid", payload={"amount": "10.00", "paid": True})
    db_session.flush()

    resp = client.get("/api/v1/admin/business-events", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["totals"]["betaling_succes"] == 2
    assert body["totals"]["betaling_geannuleerd"] == 1
    assert body["totals"]["inschrijving_voltooid"] == 1


def test_business_event_stats_revenue_from_payment_records(client, db_session, admin_headers):
    """Omzet komt uit de PaymentRecords zelf (#324), niet uit de event-stream:
    alle betaalwijzen tellen mee, refunds worden afgetrokken, en betalingen van
    vóór de events-meting tellen gewoon mee. Een onbetaalde charge telt als 0."""
    from datetime import datetime, timezone, timedelta
    # Drie geslaagde charges via verschillende betaalwijzen = 40 bruto ontvangen.
    _seed_payment(db_session, amount="20.00", amount_paid="20.00", method="online", payable_id=1)
    _seed_payment(db_session, amount="10.00", amount_paid="10.00", method="transfer", payable_id=2)
    _seed_payment(db_session, amount="10.00", amount_paid="10.00", method="cash", payable_id=3)
    # Eén terugbetaling van 10 -> netto 30.
    _seed_payment(db_session, amount="-10.00", amount_paid="-10.00", type="refund", payable_id=2)
    # Een nog niet betaalde charge mag niet meetellen.
    _seed_payment(db_session, amount="15.00", amount_paid=None, status="pending", payable_id=4)
    # Een oude betaling (>30 dagen) telt wel in het totaal, niet in 30d.
    old = datetime.now(timezone.utc) - timedelta(days=45)
    _seed_payment(db_session, amount="100.00", amount_paid="100.00", method="online",
                  payable_id=5, paid_at=old)
    db_session.flush()

    body = client.get("/api/v1/admin/business-events", headers=admin_headers).json()
    assert body["revenue_paid_eur"] == 130.0       # 40 - 10 refund + 100 oud
    assert body["revenue_paid_eur_30d"] == 30.0     # 40 - 10, zonder de oude 100


# ── Events bij handmatige bevestiging en terugbetaling (#324) ─────────────────

def test_confirm_manual_payment_logs_success_event(db_session):
    """Overschrijving/cash bevestigd via de admin moet óók een betaling_succes
    event loggen — anders mist het rapport alle niet-online betalingen."""
    from app.domains.payment_status.service import confirm_manual_payment
    charge = _seed_payment(db_session, amount="20.00", amount_paid=None, status="pending",
                           method="transfer")
    confirm_manual_payment(db_session, charge.id, actor="admin@test")
    evs = _events(db_session, "betaling_succes")
    assert len(evs) == 1
    assert evs[0].payment_record_id == charge.id
    assert evs[0].payload["method"] == "transfer"
    # Idempotent: nogmaals bevestigen telt niet dubbel.
    confirm_manual_payment(db_session, charge.id, actor="admin@test")
    assert len(_events(db_session, "betaling_succes")) == 1


def test_settled_refund_logs_refund_event(db_session):
    from app.domains.payment_status.service import create_refund
    from decimal import Decimal
    charge = _seed_payment(db_session, amount="20.00", amount_paid="20.00", payable_id=7)
    create_refund(db_session, charge.id, Decimal("20.00"), actor="admin@test")
    evs = _events(db_session, "betaling_terugbetaling")
    assert len(evs) == 1
    assert evs[0].payload["payable_type"] == "registration"


def test_pending_refund_logs_event_only_when_confirmed(db_session):
    """Een nog niet uitbetaalde terugbetaling (verplichting) logt nog niets; het
    event volgt pas wanneer de penningmeester de terugstorting bevestigt."""
    from app.domains.payment_status.service import create_refund, confirm_manual_payment
    from decimal import Decimal
    charge = _seed_payment(db_session, amount="20.00", amount_paid="20.00", payable_id=8)
    refund = create_refund(db_session, charge.id, Decimal("20.00"), settled=False)
    assert _events(db_session, "betaling_terugbetaling") == []
    confirm_manual_payment(db_session, refund.id, actor="admin@test")
    assert len(_events(db_session, "betaling_terugbetaling")) == 1


def test_business_event_stats_requires_admin(client, db_session):
    """Het rapport is admin-only — geen token mag geen cijfers prijsgeven."""
    resp = client.get("/api/v1/admin/business-events")
    assert resp.status_code in (401, 403)


def test_revenue_30d_includes_amount_paid_without_paid_at(client, db_session, admin_headers):
    """#346: een bewerkt record met amount_paid maar zónder paid_at telt in het
    totaal; het 30d-venster (COALESCE paid_at, created_at) rekent het via het
    recente created_at mee, zodat totaal == 30d op een jonge app."""
    from decimal import Decimal
    from app.domains.payment_status.models import PaymentRecord
    rec = PaymentRecord(
        payable_type="registration", payable_id=99,
        amount=Decimal("65.00"), amount_paid=Decimal("65.00"),
        method="transfer", status="pending", type="charge", paid_at=None,
    )
    db_session.add(rec)
    db_session.flush()
    body = client.get("/api/v1/admin/business-events", headers=admin_headers).json()
    assert body["revenue_paid_eur"] == 65.0
    assert body["revenue_paid_eur_30d"] == 65.0
