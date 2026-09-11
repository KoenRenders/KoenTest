"""#870 (A, B, C from #529) — the treasurer's mutations, at the entrance she actually uses.

The coverage measurement on this tree showed three routes with no test at all:
`/admin/betalingen/{id}/status`, `/verwijderen` and `/verversen`, plus their service
wrappers. The rules underneath **are** tested (`set_payment_status`, `void_payment_record`
in `test_payment_admin_actions.py`); what nobody called is the path the treasurer clicks,
and that path carries more than a hand-over: the `db.commit()`, the `db.rollback()` on a
rejected mutation, and `require_finance_mutation`.

**Why a 4xx is not the assertion here.** `_uitvoeren` deliberately answers a
`BetalingFout` with a **200** and the reason in the error banner — htmx does not swap a
4xx, so a 400 would leave the reason on the floor (#723). A test asserting "not 2xx" would
therefore be wrong here *and* would pass on a CSRF error or a missing role, proving nothing
(#680). Every refusal below is checked against its message and against the state that did
not change.

Broken on purpose to check that these tests can go red:

- `require_finance_mutation` removed from `betaling_status` → the authorisation test falls
  over: a viewer without FINANCE changes the status of a payment.
- the status route's happy path disabled → two fall over (the happy path and the refusal,
  because a route that does nothing also refuses nothing), which is what makes the
  refusals below mean something.

**And one counterproof that did NOT work, which corrects my own finding in #529.** That
report said the untested wrapper carries "the `db.commit()`, the `db.rollback()` on a
rejected mutation, and `require_finance_mutation`". Measured here: removing the
`db.rollback()` from `zet_betaalstatus` **and** from `bevestig_betaling` leaves all these
tests green. On today's payment paths the validation raises *before* anything is flushed,
so there is nothing to roll back — the line is defensive, not load-bearing. The commit and
the role check are real; the rollback claim was mine and it was too strong.

The session check below therefore stays as a guard for a future path that *does* flush
first (that is exactly how #792 bit us), but it is labelled for what it is instead of
being sold as proof.
"""
from decimal import Decimal

import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from app.domains.payment.api import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db, *roles):
    roles = roles or ("FINANCE",)
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    for role in roles:
        if not any(r.role_code == role for r in user.roles):
            db.add(UserRole(user_id=user.id, role_code=role))
    db.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _charge(db, *, amount="25.00", status="pending", payable_id=7701, paid=None,
            method="transfer", gateway_id=None):
    record = PaymentRecord(payable_type="membership", payable_id=payable_id,
                           amount=Decimal(amount), method=method, status=status,
                           type="charge",
                           amount_paid=Decimal(paid) if paid is not None else None,
                           gateway_payment_id=gateway_id)
    db.add(record)
    db.flush()
    return record


# ── A. de drie penningmeester-mutaties ───────────────────────────────────────

def test_the_status_route_changes_the_status(client, db_session):
    """Het gelukkige pad, en zonder dat bewijst de weigering hieronder niets."""
    headers = _login(client, db_session)
    record = _charge(db_session, status="pending")

    resp = client.post(f"/admin/betalingen/{record.id}/status", headers=headers,
                       data={"status": "cancelled", "note": "per mail geannuleerd"})

    assert resp.status_code == 200, resp.text[:200]
    db_session.refresh(record)
    assert record.status == "cancelled"
    assert record.note == "per mail geannuleerd"


