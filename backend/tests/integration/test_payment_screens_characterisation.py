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
