"""Tests voor het (her)activeren van een lidmaatschap vanuit het gezinscherm (#113).

Invarianten:
  - Vernieuwen maakt een nieuw (nog niet-actief) lidmaatschap + online betaling,
    zónder een nieuw gezin aan te maken.
  - Een geldig lidmaatschap blokkeert een tweede betaling (geen dubbele betaling).
  - De Mollie-webhook activeert het lidmaatschap bij bevestigde betaling.
  - /auth/member/me rapporteert de geldigheidsdatum voor het scherm.
"""

import pytest

from app.domains.auth.api import login_person_for_email
from app.domains.membership import household_service
from app.domains.membership.schemas_member import MembershipCreate
from app.domains.payment.api import PayableType
from tests import payments_door
from tests.conftest import renew_at_the_portal, seed_postal_code, seeded_admin, sign_up_at_the_door
from tests.integration.test_functional_regression import _family_payload
from tests.integration.test_membership_pricing import seed_household

pytestmark = pytest.mark.ui_agnostisch


def test_admin_created_membership_is_valid(client, db_session, admin_headers):
    """Admin 'Lid maken' moet een geldig lidmaatschap opleveren (met
    valid_from/valid_to), anders telt het nergens als geldig (#143)."""
    from datetime import date

    from app.domains.membership.api import has_valid_membership

    member, person = seed_household(db_session, "adminmade@example.com", with_membership=False)
    year = date.today().year
    made = household_service.create_membership_for_family(
        db_session,
        member.id,
        MembershipCreate(year=year, is_active=True),
        admin=seeded_admin(db_session),
    )
    assert made.valid_from is not None and made.valid_to is not None
    db_session.expire_all()
    assert has_valid_membership(person) is True


def test_manual_payment_confirmation_activates_membership(client, db_session, admin_headers):
    """Een handmatig bevestigde lidmaatschap-betaling (cash/overschrijving) moet het
    lidmaatschap activeren — net als de Mollie-webhook (#143)."""
    seed_postal_code(db_session)
    assert (
        sign_up_at_the_door(client, json=_family_payload(email="manualpay@example.com")).status_code
        == 201
    )

    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord

    rec = (
        db_session.query(PaymentRecord)
        .filter(PaymentRecord.payable_type == PayableType.MEMBERSHIP)
        .first()
    )
    assert rec is not None
    ms = db_session.query(Membership).first()
    assert ms.is_active is False  # nog niet betaald

    resp = payments_door.update(client, rec.id, {"status": "paid"})
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    ms = db_session.query(Membership).first()
    assert ms.is_active is True


def test_renew_creates_inactive_membership_and_checkout(client, db_session, mock_mollie):
    email = "renew@example.com"
    member, _person = seed_household(db_session, email, with_membership=False)

    resp = renew_at_the_portal(client, email)
    assert resp.status_code == 200, resp.text
    assert resp.json()["checkout_url"].startswith("https://mollie.test")

    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord

    ms = db_session.query(Membership).filter(Membership.member_id == member.id).first()
    assert ms is not None and ms.is_active is False  # pas actief na betaling
    rec = (
        db_session.query(PaymentRecord)
        .filter(PaymentRecord.payable_type == PayableType.MEMBERSHIP)
        .first()
    )
    assert rec.payable_id == ms.id


def test_renew_refused_when_already_valid(client, db_session, mock_mollie):
    email = "alvalid@example.com"
    seed_household(db_session, email)  # actief, geldig vandaag
    resp = renew_at_the_portal(client, email)
    assert resp.status_code == 409, resp.text


def test_membership_payment_description_uses_raak_not_kwb(client, db_session, monkeypatch):
    """De Mollie-omschrijving van een lidmaatschap-betaling vermeldt 'Raak
    Millegem', niet 'KWB' (#286)."""
    from app.config import settings
    from app.domains.payment.providers import mollie
    from app.domains.payment.providers.base import PaymentResult

    captured = {}

    def capture_create_payment(self, amount, description, redirect_url, webhook_url, metadata):
        captured["description"] = description
        return PaymentResult(
            provider_payment_id="tr_test_123",
            checkout_url="https://mollie.test/checkout/tr_test_123",
            status="pending",
        )

    monkeypatch.setattr(mollie.MollieProvider, "create_payment", capture_create_payment)

    email = "raakdesc@example.com"
    seed_household(db_session, email)  # actief, geldig dit jaar
    old = settings.membership_renewal_start_md
    settings.membership_renewal_start_md = "01-01"  # open het hernieuwingsvenster
    try:
        resp = renew_at_the_portal(client, email)
    finally:
        settings.membership_renewal_start_md = old
    assert resp.status_code == 200, resp.text

    desc = captured.get("description", "")
    assert desc.startswith("Raak Millegem lidmaatschap"), desc
    assert "KWB" not in desc


