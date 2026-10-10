"""An e-mail row refuses a text that is no address (#1853).

mdm had no rule for the shape of an e-mail address. Two fields got one in pull
request #1844, through their request schemas; the e-mail ROWS — the extra
addresses on a person's card, the same rows in Mijn gezin — and an
organisation's address still took any text. The address was stored, used as a
recipient, and the mail never left without anybody noticing.

The rule has one home now: the contact detail itself (`ContactDetail.check`,
held at every flush), judged by `require_email_address`. These tests read each
door of the back office as the screen gets it — the sentence, where it is sent,
and that nothing was written. Mijn gezin and Mijn gegevens are held in
`test_household_save.py` (the row's own field) and in the browser.

Red proofs, one replacement each, the tree as before afterwards — the counts
stand in the pull request.
"""

from __future__ import annotations

import pytest

from app.domains.mdm.api import ContactDetail, EmailAddressInvalid
from app.domains.mdm.models import require_email_address
from app.domains.mdm.tests.test_household_cards_say_why_1831 import (  # noqa: F401
    CARD,
    World,
    _state,
    world,
)
from tests._refusal import heading, message_line, said

pytestmark = pytest.mark.ui_serverrendered

RULE = "Vul een geldig e-mailadres in."
NO_ADDRESS = pytest.mark.parametrize(
    "typed",
    [
        "hanne",
        "hanne@",
        "@example.com",
        "hanne proef@example.com",
        "hanne@example",
        "a@b@example.com",
    ],
    ids=["no at", "nothing after the at", "nothing before the at", "a space", "no dot", "two ats"],
)


# ── the rule itself ──────────────────────────────────────────────────────────


@NO_ADDRESS
def test_a_text_that_is_no_address_is_refused(typed):
    with pytest.raises(EmailAddressInvalid) as refused:
        require_email_address(typed)
    assert str(refused.value) == RULE


@pytest.mark.parametrize(
    "typed", ["hanne@example.com", "Hanne.Proef+raak@Example.COM", "h@sub.example.org"]
)
def test_an_address_is_let_through_as_typed(typed):
    """Judged, not rewritten: the rule returns nothing."""
    assert require_email_address(typed) is None


def test_the_contact_detail_holds_the_rule_at_the_flush(db_session, world):  # noqa: F811
    """The net under every door: a row written past the doors is refused too."""
    row = (
        db_session.query(ContactDetail)
        .filter_by(person_id=world.main, contact_type_code="EMAIL")
        .one()
    )
    row.value = "geen adres"
    with pytest.raises(EmailAddressInvalid):
        db_session.flush()
    db_session.rollback()


def test_a_telephone_row_is_not_judged_as_an_address(db_session, world):  # noqa: F811
    db_session.add(
        ContactDetail(person_id=world.partner, contact_type_code="PHONE", value="014 00 00 00")
    )
    db_session.flush()


# ── a person's card on the Leden screen ──────────────────────────────────────


def _refused_in_the_card(answer, person_id: int) -> None:
    assert answer.status_code == 422, answer.text[:200]
    assert heading(answer) == "Opslaan is niet gelukt."
    assert said(answer) == [RULE]
    assert message_line(answer) == f"#persoon-{person_id}-melding"


@NO_ADDRESS
def test_a_new_row_on_a_persons_card_says_why(client, db_session, world, typed):  # noqa: F811
    before = _state(db_session)

    answer = client.post(
        f"/admin/leden/gezin/{world.household}/persoon/{world.partner}",
        data=CARD | {"email_new_0": typed},
        headers=world.headers,
    )

    _refused_in_the_card(answer, world.partner)
    assert _state(db_session) == before


def test_an_existing_row_changed_into_no_address_says_why(client, db_session, world):  # noqa: F811
    row = (
        db_session.query(ContactDetail)
        .filter_by(person_id=world.main, contact_type_code="EMAIL")
        .one()
    )
    card = CARD | {"first_name": "Hanne", "gender_code": "F", "relation_type": "HOOFDLID"}
    before = _state(db_session)

    answer = client.post(
        f"/admin/leden/gezin/{world.household}/persoon/{world.main}",
        data=card
        | {"mobile": "0470 00 00 01", f"email_existing_{row.id}": "hanne-zonder-apenstaart"},
        headers=world.headers,
    )

    _refused_in_the_card(answer, world.main)
    assert _state(db_session) == before


def test_the_add_address_button_of_a_card_says_why(client, db_session, world):  # noqa: F811
    before = _state(db_session)

    answer = client.post(
        f"/admin/leden/gezin/{world.household}/persoon/{world.partner}/email",
        data={"extra_email": "bram zonder adres"},
        headers=world.headers,
    )

    _refused_in_the_card(answer, world.partner)
    assert _state(db_session) == before


def test_a_good_row_is_still_written(client, db_session, world):  # noqa: F811
    answer = client.post(
        f"/admin/leden/gezin/{world.household}/persoon/{world.partner}",
        data=CARD | {"email_new_0": "bram-1853@example.com"},
        headers=world.headers,
    )

    assert answer.status_code == 200, answer.text[:200]
    db_session.expire_all()
    assert db_session.query(ContactDetail).filter_by(value="bram-1853@example.com").count() == 1


# ── the application's own answer, for a door that has none of its own ────────


def test_a_door_without_an_answer_of_its_own_still_says_the_rule(
    client,
    db_session,
    world,  # noqa: F811
    monkeypatch,
):
    """The rule is held at the flush, so it can surface at any door. One that does
    not answer it itself gets the application's answer — the rule's sentence in a
    422, never "Interne serverfout". Shown on a door that writes no address text:
    its service is made to refuse the way a flush would."""
    import app.domains.mdm.api as mdm

    def refuses(*_args, **_kwargs):
        raise EmailAddressInvalid(RULE)

    monkeypatch.setattr(mdm, "make_email_primary", refuses)
    row = (
        db_session.query(ContactDetail)
        .filter_by(person_id=world.main, contact_type_code="EMAIL")
        .one()
    )

    answer = client.post(
        f"/admin/leden/gezin/{world.household}/persoon/{world.main}/email/{row.id}/hoofd",
        headers=world.headers,
    )

    assert answer.status_code == 422
    assert answer.json()["detail"] == RULE
