"""CR-14 phase 2 (#1333): reading the answers — the export, the book and the
registration detail (§B4.4, §B1.1 F8, F14; B7 tests 7 and 13).

- **Export**: one column per question after *Opmerkingen*, headed by its label, in
  the form's order; a checkbox's ticks joined with ", "; the answers of all
  registrations fetched in ONE statement — counted, not timed.
- **Book**: one block per registration by contact name, a page break between
  blocks, "Nog niet beantwoord" while the link is open, the address for a member
  and the note for a guest — and the same answers as the export (one read).
- **Detail**: the answers as label and value, or "Antwoorden gevraagd op" while
  the link is open.

Broken on purpose to check these tests can go red (run, then restored), with what
failed: `+ questions` removed from the export's headers → the export test;
`submission_views` called once per registration in `component_answers` → the
one-statement test (2 statements: one per answered registration); `sorted(…)` in `component_book` replaced by the
registrations in their own order → the book-order test.
"""

from __future__ import annotations

import re
from io import BytesIO
from types import SimpleNamespace

import pytest
from odf.opendocument import load
from odf.table import Table, TableCell, TableRow
from odf.teletype import extractText
from sqlalchemy import event

from app.domains.activities import service
from app.domains.activities.api import Registration
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    create_test_family,
    register_at_the_door,
    seed_activity_with_product,
    seed_postal_code,
    seed_question_form,
)

pytestmark = pytest.mark.ui_serverrendered


def _field(form, label):
    return next(f for f in form.fields if f.label == label)


def _register(client, s, name: str, answers):
    body = {
        "contact_name": name,
        "contact_email": f"{name.split()[0].lower()}@example.com",
        "phone": "0470000000",
        "component_id": s.component.id,
        "items": [{"product_id": s.product.id, "quantity": 1}],
    }
    if answers is not None:
        body["answers"] = answers
    r = register_at_the_door(client, s.activity.id, json=body)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture
def sint(client, db_session):
    """Three registrations: Zoë (both slots), Anna (a member, with an address),
    Bert (still to answer)."""
    from app.domains.mdm.api import Address

    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)
    form = seed_question_form(db_session)
    service.update_component(db_session, activity.id, component.id, {"form_id": form.id})
    s = SimpleNamespace(activity=activity, component=component, product=product, form=form)
    slot, story = _field(form, "Tijdslot"), _field(form, "Verhaal")
    both = [o.id for o in slot.options if not o.is_other]
    _register(
        client,
        s,
        "Zoë Laatst",
        [{"field_id": slot.id, "option_ids": both}, {"field_id": story.id, "text": "Zingt"}],
    )
    anna = _register(
        client,
        s,
        "Anna Eerst",
        [{"field_id": slot.id, "option_ids": both[:1]}, {"field_id": story.id, "text": "Leest"}],
    )
    _register(client, s, "Bert Midden", None)

    postcode = seed_postal_code(db_session)
    _member, person = create_test_family(db_session, email="anna.eerst@example.com")
    db_session.add(
        Address(
            person_id=person.id, street="Kerkstraat", house_number="7", postal_code_id=postcode.id
        )
    )
    db_session.get(Registration, anna).person_id = person.id
    db_session.commit()
    db_session.expire_all()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    return s


def _sheet(content: bytes) -> list[list]:
    table = load(BytesIO(content)).getElementsByType(Table)[0]
    rows = []
    for tr in table.getElementsByType(TableRow):
        cells = []
        for tc in tr.getElementsByType(TableCell):
            cells.extend([extractText(tc)] * int(tc.getAttribute("numbercolumnsrepeated") or 1))
        rows.append(cells)
    return rows


def test_the_export_has_a_column_per_question_after_the_remarks(client, sint):
    r = client.get(f"/admin/activiteiten/{sint.activity.id}/onderdelen/{sint.component.id}/export")
    rows = _sheet(r.content)
    header = rows[0]
    at = header.index("Opmerkingen")
    assert header[at + 1 : at + 4] == ["Tijdslot", "Verhaal", "Opmerkingen"]
    by_name = {row[0]: row for row in rows[1:]}
    assert by_name["Zoë Laatst"][at + 1 : at + 3] == ["Voormiddag, Namiddag", "Zingt"]
    assert by_name["Bert Midden"][at + 1 : at + 3] == ["", ""]


def test_the_answers_are_read_in_one_statement(client, db_session, sint):
    statements = []

    def _count(conn, cursor, statement, *args):
        if "form_submission_answers" in statement:
            statements.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", _count)
    try:
        client.get(f"/admin/activiteiten/{sint.activity.id}/onderdelen/{sint.component.id}/export")
    finally:
        event.remove(db_session.bind, "before_cursor_execute", _count)
    assert len(statements) == 1, len(statements)


def test_the_book_has_a_page_per_registration_by_name(client, sint):
    html = client.get(
        f"/admin/activiteiten/{sint.activity.id}/onderdelen/{sint.component.id}/antwoorden"
    ).text
    names = re.findall(r"<h2>([^<]+)</h2>", html)
    assert names == ["Anna Eerst", "Bert Midden", "Zoë Laatst"]
    assert html.count('<section class="blok">') == 3
    assert "page-break-after: always" in html

    blocks = dict(zip(names, html.split('<section class="blok">')[1:]))
    assert "Kerkstraat 7, " in blocks["Anna Eerst"]
    assert "Geen adres gekend" in blocks["Zoë Laatst"]
    assert "Nog niet beantwoord" in blocks["Bert Midden"]
    assert "Voormiddag, Namiddag" in blocks["Zoë Laatst"] and "Zingt" in blocks["Zoë Laatst"]


def test_the_detail_shows_the_answers_or_when_they_were_asked(client, db_session, sint):
    regs = {
        r.contact_name: r
        for r in db_session.query(Registration).filter_by(activity_id=sint.activity.id)
    }
    answered = client.get(f"/admin/inschrijvingen/{regs['Zoë Laatst'].id}").text
    assert "Tijdslot" in answered and "Voormiddag, Namiddag" in answered

    open_ = client.get(f"/admin/inschrijvingen/{regs['Bert Midden'].id}").text
    assert "Antwoorden gevraagd op" in open_
