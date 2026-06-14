"""Tests voor het (her)activeren van een lidmaatschap vanuit het gezinscherm (#113).

Invarianten:
  - Vernieuwen maakt een nieuw (nog niet-actief) lidmaatschap + online betaling,
    zónder een nieuw gezin aan te maken.
  - Een geldig lidmaatschap blokkeert een tweede betaling (geen dubbele betaling).
  - De Mollie-webhook activeert het lidmaatschap bij bevestigde betaling.
  - /auth/member/me rapporteert de geldigheidsdatum voor het scherm.
"""
from app.auth import create_access_token
from tests.test_membership_pricing import seed_household


def _headers(email):
    return {"Authorization": f"Bearer {create_access_token({'sub': email})}"}


def test_renew_creates_inactive_membership_and_checkout(client, db_session, mock_mollie):
    email = "renew@example.com"
    member, _person = seed_household(db_session, email, with_membership=False)

    resp = client.post("/api/v1/member/household/renew-membership", headers=_headers(email))
    assert resp.status_code == 200, resp.text
    assert resp.json()["checkout_url"].startswith("https://mollie.test")

    from app.models.member import Membership
    from app.domains.payment_status.models import PaymentRecord
    ms = db_session.query(Membership).filter(Membership.member_id == member.id).first()
    assert ms is not None and ms.is_active is False  # pas actief na betaling
    rec = db_session.query(PaymentRecord).filter(PaymentRecord.payable_type == "membership").first()
    assert rec.payable_id == ms.id


def test_renew_refused_when_already_valid(client, db_session, mock_mollie):
    email = "alvalid@example.com"
    seed_household(db_session, email)  # actief, geldig vandaag
    resp = client.post("/api/v1/member/household/renew-membership", headers=_headers(email))
    assert resp.status_code == 409, resp.text


def test_early_renew_while_valid_targets_next_year(client, db_session, mock_mollie):
    """Met open hernieuwingsvenster mag een lid met een nog-geldig lidmaatschap
    vroeg hernieuwen. De nieuwe periode dekt het JAAR ná de huidige geldigheid —
    niet het lopende jaar (anders botst uq_memberships_member_year). Regressie #134-flow."""
    from datetime import date
    from app.config import settings
    from app.models.member import Membership

    email = "early@example.com"
    member, _person = seed_household(db_session, email)  # actief, geldig dit jaar
    this_year = date.today().year

    # Open het hernieuwingsvenster (1 januari) voor deze test.
    old = settings.membership_renewal_start_md
    settings.membership_renewal_start_md = "01-01"
    try:
        resp = client.post("/api/v1/member/household/renew-membership", headers=_headers(email))
    finally:
        settings.membership_renewal_start_md = old

    assert resp.status_code == 200, resp.text

    # Er moet nu een lidmaatschap voor volgend jaar bestaan, naast dat van dit jaar.
    years = {ms.year for ms in db_session.query(Membership).filter(Membership.member_id == member.id).all()}
    assert this_year in years
    assert this_year + 1 in years


def test_webhook_activates_membership_on_paid(client, db_session, mock_mollie):
    email = "activate@example.com"
    _member, person = seed_household(db_session, email, with_membership=False)
    assert client.post("/api/v1/member/household/renew-membership", headers=_headers(email)).status_code == 200

    # Mollie roept de webhook met de provider_payment_id (mock = tr_test_123).
    hook = client.post("/api/v1/payment-gateway/webhooks/mollie", data={"id": "tr_test_123"})
    assert hook.status_code == 200, hook.text

    from app.models.member import Membership
    from app.services.membership import has_valid_membership
    ms = db_session.query(Membership).first()
    db_session.refresh(ms)
    assert ms.is_active is True
    db_session.refresh(person)
    assert has_valid_membership(person) is True


def test_member_me_reports_membership_validity(client, db_session):
    email = "mestatus@example.com"
    seed_household(db_session, email)
    resp = client.get("/api/v1/auth/member/me", headers=_headers(email))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_valid_membership"] is True
    assert body["membership_valid_until"] is not None


def test_member_me_without_membership(client, db_session):
    email = "nomember@example.com"
    seed_household(db_session, email, with_membership=False)
    resp = client.get("/api/v1/auth/member/me", headers=_headers(email))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_valid_membership"] is False
    assert body["membership_valid_until"] is None