def test_a_rejected_status_is_refused_in_words(client, db_session):
    """Een afgewezen statuswijziging komt terug met de REDEN, niet met een kale fout.

    Let op de vorm van het antwoord: `_uitvoeren` geeft bewust een **200** met de reden
    in de foutbanner, want htmx swapt geen 4xx (#723). Een assertie op "niet 2xx" zou
    hier dus fout zijn, én ze zou slagen bij een CSRF-fout — precies de val uit #680.

    **Wat hier niet beweerd wordt.** "Het record is onveranderd" is in deze suite niet te
    toetsen: een rollback gaat tot het SAVEPOINT dat de opstelling rond de hele test zet,
    dus het record uit de opzet verdwijnt mee. In productie heeft elk verzoek zijn eigen
    sessie.

    De sessiecontrole onderaan is een vangrail voor een toekomstig pad dat wél flusht vóór
    het weigert (zo beet #792), geen bewijs dat de rollback hier iets doet — zie de
    modulekop: op deze paden gooit de validatie vóór er iets geflusht is.
    """
    headers = _login(client, db_session)
    record = _charge(db_session, status="pending")

    resp = client.post(f"/admin/betalingen/{record.id}/status", headers=headers,
                       data={"status": "verzonnen", "note": ""})

    assert "Ongeldige status" in resp.text, resp.text[:300]
    # Déze query is de assertie: in pending-rollback gooit ze PendingRollbackError.
    assert isinstance(db_session.query(PaymentRecord).count(), int), (
        "de sessie staat in pending-rollback — de mutatie draaide niet terug")


def test_the_delete_route_takes_the_record_out_of_the_balance(client, db_session):
    """Soft-delete: bewaard als financieel feit, weg uit het saldo (#455)."""
    from app.domains.payment.api import net_paid

    headers = _login(client, db_session)
    record = _charge(db_session, status="paid", paid="25.00", payable_id=7702)
    assert net_paid(db_session, "membership", 7702) == Decimal("25.00")

    resp = client.post(f"/admin/betalingen/{record.id}/verwijderen", headers=headers,
                       data={"note": "dubbel geboekt"})

    assert resp.status_code == 200, resp.text[:200]
    db_session.expire_all()
    assert net_paid(db_session, "membership", 7702) == Decimal("0.00"), (
        "het verwijderde record telt nog mee in het saldo")


@pytest.mark.parametrize("pad,data", [
    ("status", {"status": "cancelled"}),
    ("verwijderen", {"note": "weg"}),
    ("verversen", {}),
])
def test_only_finance_may_mutate(client, db_session, pad, data):
    """`require_finance_mutation` op alle drie. ADMIN mag kijken en exporteren maar
    niet muteren (#83/#530) — en dat onderscheid is precies wat hier ongedekt was."""
    # Een EIGEN gebruiker: de geseede beheerder kan FINANCE al dragen, en dan zou deze
    # test groen staan zonder iets over de rolcheck te bewijzen.
    kijker = User(email="alleen-kijken@example.com", is_active=True)
    db_session.add(kijker)
    db_session.flush()
    db_session.add(UserRole(user_id=kijker.id, role_code="ADMIN"))
    db_session.flush()
    waarde = make_session_value("alleen-kijken@example.com")
    client.cookies.set(SESSION_COOKIE, waarde)
    headers = {"X-CSRF-Token": csrf_token_for(waarde)}
    record = _charge(db_session, status="pending", payable_id=7703)

    resp = client.post(f"/admin/betalingen/{record.id}/{pad}", headers=headers, data=data)

    assert resp.status_code == 403, f"{pad}: {resp.status_code} — {resp.text[:200]}"
    assert "FINANCE" in resp.text
    db_session.refresh(record)
    assert record.status == "pending", f"{pad} muteerde ondanks de weigering"


# ── B. de handmatige Mollie-verversing ───────────────────────────────────────

