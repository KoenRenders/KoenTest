"""A taken e-mail address is a refusal with its reason at the door, never a 500 (CR-22, #1704).

The rule lives in one place, master data's `new_contact_detail`; a dozen doors
reach it. A door that forgot to translate the refusal would answer "Interne
serverfout" to someone who only typed an address that was taken. So the app
translates `EmailAddressInUse` once (`main.py`), and the member import reports
the row and goes on.

On made-up data, through the real routes.

Broken on purpose (7 October 2026): the handler in `main.py` taken out → the
board's screen answers 500; the import's check taken out → the run stops on
`EmailAddressInUse` instead of reporting; the meetings screen without its own
`except` → it says "Vul een voornaam en een achternaam in." for a taken address.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import ContactDetail, Member, MemberPerson, Person, new_contact_detail
from app.domains.mdm.import_service import upsert_families
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_postal_code

pytestmark = pytest.mark.ui_serverrendered

TAKEN = "bezet@example.com"
REASON = "Dit e-mailadres is al in gebruik door iemand anders."


def _member(db, first_name, *, email=None):
    person = Person(
        date_of_birth=date(1980, 1, 1), gender_code="M", first_name=first_name, last_name="Deur"
    )
    db.add(person)
    db.flush()
    household = Member()
    db.add(household)
    db.flush()
    db.add(MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID"))
    db.flush()
    if email:
        db.add(new_contact_detail(db, person, "EMAIL", email, is_primary=True))
        db.flush()
    return person, household


@pytest.fixture
def two_households(db_session):
    holder, _ = _member(db_session, "Houder", email=TAKEN)
    other, household = _member(db_session, "Buur")
    db_session.commit()
    return holder, other, household


def _admin(client) -> dict[str, str]:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _holders(db) -> int:
    db.expire_all()
    return db.query(ContactDetail).filter(ContactDetail.value == TAKEN).count()


def test_the_boards_person_screen_says_why(client, db_session, two_households):
    """Red without the handler: 500, "Interne serverfout"."""
    _holder, other, household = two_households
    answer = client.post(
        f"/admin/leden/gezin/{household.id}/persoon/{other.id}/email",
        data={"extra_email": TAKEN},
        headers=_admin(client),
    )
    assert answer.status_code == 422, answer.text[:200]
    assert answer.json()["detail"] == REASON
    assert _holders(db_session) == 1, "the address got a second holder after all"


def test_a_free_address_is_still_added_on_that_screen(client, db_session, two_households):
    """The door is not simply shut: the same request with a free address works."""
    _holder, other, household = two_households
    answer = client.post(
        f"/admin/leden/gezin/{household.id}/persoon/{other.id}/email",
        data={"extra_email": "vrij@example.com"},
        headers=_admin(client),
    )
    assert answer.status_code == 200, answer.text[:200]
    db_session.expire_all()
    row = db_session.query(ContactDetail).filter_by(value="vrij@example.com").one()
    assert row.person_id == other.id and row.confirmed_at is not None


def test_the_meeting_circle_says_why_and_makes_no_person(client, db_session, two_households):
    """Red without its own `except`: "Vul een voornaam en een achternaam in."."""
    answer = client.post(
        "/admin/vergaderingen/kring/nieuw",
        data={
            "first_name": "Gast",
            "last_name": "Deur",
            "person_email": TAKEN,
            "start_date": "2026-10-07",
        },
        headers=_admin(client),
    )
    assert answer.status_code == 200, answer.text[:200]
    assert REASON in answer.text
    assert "Vul een voornaam en een achternaam in." not in answer.text
    db_session.expire_all()
    assert db_session.query(Person).filter_by(first_name="Gast").count() == 0
    assert _holders(db_session) == 1


def _report_row(lidnr, first_name, last_name, **more):
    row = {
        "lidnr": lidnr,
        "voornaam": first_name,
        "naam": last_name,
        "straat": "Dorpsplein",
        "huisnummer": "1",
        "busnummer": "",
        "postcode": "2400",
        "gemeente": "Mol",
        "email": None,
        "telefoon": None,
        "gsm": None,
        "geboortedatum": date(1980, 5, 1),
        "geslacht": "M",
        "bestuurslid": None,
        "_relatie": "HOOFDLID",
    }
    return row | more


def test_the_import_reports_the_row_and_goes_on_the_same_in_preview_and_run(
    db_session, two_households
):
    """Red without the import's check: the run raises `EmailAddressInUse`."""
    seed_postal_code(db_session)
    families = [
        [_report_row("900", "Nieuw", "Rapport", email=TAKEN, gsm="0470000001")],
        [_report_row("901", "Ander", "Rapport", email="ander@example.com")],
    ]
    preview = upsert_families(db_session, families, {}, [], apply=False)
    run = upsert_families(db_session, families, {}, [], apply=True)
    db_session.commit()

    warning = "#900 Nieuw Rapport: e-mailadres niet overgenomen — al in gebruik door iemand anders."
    assert warning in preview.warnings and warning in run.warnings
    assert list(preview.lines) == list(run.lines), (
        "the preview promised other lines than the run wrote"
    )
    assert not [line for line in run.lines if "bezet@" in line], (
        "the refused address stands in a line"
    )

    assert _holders(db_session) == 1
    new = db_session.query(Person).filter_by(first_name="Nieuw", last_name="Rapport").one()
    kept = {c.contact_type_code: c.value for c in new.contact_details}
    assert kept == {"MOBILE": "0470000001"}, "the rest of the row was taken over"
    other = db_session.query(ContactDetail).filter_by(value="ander@example.com").one()
    assert other.confirmed_at is not None, "what the import writes counts at once"
