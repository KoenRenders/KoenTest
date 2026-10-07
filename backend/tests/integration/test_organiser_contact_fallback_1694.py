"""An organiser's empty contact field shows the member's own value in grey (#1694).

Koen, 7 October 2026: on the activity record the two fields "Ander e-mailadres"
and "Ander gsm-nummer" of an organiser were empty with a help text, so the
board could not see whether the member had an address or a number at all — an
organiser without a number went onto the poster without one, unnoticed.

Now an empty field shows what it falls back to: while editing as the control's
grey placeholder (never a value), in read mode in the soft ink with "(van de
fiche)". When the member's record holds nothing, the field says so. The grey
value comes from `member_contacts`, the function `organisers_for` — and so the
poster — reads.

On made-up data, through the real routes.

Broken on purpose (7 October 2026), each red for its own reason: the `fallback`
out of the organiser row → the placeholder tests; the kit's read branch for a
fallback removed → the read-mode test shows "—"; the record given a lookup of
its own that takes the LAST contact row → the grey value differs from the
poster's; the candidates without their own values → the picked row keeps its
tokens.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from datetime import date

import pytest

from app.domains.activities.api import add_organiser, member_contacts, update_organiser
from app.domains.activities.models import Activity, ActivityOrganiser
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.designstudio import service as designstudio
from app.domains.mdm.api import CONTACT, ContactDetail, Member, MemberPerson, Person
from app.kernel.codes import code_of
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

NO_EMAIL = "geen e-mailadres op de fiche"
NO_MOBILE = "geen nummer op de fiche"


def _member(db, first_name, *, email=None, mobile=None):
    person = Person(
        date_of_birth=date(1980, 1, 1), gender_code="M", first_name=first_name, last_name="Trekker"
    )
    db.add(person)
    db.flush()
    household = Member()
    db.add(household)
    db.flush()
    db.add(MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID"))
    if email:
        db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=email))
    if mobile:
        db.add(ContactDetail(person_id=person.id, contact_type_code="MOBILE", value=mobile))
    db.flush()
    return person


@pytest.fixture
def record(db_session):
    """One activity with three organisers: both details, neither, and an override."""
    activity = Activity(name="Quiz met trekkers")
    db_session.add(activity)
    db_session.flush()
    both = add_organiser(
        db_session,
        activity.id,
        _member(db_session, "Beide", email="beide@example.com", mobile="0470000001").id,
    )
    neither = add_organiser(db_session, activity.id, _member(db_session, "Geen").id)
    other = add_organiser(
        db_session,
        activity.id,
        _member(db_session, "Ander", email="ander@example.com", mobile="0470000002").id,
    )
    for row in (both, neither, other):
        update_organiser(db_session, activity.id, row.id, {"is_contact": True})
    update_organiser(
        db_session,
        activity.id,
        other.id,
        {"email_override": "quiz@example.com", "mobile_override": "0470000003"},
    )
    db_session.commit()
    return activity.id, both.id, neither.id, other.id


def _page(client, activity_id: int, *, edit: bool) -> str:
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    answer = client.get(f"/admin/activiteiten/{activity_id}" + ("?bewerken=1" if edit else ""))
    assert answer.status_code == 200
    return answer.text


def _input(page: str, organiser_id: int, field: str) -> dict[str, str]:
    """The attributes of one override's control."""
    tags = re.findall(rf'<input[^>]*\bid="o-{organiser_id}-{field}"[^>]*>', page)
    assert len(tags) == 1, f"{len(tags)} controls for {field} of organiser {organiser_id}"
    return {k: html_lib.unescape(v) for k, v in re.findall(r'([\w-]+)="([^"]*)"', tags[0])}


def _read_value(page: str, organiser_id: int, field: str) -> str:
    """What read mode shows for one override, tags and all."""
    found = re.search(
        rf'<div data-field="o\.{organiser_id}\.{field}".*?<p data-value[^>]*>(.*?)</p>', page, re.S
    )
    assert found, f"no read value for {field} of organiser {organiser_id}"
    return found.group(1).strip()


def test_an_empty_override_shows_the_members_own_value_as_placeholder(client, record):
    """Red on master: no placeholder at all."""
    activity_id, both, _neither, _other = record
    page = _page(client, activity_id, edit=True)
    email = _input(page, both, "email_override")
    mobile = _input(page, both, "mobile_override")
    assert email["placeholder"] == "beide@example.com"
    assert mobile["placeholder"] == "0470 00 00 01", "the number in its readable form (#1675)"
    assert "value" not in email and "value" not in mobile, "the grey value is never a value"
    assert "Leeg: het adres van het lid, hierboven in het grijs." in page
    assert "Leeg: het nummer van het lid, hierboven in het grijs." in page