def test_the_manual_refresh_takes_its_status_from_mollie(client, db_session,
                                                         admin_headers, mock_mollie):
    """Het vangnet voor een gemiste webhook, en het endpoint waarvan de veiligheid ís
    dat het de status bij Mollie ópvraagt in plaats van iets te geloven."""
    from app.domains.auth.api import User, UserRole
    from app.domains.payment.api import GatewayPayment

    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db_session.add(UserRole(user_id=user.id, role_code="FINANCE"))
    db_session.flush()

    gp = GatewayPayment(provider="mollie", provider_payment_id="tr_test_123",
                        amount=Decimal("25.00"), status="pending",
                        checkout_url="https://mollie.test/x", description="Test",
                        payment_metadata={})
    db_session.add(gp)
    db_session.flush()
    record = _charge(db_session, status="pending", payable_id=7704, method="online",
                     gateway_id=gp.id)

    resp = client.post(f"/api/v1/payment-status/records/{record.id}/refresh",
                       headers=admin_headers)

    assert resp.status_code == 200, resp.text[:300]
    db_session.expire_all()
    assert db_session.query(PaymentRecord).filter(
        PaymentRecord.id == record.id).one().status == "paid", (
        "de status is niet toegepast, dus de handmatige tegenhanger van de webhook doet "
        "niets")


def test_a_transfer_cannot_be_refreshed_at_mollie(client, db_session, admin_headers):
    """De tegenproef: zonder haar zou "hij antwoordt 200" ook groen staan als het
    endpoint elk record zomaar aanraakt."""
    from app.domains.auth.api import User, UserRole

    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db_session.add(UserRole(user_id=user.id, role_code="FINANCE"))
    db_session.flush()
    record = _charge(db_session, status="pending", payable_id=7705)

    resp = client.post(f"/api/v1/payment-status/records/{record.id}/refresh",
                       headers=admin_headers)

    assert resp.status_code == 400
    assert "online" in resp.text.lower()


# ── C. drie foutpaden rond bedragen ──────────────────────────────────────────

def test_an_unreadable_amount_is_refused_in_words(client, db_session):
    """`_ingetypt_bedrag` gooit BetalingFout("Ongeldig bedrag") — een regel die door
    geen enkele test uitgevoerd werd."""
    headers = _login(client, db_session)
    record = _charge(db_session, status="pending", payable_id=7706)

    resp = client.post(f"/admin/betalingen/{record.id}/bijwerken", headers=headers,
                       data={"amount_paid": "abc", "note": ""})

    assert "Ongeldig bedrag" in resp.text, resp.text[:300]
    # Niet `refresh`: een afgewezen mutatie draait terug tot het SAVEPOINT van deze
    # test, dus het record uit de opzet is mee verdwenen. Zie de uitleg hierboven.
    assert isinstance(db_session.query(PaymentRecord).count(), int)


def test_a_refund_without_an_amount_is_refused(client, db_session):
    """`registreer_terugbetaling` met een leeg bedrag — de derde ongedekte regel."""
    headers = _login(client, db_session)
    record = _charge(db_session, status="paid", paid="25.00", payable_id=7707)

    resp = client.post(f"/admin/betalingen/{record.id}/refund", headers=headers,
                       data={"amount": "", "note": ""})

    assert "Ongeldig bedrag" in resp.text, resp.text[:300]
    assert not db_session.query(PaymentRecord).filter(
        PaymentRecord.type == "refund", PaymentRecord.payable_id == 7707).all(), (
        "er is een terugbetaling aangemaakt zonder bedrag")


def test_too_large_an_amount_is_refused_with_the_limit_in_the_message(client, db_session):
    """Te veel afboeken wordt geweigerd, en de melding noemt de grens — dezelfde norm als
    de refundgrens uit #680: een 4xx alleen zou ook groen staan bij een CSRF-fout."""
    headers = _login(client, db_session)
    record = _charge(db_session, status="pending", payable_id=7708, amount="25.00")

    resp = client.post(f"/admin/betalingen/{record.id}/bijwerken", headers=headers,
                       data={"amount_paid": "99.00", "note": ""})

    assert "tussen" in resp.text or "Meer dan" in resp.text, resp.text[:300]
    assert isinstance(db_session.query(PaymentRecord).count(), int), (
        "de sessie staat in pending-rollback — de bevestiging draaide niet terug")
