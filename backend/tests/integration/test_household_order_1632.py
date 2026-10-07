"""The correction on Word lid and Mijn gezin (#1632; CR-11 Q70–Q73, end state §2.6).

Koen, 5 October 2026, after P3 (#1590) on HDEV. Four things, counted in the
page the server answers:

1. **an e-mail row carries no label**: the group's title "E-mailadressen" is
   the label, in read and edit mode. Red on master: the word stood as a label
   on every row (and in the group's column head). The field keeps its
   accessible name;
2. **Geslacht is a select beside Geboortedatum**, no radio group;
3. **the order**: Hoofdlid (a fixed section, no row of the group, nothing to
   remove) → Adres → Gezinsleden → the price. The form still sends the main
   member as the first person, so the one save is untouched;
4. **the Lidmaatschap card**: valid in the kit's success tone without an
   emoji; a renewal that waits for a transfer shows what to pay in the card —
   the same block as the renewal page, from one template.

Broken on purpose (5 October 2026), each red for its own reason:
`label_hidden` taken off the e-mail field → the label count; the select made a
radio group again; the head included after the address → the order; the main
member put back among the rows → "the main member is a row"; `ui.fixed_row`
left out → the form sends no main member; the transfer not handed to the page
→ no instructions in the card; the badge replaced by "✅".
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mdm.api import ContactDetail, MemberPerson
from app.domains.membership.api import Membership
from app.domains.payment.api import PaymentRecord
from tests.conftest import create_test_family, create_test_person, form_fields

pytestmark = pytest.mark.ui_serverrendered

READ, EDIT, SIGN_UP = "/leden/gezin", "/leden/gezin?bewerken=1", "/lid-worden"
#: The word as a label of its own: in a label, a read-mode line or a column head.
LABEL = re.compile(
    r">\s*E-mail(?:adres)?\s*(?:<span class=\"text-red-600\">\*</span>)?\s*</(?:label|p|span)>"
)
OGM = "+++123/4567/89012+++"


def _household(db, email: str):
    """A main member with two e-mail addresses and a partner with one."""
    member, main = create_test_family(db, email=email, mobile="0470000000")
    db.add(
        ContactDetail(
            person_id=main.id,
            contact_type_code="EMAIL",
            value="tweede." + email,
            is_primary=False,
        )
    )
    partner = create_test_person(db)
    db.add(MemberPerson(member_id=member.id, person_id=partner.id, relation_type="PARTNER"))
    db.add(
        ContactDetail(
            person_id=partner.id,
            contact_type_code="EMAIL",
            value="partner." + email,
            is_primary=True,
        )
    )
    db.commit()
    return member, main, partner


def _page(client, email: str, path: str) -> str:
    client.cookies.set(SESSION_COOKIE, make_session_value(email))
    answer = client.get(path)
    assert answer.status_code == 200
    return answer.text


_TEMPLATE = re.compile(r"<template\b(?:(?!<template\b).)*?</template>", re.S)


def _main(html: str) -> str:
    """The page's own content: without the shell around it, and without what a
    `<template>` holds — a row nobody added is not on the page (innermost
    first: a person's template carries an e-mail group with its own)."""
    html = html[html.index("<main") : html.index("</main>")]
    while _TEMPLATE.search(html):
        html = _TEMPLATE.sub("", html)
    return html


# ── 1. No label on an e-mail row ─────────────────────────────────────────────


@pytest.mark.parametrize("path", [READ, EDIT])
def test_an_email_row_carries_no_label_of_its_own(client, db_session, path):
    _household(db_session, "rijen@example.com")
    html = _main(_page(client, "rijen@example.com", path))

    assert html.count("rijen@example.com") >= 2, "the addresses are not on the page"
    assert html.count(">E-mailadressen</h3>") == 2, "the group's title is the label"
    assert LABEL.findall(html) == [] and not LABEL.search(html), "a row says E-mail itself"


def test_the_email_field_keeps_its_accessible_name(client, db_session):
    _household(db_session, "naam@example.com")
    html = _main(_page(client, "naam@example.com", EDIT))
    fields = re.findall(r'<input[^>]*name="e\.[^"]+\.value"[^>]*>', html)
    assert len(fields) == 3, "the three addresses of the household"
    assert all('aria-label="E-mail"' in field for field in fields)
    assert not re.search(r'<label[^>]*for="e-[^"]+-value"', html), "a label element is back"


def test_word_lid_has_no_label_on_its_email_row_either(client, db_session):
    html = _main(client.get(SIGN_UP).text)
    assert 'name="e.n0e.value"' in html and 'aria-label="E-mail"' in html
    assert not LABEL.search(html)


# ── 2. Geslacht ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", [EDIT, SIGN_UP])
def test_geslacht_is_a_select_of_half_width_after_the_date_of_birth(client, db_session, path):
    _household(db_session, "geslacht@example.com")
    html = _main(_page(client, "geslacht@example.com", path))

    blocks = re.findall(r'<div data-field="h\.[^"]+\.gender_code"[^>]*>', html)
    assert blocks, "no gender field"
    assert all('data-kind="select"' in b and 'data-span="half"' in b for b in blocks)
    assert not re.search(r'type="radio"[^>]*name="h\.[^"]+\.gender_code"', html)
    assert re.search(r'<select[^>]*name="h\.[^"]+\.gender_code"[^>]*required', html)
    # beside it: the two fields follow each other on the grid
    order = re.findall(r'data-field="h\.[^".]+\.(\w+)"', html)
    assert order[order.index("date_of_birth") + 1] == "gender_code"


def test_in_read_mode_the_gender_is_one_word(client, db_session):
    _member, main, _partner = _household(db_session, "woord@example.com")
    html = _main(_page(client, "woord@example.com", READ))
    block = html[html.index(f'data-field="h.{main.id}.gender_code"') :][:500]
    assert "<select" not in block and "data-value" in block


# ── 3. The order, and the main member outside the group ──────────────────────


@pytest.mark.parametrize("path", [READ, EDIT])
def test_mijn_gezin_reads_hoofdlid_then_adres_then_gezinsleden(client, db_session, path):
    _household(db_session, "volgorde@example.com")
    html = _main(_page(client, "volgorde@example.com", path))
    places = [html.index(f'id="{mark}"') for mark in ("hoofdlid", "gezin-adres", "gezinsleden")]
    assert places == sorted(places), places
    titles = re.findall(r"<h2[^>]*>([^<]+)</h2>", html)
    assert [t for t in titles if t in ("Hoofdlid", "Adres", "Gezinsleden")] == [
        "Hoofdlid",
        "Adres",
        "Gezinsleden",
    ]


def test_word_lid_ends_with_the_price_and_starts_with_an_empty_group(client, db_session):
    html = _main(client.get(SIGN_UP).text)
    places = [
        html.index(f'id="{mark}"') for mark in ("hoofdlid", "gezin-adres", "gezinsleden", "lidgeld")
    ]
    assert places == sorted(places), places
    group = html[html.index('id="gezinsleden"') : html.index('id="lidgeld"')]
    assert "Nog geen gezinsleden." in group and "Gezinslid toevoegen" in group
    assert not re.search(r"data-group-row\b(?!s)", group), "a row before anyone is added"


def test_the_main_member_is_no_row_and_the_form_still_sends_them_first(client, db_session):
    _member, main, partner = _household(db_session, "vast@example.com")
    html = _main(_page(client, "vast@example.com", EDIT))

    head = html[html.index('id="hoofdlid"') : html.index('id="gezin-adres"')]
    assert f'name="h.{main.id}.first_name"' in head
    assert "data-row-fold" not in head, "the main member folds"
    assert 'data-row-action="remove"' not in head.split("E-mailadressen")[0], (
        "the main member can be removed"
    )
    rows = re.findall(
        r'data-group-row data-row-key="(\d+)"', html[html.index('id="gezinsleden"') :]
    )
    assert str(partner.id) in rows and str(main.id) not in rows, "the main member is a row"
    # what the browser would send: one list of persons, the main member first
    sent = form_fields(_page(client, "vast@example.com", EDIT), "gezin-form")
    assert sent["h_order"] == [str(main.id), str(partner.id)]


# ── 4. The Lidmaatschap card ─────────────────────────────────────────────────


def _membership(db, member, *, year: int, active: bool) -> Membership:
    membership = Membership(
        member_id=member.id,
        year=year,
        is_active=active,
        valid_from=date(year, 1, 1),
        valid_to=date(year, 12, 31),
    )
    db.add(membership)
    db.flush()
    return membership


def _card(html: str) -> str:
    start = html.index("data-membership-status")
    return html[start : html.index("</section>", start)]


def test_a_valid_membership_shows_in_the_success_tone_without_an_emoji(client, db_session):
    member, _main_person, _partner = _household(db_session, "geldig@example.com")
    before = _card(_page(client, "geldig@example.com", READ))
    assert "data-membership-valid" not in before and "geen geldig lidmaatschap" in before

    _membership(db_session, member, year=date.today().year, active=True)
    db_session.commit()
    card = _card(_page(client, "geldig@example.com", READ))
    assert "geldig tot en met" in card
    assert "data-membership-valid" in card and "bg-green-100" in card and ">Geldig</span>" in card
    assert "✅" not in card and "✓" not in card, "the tone is the kit's, with its icon"
    assert "<svg" in card.split("Geldig</span>")[0], "the badge carries the kit's check"


def test_a_renewal_that_waits_for_a_transfer_shows_what_to_pay_in_the_card(client, db_session):
    member, _main_person, _partner = _household(db_session, "storting@example.com")
    assert "data-transfer-due" not in _card(_page(client, "storting@example.com", READ))

    renewal = _membership(db_session, member, year=date.today().year + 1, active=False)
    db_session.add(
        PaymentRecord(
            payable_type="membership",
            payable_id=renewal.id,
            amount=Decimal("35.00"),
            method="transfer",
            status="pending",
            structured_communication=OGM,
        )
    )
    db_session.commit()

    card = _card(_page(client, "storting@example.com", READ))
    assert "Je vernieuwing loopt nog." in card
    assert card.count("data-transfer-due") == 1
    assert OGM in card and "35,00" in card and "betaal via overschrijving:" in card


def test_only_the_card_writes_what_a_running_renewal_asks():
    """One source (#1641: the renewal page lost its running view; CR-22 S2,
    #1705: moved, never copied). In EVERY template of the application:

    - the lines of a transfer are written by `_transfer_due.html` alone, the
      shared partial, and the membership card reaches it through
      `_renewal_running.html`;
    - the membership card is written by `_membership_card.html` alone, which the
      household page includes.

    Red by putting a second `data-transfer-due` inset into the household page
    (the first list names two files), and by writing the card's hook into it."""
    from pathlib import Path

    app = Path(__file__).resolve().parents[2] / "app"
    sources = {p.name: p.read_text() for p in app.rglob("templates/*.html")}
    assert len(sources) > 150, f"only {len(sources)} templates found — the glob looks nowhere"

    def holding(needle: str) -> list[str]:
        return sorted(name for name, text in sources.items() if needle in text)

    # The kit page draws an inset with made-up lines to SHOW the kit's inset; it
    # is no place that says what somebody owes.
    assert holding("Mededeling (OGM)") == ["_transfer_due.html", "design_system.html"]
    assert holding('attrs="data-transfer-due"') == ["_transfer_due.html"]
    # Since CR-22 S5 (#1709) a registration still to be paid shows the same block.
    assert holding('"_transfer_due.html"') == ["_my_registration.html", "_renewal_running.html"]
    assert holding('"_renewal_running.html"') == ["_membership_card.html"]
    assert holding('attrs="data-membership-status"') == ["_membership_card.html"]
    # Since CR-22 S3 (#1706) the landing page shows the same card.
    assert holding('"_membership_card.html"') == ["account_home.html", "household_page.html"]
