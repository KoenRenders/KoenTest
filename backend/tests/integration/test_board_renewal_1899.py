"""#1899 §4 — the board renews a household's membership from its record.

"Lidmaatschap vernieuwen" stands under Acties on the household's record when
membership's own rule says a renewal can start. It opens the page of the
member's own renewal in the admin shell (`_renewal_form.html`, one page for the
member and the board), and the renewal is the ONE renewal
(`portal_service.renew_membership`) for the household's main member — with the
board member in the history, and the household's record as the place the
provider returns to.

What is held here, through the routes:

- the record offers the renewal, and the page is the form in the admin shell,
  posting to the board's route — and neither is there once a renewal runs: the
  record shows the transfer to make instead, and the page lands on the record;
- a transfer writes the open payment and names the board member and the
  board's source in the history, where the member's own renewal names the
  member (the pair, so the first is the board's doing);
- online leaves with a hard redirect to the provider, who is told to return to
  the household's record;
- a household without a main member is offered nothing and is refused when
  the route is posted directly; an answer without a payment method is refused
  at the choice; neither writes anything.

In #1899 the renewal sends no mail: that is #1903.

Proven red (locally, restored), each by an addition:
- `or True` behind the head's condition for the action → "the record offers a
  second renewal while one runs";
- `source = "member_self"` put again under the line that chooses the source →
  "the history does not say the board did it";
- `return_path = None` at the top of `renew_membership` → "the provider is not
  sent back to the household's record";
- `if False and` put before the facade's check for a main member → the
  household without one fails on an AttributeError where the refusal stood.
"""

from __future__ import annotations

import pytest

from app.domains.mdm.api import MemberPerson
from app.domains.membership.api import Membership, MembershipHistory, open_renewal_payment
from app.domains.payment.api import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL, board_session, create_test_family

pytestmark = pytest.mark.ui_serverrendered

FORM = 'id="vernieuw-form"'
RUNNING = "data-renewal-running"


def _record(household_id: int) -> str:
    return f"/admin/leden/gezin/{household_id}"


def _page(household_id: int) -> str:
    return f"{_record(household_id)}/vernieuwen"


def _offer(household_id: int) -> str:
    return f'href="{_page(household_id)}"'


def _written(db) -> tuple[int, int, int]:
    return (
        db.query(Membership).count(),
        db.query(PaymentRecord).count(),
        db.query(MembershipHistory).count(),
    )


def _started(db, member) -> MembershipHistory:
    return (
        db.query(MembershipHistory)
        .filter_by(member_id=member.id, action="membership_renewal_started")
        .one()
    )


def test_the_record_offers_it_and_the_page_is_the_form_in_the_admin_shell(client, db_session):
    member, _person = create_test_family(db_session, email="aanbod-1899@example.com")
    db_session.commit()
    board_session(client)

    assert _offer(member.id) in client.get(_record(member.id)).text

    answer = client.get(_page(member.id))
    assert answer.status_code == 200
    assert FORM in answer.text and f'hx-post="{_page(member.id)}"' in answer.text
    assert 'data-shell="admin"' in answer.text, "not the admin shell"
    assert "Dit gezin heeft momenteel geen geldig lidmaatschap." in answer.text
    assert "Je gezin" not in answer.text, "the board is addressed as the member"
    assert 'name="payment_method"' in answer.text


def test_a_transfer_runs_on_the_record_and_names_the_board_member(client, db_session):
    member, _person = create_test_family(db_session, email="overschrijving-1899@example.com")
    db_session.commit()
    headers = board_session(client)

    answer = client.post(_page(member.id), data={"payment_method": "transfer"}, headers=headers)

    assert answer.status_code == 200, answer.text[:300]
    assert answer.headers["HX-Redirect"] == _record(member.id)
    db_session.expire_all()
    open_payment = open_renewal_payment(db_session, member)
    assert open_payment is not None and open_payment.method.value == "transfer"
    history = _started(db_session, member)
    assert (history.source, history.actor) == ("admin_manual", SEEDED_ADMIN_EMAIL), (
        "the history does not say the board did it"
    )

    record = client.get(_record(member.id)).text
    assert RUNNING in record and open_payment.structured_communication in record
    assert _offer(member.id) not in record, "the record offers a second renewal while one runs"
    again = client.get(_page(member.id), follow_redirects=False)
    assert again.status_code == 303 and again.headers["location"] == _record(member.id)