def test_double_renew_is_refused(client, db_session, mock_mollie):
    """Invariant: een tweede hernieuwing voor hetzelfde doeljaar wordt geweigerd
    (409) zodat er nooit een dubbel lidmaatschap of dubbele betaling ontstaat.
    Het venster staat open en het lid is nog geldig (vroeg hernieuwen)."""
    from app.config import settings
    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord

    email = "double@example.com"
    member, _person = seed_household(db_session, email)  # actief, geldig dit jaar

    old = settings.membership_renewal_start_md
    settings.membership_renewal_start_md = "01-01"
    try:
        first = renew_at_the_portal(client, email)
        assert first.status_code == 200, first.text
        second = renew_at_the_portal(client, email)
    finally:
        settings.membership_renewal_start_md = old

    assert second.status_code == 409, second.text
    # Geen dubbel lidmaatschap voor het doeljaar, geen tweede betaalrecord.
    memberships = db_session.query(Membership).filter(Membership.member_id == member.id).all()
    years = [m.year for m in memberships]
    assert len(years) == len(set(years))  # geen duplicaat (member_id, year)
    rec_count = (
        db_session.query(PaymentRecord)
        .filter(PaymentRecord.payable_type == PayableType.MEMBERSHIP)
        .count()
    )
    assert rec_count == 1


def test_early_renew_while_valid_targets_next_year(client, db_session, mock_mollie):
    """Met open hernieuwingsvenster mag een lid met een nog-geldig lidmaatschap
    vroeg hernieuwen. De nieuwe periode dekt het JAAR ná de huidige geldigheid —
    niet het lopende jaar (anders botst uq_memberships_member_year). Regressie #134-flow."""
    from datetime import date

    from app.config import settings
    from app.domains.membership.api import Membership

    email = "early@example.com"
    member, _person = seed_household(db_session, email)  # actief, geldig dit jaar
    this_year = date.today().year

    # Open het hernieuwingsvenster (1 januari) voor deze test.
    old = settings.membership_renewal_start_md
    settings.membership_renewal_start_md = "01-01"
    try:
        resp = renew_at_the_portal(client, email)
    finally:
        settings.membership_renewal_start_md = old

    assert resp.status_code == 200, resp.text

    # Er moet nu een lidmaatschap voor volgend jaar bestaan, naast dat van dit jaar.
    years = {
        ms.year
        for ms in db_session.query(Membership).filter(Membership.member_id == member.id).all()
    }
    assert this_year in years
    assert this_year + 1 in years

    # Een hernieuwing dekt een vol jaar → altijd volle prijs (geen halve-prijs-venster).
    from app.domains.payment.api import PaymentRecord

    rec = (
        db_session.query(PaymentRecord)
        .filter(PaymentRecord.payable_type == PayableType.MEMBERSHIP)
        .order_by(PaymentRecord.id.desc())
        .first()
    )
    assert rec.amount == settings.membership_price_full


def test_webhook_activates_membership_on_paid(client, db_session, mock_mollie):
    email = "activate@example.com"
    _member, person = seed_household(db_session, email, with_membership=False)
    assert renew_at_the_portal(client, email).status_code == 200

    # Mollie roept de webhook met de provider_payment_id (mock = tr_test_123).
    hook = client.post("/api/v1/payment-gateway/webhooks/mollie", data={"id": "tr_test_123"})
    assert hook.status_code == 200, hook.text

    from app.domains.membership.api import Membership, has_valid_membership

    ms = db_session.query(Membership).first()
    db_session.refresh(ms)
    assert ms.is_active is True
    db_session.refresh(person)
    assert has_valid_membership(person) is True


def test_a_signed_in_member_has_a_membership_that_is_valid_until_a_date(db_session):
    """Was `test_member_me_reports_membership_validity` (until CR-13 phase 4b, #1251, this asked a JSON route with a bearer token):
    the person the sign-in finds for the address, and the two facts the account
    page shows of the membership."""
    from app.domains.membership.api import has_valid_membership, valid_membership_until

    email = "mestatus@example.com"
    seed_household(db_session, email)
    person = login_person_for_email(db_session, email)
    assert person is not None
    assert has_valid_membership(person) is True
    assert valid_membership_until(person) is not None


def test_a_signed_in_person_without_a_membership_has_none(db_session):
    """Was `test_member_me_without_membership` (until CR-13 phase 4b, #1251, this asked a JSON route with a bearer token)."""
    from app.domains.membership.api import has_valid_membership, valid_membership_until

    email = "nomember@example.com"
    seed_household(db_session, email, with_membership=False)
    person = login_person_for_email(db_session, email)
    assert person is not None
    assert has_valid_membership(person) is False
    assert valid_membership_until(person) is None
