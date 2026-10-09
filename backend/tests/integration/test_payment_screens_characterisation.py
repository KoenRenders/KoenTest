"""CR-13 phase 2, B8 test 12: the payment screens render as they did.

Phase 2 makes `PaymentRecord` an aggregate: its state follows from its amounts,
`mark_paid` and `cancel` guard the transitions, `balance()` and `state` become the
owners the screens read. A gate that looks for a member *in* the output cannot see a
missing or empty rendering, so the screens are rendered on the code **before** the
conversion, kept, and the converted code must render the same (`tests/_snapshot.py`).

**"Before" is master `43ac7e05`, not this branch**: recorded by running this file
alone on that commit, before the first line of phase 2 changed.

The world holds one record in every state the screens tell apart: paid, partly
paid, open, a refund still to pay out, a paid-out refund, failed, cancelled — on
registrations and on a membership — so every branch of `derived_status` and of the
card grouping is on a screen.

**Re-recorded with CR-11 pilot A, K1 (#1555)**, on purpose: the title row, the
band of tiles, the status tabs and the filter bar became the key figures and the
toolbar, and the pager lost its count. Read before committing, as
`tests/_snapshot.py` asks: of the changed lines in the seven snapshots, none is a
table line (`<table`, `<tbody`, `<tr`, `<th`, `<td`) — the rows, their states and
their grouping render as they did. Inside the rows one thing changed, three times,
on the "Openstaand" screen: the link "Inschrijving" now carries the list's state
in its `?terug=` (the way back, CR-11 B7 test 21).

**Re-recorded again with K2 (#1556)**, on purpose: the table itself moved onto the
kit (`ui.data_table`), the unfold under a row went, the row became a link. Here
every table line changed, so "none changed" cannot be the check. Read instead,
per screen, old against new: the number of booking rows (activity 7, all 8,
all_open 6, family 3, list 8, registration_paid 2, registration_partial 1) and
of "Totaal inschrijving" rows (2, 2, 1, 1, 2, 1, 0) is the same, and every row
carries the badge of its state exactly once — the old screens showed each
status more often only because the phone copy of the badge and the status
select of each unfolded editor repeated it.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.domains.activities.models import (
    Activity,
    ActivityDate,
    ActivityProduct,
    ActivitySubRegistration,
    Registration,
    RegistrationItem,
)
from app.domains.mdm.api import ContactDetail, Member, MemberPerson, PaymentMethod, Person
from app.domains.membership.api import Membership
from app.domains.payment.api import PayableType, PaymentRecord, PaymentStatus, PaymentType
from tests._snapshot import compare, main_region, normalise
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

SNAPSHOTS = Path(__file__).parent / "snapshots" / "payment_screens"

BASE = 990_000
ACTIVITY_ID = BASE
COMPONENT_ID = BASE + 1
PRODUCT_ID = BASE + 2
MEMBER_ID = BASE + 10
PERSON_ID = BASE + 11
MEMBERSHIP_ID = BASE + 12
REGISTRATION_IDS = {"paid": BASE + 20, "partial": BASE + 21, "open": BASE + 22, "other": BASE + 23}
RECORD_IDS = {
    "paid": "00000000-0000-4000-8000-000000990101",
    "partial": "00000000-0000-4000-8000-000000990102",
    "open": "00000000-0000-4000-8000-000000990103",
    "refund_due": "00000000-0000-4000-8000-000000990104",
    "refunded": "00000000-0000-4000-8000-000000990105",
    "failed": "00000000-0000-4000-8000-000000990106",
    "cancelled": "00000000-0000-4000-8000-000000990107",
    "membership": "00000000-0000-4000-8000-000000990108",
}


def _names() -> dict[int, str]:
    names = {
        ACTIVITY_ID: "<ACTIVITY>",
        COMPONENT_ID: "<COMPONENT>",
        PRODUCT_ID: "<PRODUCT>",
        MEMBER_ID: "<MEMBER>",
        PERSON_ID: "<PERSON>",
        MEMBERSHIP_ID: "<MEMBERSHIP>",
    }
    names.update({i: f"<R:{k}>" for k, i in REGISTRATION_IDS.items()})
    return names


def _literals() -> dict[str, str]:
    return {record_id: f"<REC:{key}>" for key, record_id in RECORD_IDS.items()}


def _at(day: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, day, 10, minute, tzinfo=timezone.utc)


@pytest.fixture
def world(db_session):
    db = db_session
    db.add(Activity(id=ACTIVITY_ID, name="Betaalkarakter"))
    db.flush()
    db.add(ActivityDate(activity_id=ACTIVITY_ID, start_date=date(2099, 6, 1)))
    db.add(
        ActivitySubRegistration(
            id=COMPONENT_ID,
            activity_id=ACTIVITY_ID,
            name="Deelname",
            registration_type_code="INDIVIDUAL",
            price=Decimal("0"),
            is_free=True,
        )
    )
    db.flush()
    db.add(
        ActivityProduct(
            id=PRODUCT_ID,
            component_id=COMPONENT_ID,
            name="Ticket",
            price=Decimal("10.00"),
            is_free=False,
        )
    )
    db.add(Member(id=MEMBER_ID))
    db.add(
        Person(
            id=PERSON_ID,
            first_name="Betty",
            last_name="Betaalmans",
            date_of_birth=date(1975, 5, 5),
            gender_code="F",
        )
    )
    db.flush()
    db.add(MemberPerson(member_id=MEMBER_ID, person_id=PERSON_ID, relation_type="HOOFDLID"))
    db.add(
        ContactDetail(
            person_id=PERSON_ID,
            contact_type_code="EMAIL",
            value="betaal@example.org",
            is_primary=True,
        )
    )
    db.add(
        Membership(
            id=MEMBERSHIP_ID,
            member_id=MEMBER_ID,
            year=2026,
            is_active=True,
            valid_from=date(2026, 1, 1),
            valid_to=date(2026, 12, 31),
        )
    )
    db.flush()
    for key, registration_id in REGISTRATION_IDS.items():
        db.add(
            Registration(
                id=registration_id,
                activity_id=ACTIVITY_ID,
                component_id=COMPONENT_ID,
                person_id=PERSON_ID if key == "paid" else None,
                registered_at=_at(1),
                registration_type="INDIVIDUAL",
                contact_name=f"Deelnemer {key}",
                contact_email=f"{key}@example.org",
                phone="0470000000",
                payment_method=PaymentMethod.TRANSFER,
            )
        )
        db.flush()
        db.add(RegistrationItem(registration_id=registration_id, product_id=PRODUCT_ID, quantity=2))
    db.flush()

    # Each record its own moment: the lists order by creation time and have no
    # tiebreaker, so equal times would render in whatever order the database returns.
    moments = {key: minute for minute, key in enumerate(RECORD_IDS)}

    def record(key, payable_type, payable_id, amount, status, *, kind=PaymentType.CHARGE, **extra):
        db.add(
            PaymentRecord(
                id=RECORD_IDS[key],
                payable_type=payable_type,
                payable_id=payable_id,
                amount=Decimal(amount),
                method=PaymentMethod.TRANSFER,
                status=status,
                type=kind,
                created_at=_at(2, moments[key]),
                **extra,
            )
        )
        db.flush()

    reg = PayableType.REGISTRATION
    record(
        "paid",
        reg,
        REGISTRATION_IDS["paid"],
        "20.00",
        PaymentStatus.PAID,
        amount_paid=Decimal("20.00"),
        paid_at=_at(3),
    )
    record(
        "partial",
        reg,
        REGISTRATION_IDS["partial"],
        "20.00",
        PaymentStatus.PENDING,
        amount_paid=Decimal("5.00"),
        paid_at=_at(3),
    )
    record("open", reg, REGISTRATION_IDS["open"], "20.00", PaymentStatus.PENDING)
    record(
        "refund_due",
        reg,
        REGISTRATION_IDS["paid"],
        "-5.00",
        PaymentStatus.PENDING,
        kind=PaymentType.REFUND,
        refund_of_id=RECORD_IDS["paid"],
    )
    record(
        "refunded",
        reg,
        REGISTRATION_IDS["other"],
        "-4.00",
        PaymentStatus.PAID,
        kind=PaymentType.REFUND,
        amount_paid=Decimal("-4.00"),
        paid_at=_at(4),
    )
    record("failed", reg, REGISTRATION_IDS["other"], "20.00", PaymentStatus.FAILED)
    record("cancelled", reg, REGISTRATION_IDS["other"], "20.00", PaymentStatus.CANCELLED)
    record(
        "membership",
        PayableType.MEMBERSHIP,
        MEMBERSHIP_ID,
        "30.00",
        PaymentStatus.PAID,
        amount_paid=Decimal("30.00"),
        paid_at=_at(3),
    )


SCREENS = {
    "all": "/admin/betalingen",
    "all_open": "/admin/betalingen?zicht=openstaand",
    "list": "/admin/betalingen/lijst",
    "activity": f"/admin/activiteiten/{ACTIVITY_ID}/betalingen",
    "family": f"/admin/leden/gezin/{MEMBER_ID}/betalingen",
    "registration_paid": f"/admin/inschrijvingen/{REGISTRATION_IDS['paid']}/betalingen",
    "registration_partial": f"/admin/inschrijvingen/{REGISTRATION_IDS['partial']}/betalingen",
}


@pytest.mark.parametrize("screen", sorted(SCREENS))
def test_the_payment_screen_renders_as_before(client, world, screen):
    from app.domains.auth.api import SESSION_COOKIE, make_session_value

    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    response = client.get(SCREENS[screen])
    assert response.status_code == 200, (screen, response.status_code)
    html = response.text
    body = main_region(html) if "<main" in html else html
    assert "Deelnemer" in body or "Betaalmans" in body or "Betaalkarakter" in body, (
        f"{screen} shows none of the world"
    )
    compare(SNAPSHOTS, screen, normalise(body, _names(), _literals()), before="phase 2")


# ── T16 of CR-21 (#1748): what the describers must leave as it was ──────────────
#
# Phase 0 of CR-21 moves "what is this payment for" out of `payment` — the name, the
# description, the links, the place in the filter tree, the export's words, the
# subject of a change line — into describers that activities and membership register.
# The seven screens above do not show all of that, so these were added and **recorded
# on master `1bae78ec`, before the first describer existed**: the page of a booking
# (the jump link to the activity or the household), the three filter contexts, the
# screen's export (not the JSON export route, which CR-13 phase 4b prunes) and the
# change lines of a payment.

DESCRIBED = {
    "booking_registration": f"/admin/betalingen/{RECORD_IDS['paid']}",
    "booking_refund": f"/admin/betalingen/{RECORD_IDS['refund_due']}",
    "booking_membership": f"/admin/betalingen/{RECORD_IDS['membership']}",
    "filter_membership": "/admin/betalingen/lijst?context=membership",
    "filter_year": "/admin/betalingen/lijst?context=year-2026",
    "filter_component": f"/admin/betalingen/lijst?context=comp-{COMPONENT_ID}",
}


def _sign_in(client) -> None:
    from app.domains.auth.api import SESSION_COOKIE, make_session_value

    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


@pytest.mark.parametrize("screen", sorted(DESCRIBED))
def test_what_a_payment_is_for_reads_as_before(client, world, screen):
    _sign_in(client)
    response = client.get(DESCRIBED[screen])
    assert response.status_code == 200, (screen, response.status_code)
    html = response.text
    body = main_region(html) if "<main" in html else html
    assert "Deelnemer" in body or "Betaalmans" in body or "Betaalkarakter" in body, (
        f"{screen} shows none of the world"
    )
    compare(SNAPSHOTS, screen, normalise(body, _names(), _literals()), before="the describers")


def _export_rows(response) -> list[list]:
    from io import BytesIO

    from odf.opendocument import load
    from odf.table import Table, TableCell, TableRow
    from odf.teletype import extractText

    rows = []
    for tr in (
        load(BytesIO(response.content)).getElementsByType(Table)[0].getElementsByType(TableRow)
    ):
        cells: list = []
        for tc in tr.getElementsByType(TableCell):
            value = tc.getAttribute("value")
            repeat = int(tc.getAttribute("numbercolumnsrepeated") or 1)
            cells.extend([value if value is not None else extractText(tc)] * repeat)
        rows.append(cells)
    return rows


@pytest.mark.parametrize(
    "name, query", [("export_all", ""), ("export_membership", "?context=membership")]
)
def test_the_screens_export_reads_as_before(client, world, name, query):
    _sign_in(client)
    response = client.get(f"/admin/betalingen/export{query}")
    assert response.status_code == 200, response.status_code
    rows = _export_rows(response)
    assert len(rows) >= 2 and any("Betaalmans" in str(c) for row in rows for c in row), rows[:3]
    text = "\n".join(" | ".join(str(c) for c in row) for row in rows) + "\n"
    compare(SNAPSHOTS, name, normalise(text, _names(), _literals()), before="the describers")


def test_the_change_lines_of_a_payment_name_their_subject_as_before(client, world, db_session):
    """The subject of a payment's change line comes through the payable: the person of a
    registration, the household of a membership (`reporting/changes.py::from_payment`)."""
    from app.domains.reporting.changes import _SubjectResolver

    _sign_in(client)
    lines = []
    # "paid" is a member's registration, "partial" a guest's: two roads to a subject.
    for key in ("paid", "partial", "membership"):
        payable_type = "membership" if key == "membership" else "registration"
        payable_id = MEMBERSHIP_ID if key == "membership" else REGISTRATION_IDS[key]
        subject = _SubjectResolver(db_session).from_payment(payable_type, payable_id)
        lines.append(f"{key}: {sorted((subject or {}).items())}")
    text = "\n".join(lines) + "\n"
    assert "Betaalmans" in text, text
    # What the change line's subject is read from, by name: in this world a household
    # and its head give the same four columns, so the snapshot alone cannot tell
    # whether a membership still answers with its household.
    from app.domains.payment.api import describe_one

    membership = describe_one(db_session, "membership", MEMBERSHIP_ID)
    member_registration = describe_one(db_session, "registration", REGISTRATION_IDS["paid"])
    guest_registration = describe_one(db_session, "registration", REGISTRATION_IDS["partial"])
    assert membership.household_id == MEMBER_ID
    assert member_registration.person_id == PERSON_ID
    assert guest_registration.person_id is None
    assert guest_registration.contact_email == "partial@example.org"
    compare(
        SNAPSHOTS,
        "change_subjects",
        normalise(text, _names(), _literals()),
        before="the describers",
    )
