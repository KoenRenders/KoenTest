"""The add button under the last item, one empty e-mail field per person, and the
Lidmaatschap card as the one place for a running renewal (#1641; CR-11 Q76, Q77,
Q79; end state §3.3 and §2.6).

Koen, 5 October 2026, at the HDEV validation of #1632 and #1610. Counted in what
the server answers; the geometry is measured in the browser
(`tests_e2e/test_household_pages.py`, `test_repeating_groups.py`).

Broken on purpose (5 October 2026), each red for its own reason: the kit's
`_add_below` made false → the button back in the head; the blank row not added
to a person without an address → no field to type in; the reader keeping an
empty new row → `emails` holds a row that says nothing; `email_field` not read
by the sign-up → the refusal lands on the person, not on the field; the 303
taken off the renewal page → it answers 200 while a renewal runs; the link put
back on the card; the inset replaced by loose lines.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest
from starlette.datastructures import FormData

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import ContactDetail, MemberPerson
from app.domains.mdm.household_form import household_from_form
from app.domains.membership.api import Membership
from app.domains.payment.api import GatewayPayment, PaymentRecord
from tests.conftest import create_test_family, create_test_person, form_fields

pytestmark = pytest.mark.ui_serverrendered

EDIT, SIGN_UP, RENEW = "/leden/gezin?bewerken=1", "/lid-worden", "/leden/gezin/vernieuwen"
OGM = "+++123/4567/89012+++"
_TEMPLATE = re.compile(r"<template\b(?:(?!<template\b).)*?</template>", re.S)


def _household(db, email: str):
    """A main member with an address to sign in with, and a partner without one."""
    member, main = create_test_family(db, email=email, mobile="0470000000")
    partner = create_test_person(db)
    db.add(MemberPerson(member_id=member.id, person_id=partner.id, relation_type="PARTNER"))
    db.commit()
    return member, main, partner


def _login(client, email: str) -> dict:
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _on_the_page(html: str) -> str:
    """The page's content without what a `<template>` holds (innermost first)."""
    html = html[html.index("<main") : html.index("</main>")]
    while _TEMPLATE.search(html):
        html = _TEMPLATE.sub("", html)
    return html


def _group(html: str, name: str) -> str:
    """The markup of the repeating group `name`, up to the next section."""
    start = html.index(f'data-repeating-group="{name}"')
    end = html.find("</section>", start)
    return html[start : end if end > 0 else len(html)]


# ── 1. Where the add button stands ───────────────────────────────────────────


def test_the_persons_group_adds_under_its_rows_and_the_email_group_in_its_head(client, db_session):
    """Red on master: "+ Gezinslid toevoegen" stood in the head, above the rows."""
    _household(db_session, "knop@example.com")
    _login(client, "knop@example.com")
    html = _on_the_page(client.get(EDIT).text)

    persons = _group(html, "h_order")
    rows, below = persons.index("data-group-rows"), persons.index("data-group-add-below")
    assert rows < persons.index("data-group-empty") < below, "the button is not under the rows"
    assert "Gezinslid toevoegen" in persons[below:], "the button is not in that place"
    assert "data-group-add" not in persons[:rows], "a button is left in the head"
    # the child group of a person keeps its button in the head
    mails = html[html.index('data-repeating-group="e_order.') :]
    assert mails.index("data-group-add") < mails.index("data-group-rows")
    assert "data-group-add-below" not in mails[: mails.index("data-group-rows")]


def test_an_empty_persons_group_shows_the_button_where_the_first_will_come(client, db_session):
    html = _on_the_page(client.get(SIGN_UP).text)
    persons = _group(html, "h_order")
    assert persons.index("Nog geen gezinsleden.") < persons.index("data-group-add-below")
    assert persons.count("data-group-add ") == 1


def test_the_kit_decides_by_the_form_of_the_group():
    """A property of the composite form, not of a screen: no parameter asks it."""
    from app.ui import templates

    render = templates.env.from_string(
        '{% import "_macros.html" as ui %}'
        '{% call ui.repeating_group("T", "g", add_label="Toevoegen", edit=True,'
        " variant=variant, child=child) %}{% endcall %}"
    ).render

    def head_and_below(variant: str, child: bool) -> tuple[bool, bool]:
        html = render(variant=variant, child=child)
        head = html[: html.index("data-group-rows")]
        return "data-group-add" in head, "data-group-add-below" in html

    assert head_and_below("composite", False) == (False, True)
    assert head_and_below("composite", True) == (True, False), "a child group moved its button"
    assert head_and_below("simple", False) == (True, False), "a simple group moved its button"
    assert head_and_below("simple", True) == (True, False)