def test_a_member_without_the_detail_says_so(client, record):
    activity_id, _both, neither, _other = record
    page = _page(client, activity_id, edit=True)
    assert _input(page, neither, "email_override")["placeholder"] == NO_EMAIL
    assert _input(page, neither, "mobile_override")["placeholder"] == NO_MOBILE
    read = _page(client, activity_id, edit=False)
    for field, text in (("email_override", NO_EMAIL), ("mobile_override", NO_MOBILE)):
        shown = _read_value(read, neither, field)
        assert text in shown and "data-fallback" in shown
        assert "van de fiche" not in shown, "nothing comes from the record, so nothing is marked"


def test_a_filled_override_wins_and_shows_as_a_value(client, record):
    activity_id, _both, _neither, other = record
    page = _page(client, activity_id, edit=True)
    assert _input(page, other, "email_override")["value"] == "quiz@example.com"
    assert _input(page, other, "mobile_override")["value"] == "0470000003", (
        "the input keeps what is stored"
    )
    read = _page(client, activity_id, edit=False)
    email = _read_value(read, other, "email_override")
    mobile = _read_value(read, other, "mobile_override")
    assert "quiz@example.com" in email and "data-fallback" not in email
    assert "0470 00 00 03" in mobile and "data-fallback" not in mobile
    assert "ander@example.com" not in email, "the member's own address does not show beside it"


def test_read_mode_shows_the_value_that_is_used_soft_and_marked(client, record):
    """Red on master: "—"."""
    activity_id, both, _neither, _other = record
    read = _page(client, activity_id, edit=False)
    email = _read_value(read, both, "email_override")
    mobile = _read_value(read, both, "mobile_override")
    assert re.search(r'<span data-fallback class="[^"]*text-ink-soft[^"]*">', email)
    assert "beide@example.com (van de fiche)" in email
    assert "0470 00 00 01 (van de fiche)" in mobile
    assert "—" not in email and "—" not in mobile


def test_the_grey_value_is_what_the_poster_prints(client, db_session, record):
    """One function: the record's grey value and the poster's contact line."""
    activity_id, both, _neither, _other = record
    page = _page(client, activity_id, edit=True)
    printed = {c.name: c for c in designstudio._organisers(db_session, activity_id)}
    contact = printed["Beide Trekker"]
    assert _input(page, both, "email_override")["placeholder"] == contact.email
    assert _input(page, both, "mobile_override")["placeholder"] == contact.mobile
    assert printed["Geen Trekker"].email == "" and printed["Geen Trekker"].mobile == ""
    assert printed["Ander Trekker"].email == "quiz@example.com"


def test_two_rows_of_one_type_give_the_same_value_on_the_record_and_the_poster(
    client, db_session, record
):
    """A second lookup beside `member_contacts` would have to pick between two
    rows a second time — and could pick the other one."""
    activity_id, both, _neither, _other = record
    person_id = db_session.get(ActivityOrganiser, both).person_id
    db_session.add(
        ContactDetail(person_id=person_id, contact_type_code="MOBILE", value="0470000009")
    )
    db_session.commit()
    own = member_contacts(db_session, [person_id])[(person_id, code_of(CONTACT.MOBILE))]
    page = _page(client, activity_id, edit=True)
    printed = {c.name: c for c in designstudio._organisers(db_session, activity_id)}
    assert _input(page, both, "mobile_override")["placeholder"] == printed["Beide Trekker"].mobile
    assert printed["Beide Trekker"].mobile.replace(" ", "") == own


def test_a_member_picked_in_the_search_brings_its_own_values(client, db_session, record):
    """The row the search adds is built in the page from a template: its two
    placeholders come as tokens with the candidate."""
    activity_id, _both, _neither, _other = record
    _member(db_session, "Zoekbaar", email="zoek@example.com", mobile="0470000004")
    _member(db_session, "Zoekleeg")
    db_session.commit()
    page = _page(client, activity_id, edit=True)
    template = page[page.index("<template", page.index('id="aa-group-organisers"')) :]
    template = template[: template.index("</template>")]
    assert 'placeholder="__EMAIL__"' in template and 'placeholder="__MOBILE__"' in template

    answer = client.get(f"/admin/activiteiten/{activity_id}/organisatoren?organiser_q=Zoek")
    picks = [
        json.loads(html_lib.unescape(raw))
        for raw in re.findall(r'data-pick="([^"]*)"', answer.text)
    ]
    by_name = {pick["__NAME__"]: pick for pick in picks}
    assert by_name["Zoekbaar Trekker"]["__EMAIL__"] == "zoek@example.com"
    assert by_name["Zoekbaar Trekker"]["__MOBILE__"] == "0470 00 00 04"
    assert by_name["Zoekleeg Trekker"]["__EMAIL__"] == NO_EMAIL
    assert by_name["Zoekleeg Trekker"]["__MOBILE__"] == NO_MOBILE