def test_the_members_own_renewal_still_names_the_member(client, db_session):
    """The other half of the pair above: without the board, the member's source."""
    from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value

    member, _person = create_test_family(db_session, email="zelf-1899@example.com")
    db_session.commit()
    value = make_session_value("zelf-1899@example.com")
    client.cookies.set(SESSION_COOKIE, value)

    answer = client.post(
        "/leden/gezin/vernieuwen",
        data={"payment_method": "transfer"},
        headers={"X-CSRF-Token": csrf_token_for(value)},
    )

    assert answer.status_code == 200 and answer.headers["HX-Redirect"] == "/leden/gezin"
    history = _started(db_session, member)
    assert (history.source, history.actor) == ("member_self", "zelf-1899@example.com")


def test_online_leaves_for_the_provider_who_returns_to_the_record(
    client, db_session, mock_mollie, monkeypatch
):
    from app.domains.payment.providers import mollie
    from app.domains.payment.providers.base import PaymentResult

    told = {}

    def create_payment(self, amount, description, redirect_url, webhook_url, metadata):
        told["redirect_url"] = redirect_url
        return PaymentResult(
            provider_payment_id="tr_test_1899",
            checkout_url="https://mollie.test/checkout/tr_test_1899",
            status="pending",
        )

    monkeypatch.setattr(mollie.MollieProvider, "create_payment", create_payment)
    member, _person = create_test_family(db_session, email="online-1899@example.com")
    db_session.commit()
    headers = board_session(client)

    answer = client.post(_page(member.id), data={"payment_method": "online"}, headers=headers)

    assert answer.status_code == 200, answer.text[:300]
    assert answer.headers["HX-Redirect"] == "https://mollie.test/checkout/tr_test_1899"
    assert answer.text == ""
    assert told["redirect_url"].endswith(_record(member.id)), (
        f"the provider is not sent back to the household's record: {told['redirect_url']}"
    )


def test_a_household_without_a_main_member_is_offered_nothing_and_refused(client, db_session):
    member, person = create_test_family(db_session, email="geenhoofd-1899@example.com")
    link = db_session.query(MemberPerson).filter_by(member_id=member.id, person_id=person.id).one()
    link.relation_type = "PARTNER"
    db_session.commit()
    headers = board_session(client)
    before = _written(db_session)

    assert _offer(member.id) not in client.get(_record(member.id)).text
    page = client.get(_page(member.id), follow_redirects=False)
    assert page.status_code == 303 and page.headers["location"] == _record(member.id)

    answer = client.post(_page(member.id), data={"payment_method": "transfer"}, headers=headers)

    assert answer.status_code == 422, answer.status_code
    assert answer.headers["HX-Retarget"] == "#vernieuw-melding"
    assert "Dit gezin heeft geen hoofdlid: vernieuwen kan niet." in answer.text
    db_session.expire_all()
    assert _written(db_session) == before, "a refused renewal wrote something"


def test_without_a_payment_method_it_is_refused_at_the_choice(client, db_session):
    member, _person = create_test_family(db_session, email="geenkeuze-1899@example.com")
    db_session.commit()
    headers = board_session(client)
    before = _written(db_session)

    answer = client.post(_page(member.id), data={}, headers=headers)

    assert answer.status_code == 422
    assert "Kies een betaalwijze." in answer.text
    db_session.expire_all()
    assert _written(db_session) == before