# ── 2. One empty e-mail field per person ─────────────────────────────────────


def test_every_person_opens_with_one_email_field_in_edit_mode(client, db_session):
    """Red on master: the partner's group read "Nog geen e-mailadres." with a button."""
    _member, main, partner = _household(db_session, "veld@example.com")
    _login(client, "veld@example.com")
    html = _on_the_page(client.get(EDIT).text)

    fields = re.findall(r'<input[^>]*name="(e\.[^"]+\.value)"[^>]*>', html)
    assert len(fields) == 2, fields
    blank = re.search(rf'<input[^>]*name="e\.n{partner.id}e\.value"[^>]*>', html)
    assert blank, "the partner has no field to type an address in"
    assert not re.search(r'value="[^"]+"', blank.group(0)), "the field is not empty"
    assert " required" not in blank.group(0), "an address is asked of the partner"
    sent = form_fields(client.get(EDIT).text, "gezin-form")
    assert sent[f"e_order.{partner.id}"] == [f"n{partner.id}e"]
    # reading, a person without an address shows none
    read = _on_the_page(client.get("/leden/gezin").text)
    assert f"e.n{partner.id}e.value" not in read and "Nog geen e-mailadres." in read


def test_a_person_added_in_the_page_comes_with_an_email_field_of_their_own(client, db_session):
    """The template row: its e-mail key hangs on the person's token, so two
    added persons do not share a field."""
    html = client.get(SIGN_UP).text
    row = html[re.search(r'<div data-group-row data-row-key="__H__"', html).start() :]
    assert 'name="e.__H__e.value"' in row
    assert 'name="e_order.__H__" value="__H__e"' in row
    main = _on_the_page(html)
    assert re.search(r'<input[^>]*name="e\.n0e\.value"[^>]*required', main), (
        "the main member's address is not asked"
    )


def test_the_reader_leaves_an_empty_new_row_out_and_keeps_an_emptied_stored_one():
    """The one rule, in the reader, for both pages."""
    form = FormData(
        [
            ("h_order", "7"),
            ("e_order.7", "n7e"),
            ("e.n7e.value", "  "),
            ("h_order", "8"),
            ("e_order.8", "41"),
            ("e.41.value", ""),
            ("e_order.8", "n8a"),
            ("e.n8a.value", "nieuw@example.com"),
            ("h_order", "9"),
        ]
    )
    first, second, third = household_from_form(form).persons
    assert first.emails == [] and first.email_field == "e.n7e.value"
    assert [(m.key, m.value) for m in second.emails] == [("41", ""), ("n8a", "nieuw@example.com")]
    assert second.email_field == "e.41.value"
    assert third.emails == [] and third.email_field == ""


def test_saving_with_the_partners_field_empty_writes_no_address_and_no_history(client, db_session):
    from app.domains.mdm.models import ContactDetailHistory

    _member, main, partner = _household(db_session, "leeg@example.com")
    headers = _login(client, "leeg@example.com")
    before = db_session.query(ContactDetailHistory).count()

    fields = form_fields(client.get(EDIT).text, "gezin-form")
    assert fields[f"e.n{partner.id}e.value"] == ""
    answer = client.post("/leden/gezin", data=fields, headers=headers)

    assert answer.status_code == 200, answer.text[:300]
    assert "data-save-refusal" not in answer.text
    db_session.expire_all()
    rows = db_session.query(ContactDetail).filter_by(person_id=partner.id).all()
    assert rows == [], "an empty field became a row"
    assert db_session.query(ContactDetailHistory).count() == before, "an empty field left history"

    # the other half: typed, the same field becomes the partner's address —
    # waiting for its code since CR-22 R15 (#1711), so not the main one yet
    fields = form_fields(client.get(EDIT).text, "gezin-form")
    fields[f"e.n{partner.id}e.value"] = "partner.leeg@example.com"
    assert client.post("/leden/gezin", data=fields, headers=headers).status_code == 200
    db_session.expire_all()
    stored = db_session.query(ContactDetail).filter_by(person_id=partner.id).one()
    assert (stored.value, stored.is_primary, stored.confirmed_at) == (
        "partner.leeg@example.com",
        False,
        None,
    )


