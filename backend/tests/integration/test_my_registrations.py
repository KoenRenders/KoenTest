"""Mijn inschrijvingen (CR-22 S5, #1709; R8, R23, R27; C6 T10, T12, T19, and the
rest of T18).

- a member sees his HOUSEHOLD's registrations, newest first, each with what was
  ordered, the amount and how its payment stands; a person without a household
  sees his own (T10);
- **a guest's registration — the same e-mail address, no person — is in nobody's
  list** (R23);
- **a registration the board made on a person's address is linked to that person
  and stands in his list** (Koen, 7 October 2026), and the board's form said so
  before saving;
- a registration still to be paid by transfer shows the SAME block as a renewal —
  `data-transfer-due`, from the one partial — with its own amount and reference;
  a paid one shows none (T19);
- the landing page shows the latest registration, and no card when there is none
  (T18);
- the hint above the registration form has the words of CR-22, and names no
  membership where the tenant has no members (T12, Q39).

Red (each restored after): the person filter of `my_registrations` replaced by
the contact e-mail → the guest's registration appears; `_transfer` returning
None → the transfer block is gone; the `has_members` condition taken out of the
hint → the tenant without members reads "of ben je lid"; the link notice's
include taken out of the price refresh → the board's answer names nobody.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domains.activities.api import Registration, RegistrationItem, my_registrations
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm import tenant_lookup
from app.domains.mdm.api import MemberPerson, Person, invalidate_tenant_codes
from app.domains.payment.api import PaymentRecord
from app.kernel.modules import ModuleCode
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    create_test_family,
    create_test_person,
    seed_activity_with_product,
)

pytestmark = pytest.mark.ui_serverrendered

EMAIL = "lid-1709@example.org"
OGM = "+++170/9000/00123+++"


def _main(html: str) -> str:
    return html[html.index('<main id="main"') : html.index("</main>")]


def _cards(html: str) -> list[str]:
    main = _main(html)
    return [
        "<section" + part
        for part in main.split("<section")[1:]
        if "data-my-registration" in part.split(">")[0]
    ]


def _registration(db, activity, component, product, *, person, quantity=2, days_ago=0, email=EMAIL):
    reg = Registration(
        activity_id=activity.id,
        component_id=component.id,
        person_id=person.id if person is not None else None,
        registration_type="INDIVIDUAL",
        contact_name="Emma Voorbeeld",
        contact_email=email,
        phone="0470 00 00 00",
        registered_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db.add(reg)
    db.flush()
    db.add(RegistrationItem(registration_id=reg.id, product_id=product.id, quantity=quantity))
    db.flush()
    return reg


def _booking(db, reg, amount: str, *, paid: bool, method="transfer", ogm=OGM):
    record = PaymentRecord(
        payable_type="registration",
        payable_id=reg.id,
        amount=Decimal(amount),
        amount_paid=Decimal(amount) if paid else Decimal("0"),
        method=method,
        status="paid" if paid else "pending",
        structured_communication=ogm,
    )
    db.add(record)
    db.flush()
    return record


@pytest.fixture
def world(client, db_session):
    household, me = create_test_family(db_session, email=EMAIL)
    me.first_name, me.last_name = "Emma", "Voorbeeld"
    partner = create_test_person(db_session, first_name="Bram", last_name="Voorbeeld")
    db_session.add(
        MemberPerson(member_id=household.id, person_id=partner.id, relation_type="PARTNER")
    )
    activity, component, product = seed_activity_with_product(db_session, price="10.00")
    activity.name = "Meting zomerfeest"
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(EMAIL))
    return {
        "me": me,
        "partner": partner,
        "activity": activity,
        "component": component,
        "product": product,
    }


def _reg(db, world, **kwargs):
    return _registration(db, world["activity"], world["component"], world["product"], **kwargs)


def test_without_a_session_the_page_asks_to_sign_in(client):
    response = client.get("/mijn/inschrijvingen", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/aanmelden?terug=/mijn/inschrijvingen"


def test_nobody_registered_yet_says_so(client, world):
    html = client.get("/mijn/inschrijvingen").text
    main = _main(html)
    assert "Je hebt nog geen inschrijvingen." in main and _cards(html) == []
    assert re.search(r"<h1[^>]*>\s*Mijn inschrijvingen\s*</h1>", main)


def test_a_member_sees_the_households_registrations_newest_first(client, db_session, world):
    """T10, and Q37: who of the household registered."""
    mine = _reg(db_session, world, person=world["me"], quantity=2, days_ago=3)
    _booking(db_session, mine, "20.00", paid=True)
    partners = _reg(db_session, world, person=world["partner"], quantity=1, days_ago=1)
    _booking(db_session, partners, "10.00", paid=False)
    # A guest's registration on the same address: no person, in nobody's list (R23).
    guest = _reg(db_session, world, person=None, quantity=5, days_ago=0)
    _booking(db_session, guest, "50.00", paid=False, ogm="+++170/9000/00999+++")
    db_session.commit()

    cards = _cards(client.get("/mijn/inschrijvingen").text)
    assert len(cards) == 2, (
        f"{len(cards)} cards — the guest's registration is listed, or one is missing"
    )
    newest, older = cards
    assert "ingeschreven door Bram" in newest and "1 × Testproduct" in newest
    assert "€ 10,00" in newest and 'data-payment-state="open"' in newest and "Te betalen" in newest
    assert "ingeschreven door Emma" in older and "2 × Testproduct" in older
    assert "€ 20,00" in older and 'data-payment-state="settled"' in older and "Betaald" in older
    assert all("Meting zomerfeest" in card for card in cards)
    assert "5 × Testproduct" not in "".join(cards) and "00999" not in "".join(cards)


def test_a_person_without_a_household_sees_his_own_only(db_session, world):
    """T10 for an account — a person without a household, who can sign in from
    S4a on: the list is his own, and names nobody as "ingeschreven door"."""
    account = Person(first_name="Noor", last_name="Voorbeeld")
    db_session.add(account)
    db_session.flush()
    own = _reg(db_session, world, person=account, quantity=3, email="noor-1709@example.org")
    _reg(db_session, world, person=world["me"], quantity=1)
    db_session.commit()
    rows = my_registrations(db_session, account)
    assert [row.id for row in rows] == [own.id]
    assert rows[0].registered_by is None and rows[0].lines == ("3 × Testproduct",)
    assert rows[0].has_payment is False and rows[0].transfer is None
    # And the household does not see his.
    assert own.id not in [row.id for row in my_registrations(db_session, world["me"])]


def test_a_transfer_still_to_make_shows_the_same_block_as_a_renewal(client, db_session, world):
    """T19: `data-transfer-due`, from the one partial, with THIS registration's
    amount and reference; a paid registration shows none."""
    due = _reg(db_session, world, person=world["me"], quantity=2, days_ago=1)
    _booking(db_session, due, "20.00", paid=False)
    paid = _reg(db_session, world, person=world["me"], quantity=1, days_ago=5)
    _booking(db_session, paid, "10.00", paid=True, ogm="+++170/9000/00456+++")
    db_session.commit()

    open_card, paid_card = _cards(client.get("/mijn/inschrijvingen").text)
    assert open_card.count("data-transfer-due") == 1
    assert "Inschrijving geregistreerd — betaal via overschrijving:" in open_card
    block = open_card[open_card.index("data-transfer-due") :]
    assert "€ 20,00" in block and OGM in block and "Mededeling (OGM)" in block
    assert "data-transfer-due" not in paid_card and "00456" not in paid_card


def test_an_online_payment_that_is_open_shows_no_transfer(client, db_session, world):
    reg = _reg(db_session, world, person=world["me"])
    _booking(db_session, reg, "20.00", paid=False, method="online")
    db_session.commit()
    (card,) = _cards(client.get("/mijn/inschrijvingen").text)
    assert 'data-payment-state="open"' in card and "data-transfer-due" not in card


def test_the_landing_page_shows_the_latest_registration_or_no_card(client, db_session, world):
    """T18: no registration → no "Je laatste inschrijving"; with some, the newest
    one, as the same card — its transfer included."""
    assert "data-latest-registration" not in _main(client.get("/mijn").text)
    old = _reg(db_session, world, person=world["me"], quantity=1, days_ago=9)
    _booking(db_session, old, "10.00", paid=True)
    new = _reg(db_session, world, person=world["partner"], quantity=4, days_ago=0)
    _booking(db_session, new, "40.00", paid=False)
    db_session.commit()
    main = _main(client.get("/mijn").text)
    latest = main[main.index("data-latest-registration") :]
    assert "Je laatste inschrijving" in latest and 'href="/mijn/inschrijvingen"' in latest
    assert latest.count("data-my-registration") == 1
    assert "4 × Testproduct" in latest and "1 × Testproduct" not in latest
    assert latest.count("data-transfer-due") == 1 and "€ 40,00" in latest


# ── the hint above the registration form (T12, Q39) ──────────────────────────


def _form_path(world) -> str:
    return f"/activiteiten/{world['activity'].id}/inschrijven/{world['component'].id}"


def test_the_hint_has_the_words_of_cr22_and_gives_no_reason(client, world):
    client.cookies.clear()
    html = client.get(_form_path(world)).text
    hint = html[html.index("data-member-nudge") :]
    hint = hint[: hint.index("</p>")]
    text = " ".join(re.sub(r"<[^>]+>", " ", hint.split(">", 1)[1]).split())
    assert text == "Heb je een account of ben je lid? Log je eerst aan .", text
    assert "RAAK" not in hint and "dan staat" not in hint


def test_where_the_tenant_has_no_members_the_hint_names_only_the_account(
    client, world, monkeypatch
):
    client.cookies.clear()
    invalidate_tenant_codes()
    without = frozenset(code.value for code in ModuleCode) - {ModuleCode.MEMBERSHIP.value}
    monkeypatch.setattr(tenant_lookup, "_modules_cache", {TENANT_MILLEGEM_ID: without})
    try:
        html = client.get(_form_path(world)).text
    finally:
        invalidate_tenant_codes()
    hint = html[html.index("data-member-nudge") :]
    hint = hint[: hint.index("</p>")]
    assert "Heb je een account?" in hint and "ben je lid" not in hint


# ── the board's form says to whom the registration will be linked ────────────


def _prices(client, world, email: str):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    token = csrf_token_for(client.cookies.get(SESSION_COOKIE))
    return client.post(
        f"/admin/activiteiten/{world['activity'].id}/inschrijvingen/nieuw/prijzen",
        data={"onderdeel": str(world["component"].id), "contact_email": email},
        headers={"X-CSRF-Token": token},
    )


def test_the_boards_form_names_the_person_before_saving(client, db_session, world):
    """Koen, 7 October 2026: typed address of a person → the form says to whom
    the registration will be linked, by name; an address of nobody → nothing."""
    component = world["component"].id
    known = _prices(client, world, EMAIL)
    assert known.status_code == 200, known.text[:300]
    link = re.search(rf'<div id="koppeling-{component}"[^>]*>(.*?)</div>', known.text, re.S)
    assert link and 'hx-swap-oob="true"' in link.group(0)
    assert "Deze inschrijving wordt gekoppeld aan Emma Voorbeeld." in link.group(1)
    unknown = _prices(client, world, "niemand-1709@example.org")
    link = re.search(rf'<div id="koppeling-{component}"[^>]*>(.*?)</div>', unknown.text, re.S)
    assert link and 'hx-swap-oob="true"' in link.group(0)
    assert link.group(1).strip() == "", "the form names somebody for an address of nobody"
    # The page itself carries the element, so the answer has somewhere to land.
    page = client.get(
        f"/admin/activiteiten/{world['activity'].id}/inschrijvingen/nieuw?onderdeel={component}"
    )
    assert page.status_code == 200 and f'id="koppeling-{component}"' in page.text
    # The public form never does: it looks nothing up.
    client.cookies.clear()
    assert "koppeling-" not in client.get(_form_path(world)).text