def test_the_main_members_empty_field_is_refused_on_the_field(client, db_session):
    from tests.conftest import seed_postal_code

    seed_postal_code(db_session, code="2400", municipality="Mol")
    db_session.commit()
    fields = form_fields(client.get(SIGN_UP).text, "lid-worden-form")
    fields.update(
        {
            "h.n0.first_name": "Zonder",
            "h.n0.last_name": "Adres",
            "h.n0.date_of_birth": "1980-01-01",
            "h.n0.gender_code": "F",
            "h.n0.mobile": "0470000000",
            "address.street": "Dorpsstraat",
            "address.house_number": "1",
            "address.postal_code": "2400",
            "payment_method": "transfer",
        }
    )
    assert fields["e.n0e.value"] == ""
    answer = client.post(SIGN_UP, data=fields, headers={"HX-Request": "true"})
    assert answer.status_code == 422
    assert 'data-error-for="e.n0e.value"' in answer.text
    assert "E-mailadres is verplicht voor het hoofdgezinslid." in answer.text


# ── 3 and 4. The card is the one place, and its instructions an inset ────────


def _running(db, member, *, method="transfer", gateway_payment_id=None) -> None:
    # A renewal presupposes a membership that was paid before (#1730): without
    # one this household would be paying its FIRST membership, with other words.
    db.add(
        Membership(
            member_id=member.id,
            year=date.today().year - 1,
            is_active=True,
            valid_from=date(date.today().year - 1, 1, 1),
            valid_to=date(date.today().year - 1, 12, 31),
        )
    )
    year = date.today().year + 1
    membership = Membership(
        member_id=member.id,
        year=year,
        is_active=False,
        valid_from=date(year, 1, 1),
        valid_to=date(year, 12, 31),
    )
    db.add(membership)
    db.flush()
    db.add(
        PaymentRecord(
            payable_type="membership",
            payable_id=membership.id,
            amount=Decimal("35.00"),
            method=method,
            status="pending",
            structured_communication=OGM,
            gateway_payment_id=gateway_payment_id,
        )
    )
    db.commit()


def _card(html: str) -> str:
    start = html.index("data-membership-status")
    return html[start : html.index("</section>", start)]


def test_the_card_shows_the_transfer_as_an_inset_and_links_nowhere(client, db_session):
    """Red on master: loose lines, and the link "Bekijk de betaling" beside them."""
    member, _main, _partner = _household(db_session, "kaart@example.com")
    _running(db_session, member)
    _login(client, "kaart@example.com")

    card = _card(client.get("/leden/gezin").text)

    assert "Bekijk de betaling" not in card and "/leden/gezin/vernieuwen" not in card
    inset = re.search(r"<div data-inset data-transfer-due[^>]*>(.*?)</div>", card, re.S)
    assert inset, "the instructions are not the kit's inset"
    assert "rounded-md" in inset.group(0) and "bg-blue-50" in inset.group(0)
    assert " p-4 " in inset.group(0), "16 px of padding"
    body = inset.group(1)
    assert "Vernieuwing geregistreerd — betaal via overschrijving:" in body
    places = [body.index(word) for word in ("Bedrag", "Mededeling (OGM)")]
    assert places == sorted(places) and OGM in body and "35,00" in body


def test_the_renewal_page_lands_on_mijn_gezin_while_a_renewal_runs(client, db_session):
    member, _main, _partner = _household(db_session, "landt@example.com")
    _login(client, "landt@example.com")
    free = client.get(RENEW, follow_redirects=False)
    assert free.status_code == 200 and 'id="vernieuw-form"' in free.text, (
        "without a running renewal the page still starts one"
    )

    _running(db_session, member)
    answer = client.get(RENEW, follow_redirects=False)
    assert answer.status_code == 303 and answer.headers["location"] == "/leden/gezin"


def test_an_online_payment_broken_off_is_resumed_from_the_card(client, db_session):
    """ "Betaling hervatten" stood on the renewal page's running view; that view
    is gone, so the button stands in the card."""
    member, _main, _partner = _household(db_session, "hervat@example.com")
    gateway = GatewayPayment(
        amount=Decimal("35.00"),
        currency="EUR",
        status="open",
        provider="mollie",
        checkout_url="https://betaal.example/hervat",
    )
    db_session.add(gateway)
    db_session.flush()
    _running(db_session, member, method="online", gateway_payment_id=gateway.id)
    _login(client, "hervat@example.com")

    card = _card(client.get("/leden/gezin").text)
    assert "data-renewal-online" in card and "Betaling hervatten" in card
    assert 'href="https://betaal.example/hervat"' in card
    assert "data-transfer-due" not in card


def test_a_renewal_by_transfer_answers_with_a_hard_redirect_to_the_card(client, db_session):
    _household(db_session, "start@example.com")
    headers = _login(client, "start@example.com")
    answer = client.post(RENEW, data={"payment_method": "transfer"}, headers=headers)
    assert answer.status_code == 200 and answer.headers["HX-Redirect"] == "/leden/gezin"
    card = _card(client.get("/leden/gezin").text)
    assert "data-transfer-due" in card and "+++" in card
