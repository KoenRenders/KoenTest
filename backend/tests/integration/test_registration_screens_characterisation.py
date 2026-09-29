"""CR-13 phase 1, B8 test 12: the registration screens render as they did.

Phase 1 turns `Registration` into an aggregate — validators, `check()`,
`total()`, the service that registers — and every screen that shows a
registration reads through that work. A gate that looks for a member *in* the
output cannot see a missing or empty rendering (CR-12 phase 4 learned that), so
the screens are rendered on the code **before** the conversion, the output is
kept, and the converted code must render the same.

**"Before" is master `4b5e96f7`, not this branch.** The snapshots were recorded
by running this file alone on that commit, before the first line of phase 1
changed. A snapshot recorded after the change proves nothing.

Six screens, each at the region that shows registrations:

- the public registration form of a component (`/activiteiten/{id}/inschrijven/{c}`);
- the back office's list per activity, one registration's page and its fragment,
  and the board's "new registration" form;
- a family's registrations tab.

The world is fixed: ids high enough that masking cannot hit a number the page
renders on its own, dates in 2099 so "open" never turns into "past", one member
with a membership valid on the registration date (the member price), a paid,
a free and a pay-on-site product, a component that requires a team name, and
one partially paid payment record (the balance).

To rewrite the snapshots after an intended change: `SNAPSHOT_UPDATE=1 pytest
tests/integration/test_registration_screens_characterisation.py`,
and read the diff before committing it. An unread snapshot update is a test
switched off.
"""

from __future__ import annotations

import os
import re
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
from app.domains.payment.api import (
    PayableType,
    PaymentRecord,
    PaymentStatus,
    PaymentType,
)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

SNAPSHOTS = Path(__file__).parent / "snapshots" / "registration_screens"

BASE = 980_000
ACTIVITY_ID = BASE
TEAM_COMPONENT_ID = BASE + 1
PLAIN_COMPONENT_ID = BASE + 2
PRODUCT_IDS = {"paid": BASE + 10, "free": BASE + 11, "on_site": BASE + 12, "plain": BASE + 13}
MEMBER_ID = BASE + 20
PERSON_ID = BASE + 21
REGISTRATION_IDS = {"member": BASE + 30, "guest": BASE + 31}
ITEM_IDS = {"paid": BASE + 40, "free": BASE + 41, "on_site": BASE + 42, "plain": BASE + 43}
RECORD_ID = "00000000-0000-4000-8000-000000980050"


def _names() -> dict[int, str]:
    names = {
        ACTIVITY_ID: "<ACTIVITY>",
        TEAM_COMPONENT_ID: "<C:team>",
        PLAIN_COMPONENT_ID: "<C:plain>",
        MEMBER_ID: "<MEMBER>",
        PERSON_ID: "<PERSON>",
    }
    names.update({i: f"<P:{k}>" for k, i in PRODUCT_IDS.items()})
    names.update({i: f"<R:{k}>" for k, i in REGISTRATION_IDS.items()})
    names.update({i: f"<I:{k}>" for k, i in ITEM_IDS.items()})
    return names


@pytest.fixture
def world(db_session):
    db = db_session
    activity = Activity(id=ACTIVITY_ID, name="Karakterisering", description="Elk scherm")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=ACTIVITY_ID, start_date=date(2099, 6, 1)))
    db.add(
        ActivitySubRegistration(
            id=TEAM_COMPONENT_ID,
            activity_id=ACTIVITY_ID,
            name="Ploegen",
            registration_type_code="INDIVIDUAL",
            price=Decimal("0"),
            is_free=True,
            team_name_required=True,
            max_participants=20,
            sort_order=0,
        )
    )
    db.add(
        ActivitySubRegistration(
            id=PLAIN_COMPONENT_ID,
            activity_id=ACTIVITY_ID,
            name="Los",
            registration_type_code="INDIVIDUAL",
            price=Decimal("0"),
            is_free=True,
            sort_order=1,
        )
    )
    db.flush()
    products = [
        (
            "paid",
            TEAM_COMPONENT_ID,
            dict(price=Decimal("12.50"), member_price=Decimal("10.00"), is_free=False),
        ),
        ("free", TEAM_COMPONENT_ID, dict(price=Decimal("0"), is_free=True)),
        (
            "on_site",
            TEAM_COMPONENT_ID,
            dict(price=Decimal("3.00"), pay_on_site=True, is_free=False),
        ),
        ("plain", PLAIN_COMPONENT_ID, dict(price=Decimal("5.00"), is_free=False)),
    ]
    for position, (key, component, extra) in enumerate(products):
        db.add(
            ActivityProduct(
                id=PRODUCT_IDS[key],
                component_id=component,
                name=f"Product {key}",
                sort_order=position,
                **extra,
            )
        )
    db.flush()

    db.add(Member(id=MEMBER_ID))
    db.add(
        Person(
            id=PERSON_ID,
            first_name="Karel",
            last_name="Karakter",
            date_of_birth=date(1980, 1, 1),
            gender_code="M",
        )
    )
    db.flush()
    db.add(MemberPerson(member_id=MEMBER_ID, person_id=PERSON_ID, relation_type="HOOFDLID"))
    db.add(
        ContactDetail(
            person_id=PERSON_ID,
            contact_type_code="EMAIL",
            value="karakter@example.org",
            is_primary=True,
        )
    )
    db.add(
        Membership(
            member_id=MEMBER_ID,
            year=2099,
            is_active=True,
            valid_from=date(2099, 1, 1),
            valid_to=date(2099, 12, 31),
        )
    )
    db.flush()

    db.add(
        Registration(
            id=REGISTRATION_IDS["member"],
            activity_id=ACTIVITY_ID,
            component_id=TEAM_COMPONENT_ID,
            person_id=PERSON_ID,
            registered_at=datetime(2099, 2, 1, 10, 0, tzinfo=timezone.utc),
            registration_type="INDIVIDUAL",
            contact_name="Karel Karakter",
            contact_email="karakter@example.org",
            phone="0470 00 00 01",
            team_name="De Karakters",
            payment_method=PaymentMethod.TRANSFER,
            remarks="Graag vooraan",
        )
    )
    db.add(
        Registration(
            id=REGISTRATION_IDS["guest"],
            activity_id=ACTIVITY_ID,
            component_id=PLAIN_COMPONENT_ID,
            registered_at=datetime(2099, 2, 2, 11, 0, tzinfo=timezone.utc),
            registration_type="INDIVIDUAL",
            contact_name="Gast Gastmans",
            contact_email="gast@example.org",
            phone="0470 00 00 02",
            payment_method=PaymentMethod.TRANSFER,
        )
    )
    db.flush()
    items = [
        ("paid", "member", 2),
        ("free", "member", 1),
        ("on_site", "member", 1),
        ("plain", "guest", 3),
    ]
    for key, registration, quantity in items:
        db.add(
            RegistrationItem(
                id=ITEM_IDS[key],
                registration_id=REGISTRATION_IDS[registration],
                product_id=PRODUCT_IDS[key],
                quantity=quantity,
            )
        )
    db.flush()
    db.add(
        PaymentRecord(
            id=RECORD_ID,
            payable_type=PayableType.REGISTRATION,
            payable_id=REGISTRATION_IDS["member"],
            amount=Decimal("20.00"),
            amount_paid=Decimal("5.00"),
            method=PaymentMethod.TRANSFER,
            status=PaymentStatus.PENDING,
            type=PaymentType.CHARGE,
            structured_communication="+++098/0000/05097+++",
            created_at=datetime(2099, 2, 1, 10, 1, tzinfo=timezone.utc),
        )
    )
    db.flush()
    return activity


def _login(client):
    from app.domains.auth.api import SESSION_COOKIE, make_session_value

    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _main(html: str) -> str:
    """The page's own content: `<main>`, so the chrome around it does not count."""
    match = re.search(r"<main\b.*?</main>", html, re.S)
    assert match, "the screen has no <main> — is this test still looking?"
    return match.group(0)


def _normalise(fragment: str) -> str:
    text = fragment
    text = text.replace(RECORD_ID, "<RECORD>")
    for number, name in sorted(_names().items(), key=lambda kv: -kv[0]):
        text = re.sub(rf"(?<!\d){number}(?!\d)", name, text)
    text = re.sub(r"[A-Za-z0-9_\-.]{40,}", "<TOKEN>", text)
    text = re.sub(r'(name="csrf_token" value=")[^"]*', r"\1<CSRF>", text)
    text = re.sub(r'("X-CSRF-Token"\s*:\s*")[^"]*', r"\1<CSRF>", text)
    text = re.sub(r">\s+<", ">\n<", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip() + "\n"


def _compare(screen: str, html: str) -> None:
    path = SNAPSHOTS / f"{screen}.html"
    got = _normalise(html)
    if os.environ.get("SNAPSHOT_UPDATE") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(got, encoding="utf-8")
    assert path.exists(), f"no snapshot for {screen}; run with SNAPSHOT_UPDATE=1"
    want = path.read_text(encoding="utf-8")
    if got != want:
        import difflib

        diff = "".join(
            difflib.unified_diff(
                want.splitlines(True), got.splitlines(True), "snapshot", "rendered", n=2
            )
        )
        pytest.fail(f"{screen} renders differently from before phase 1:\n{diff}")


SCREENS = {
    "public_form_team": f"/activiteiten/{ACTIVITY_ID}/inschrijven/{TEAM_COMPONENT_ID}",
    "public_form_plain": f"/activiteiten/{ACTIVITY_ID}/inschrijven/{PLAIN_COMPONENT_ID}",
    "admin_list": f"/admin/activiteiten/{ACTIVITY_ID}/inschrijvingen",
    "admin_detail_member": f"/admin/inschrijvingen/{REGISTRATION_IDS['member']}",
    "admin_detail_guest": f"/admin/inschrijvingen/{REGISTRATION_IDS['guest']}",
    "admin_fragment_member": f"/admin/inschrijvingen/{REGISTRATION_IDS['member']}/fragment",
    "admin_new": f"/admin/activiteiten/{ACTIVITY_ID}/inschrijvingen/nieuw",
    "admin_new_team": (
        f"/admin/activiteiten/{ACTIVITY_ID}/inschrijvingen/nieuw?onderdeel={TEAM_COMPONENT_ID}"
    ),
    "family_tab": f"/admin/leden/gezin/{MEMBER_ID}/inschrijvingen",
}


@pytest.mark.parametrize("screen", sorted(SCREENS))
def test_the_registration_screen_renders_as_before(client, world, screen):
    if screen.startswith(("admin", "family")):
        _login(client)
    response = client.get(SCREENS[screen])
    assert response.status_code == 200, (screen, response.status_code)
    html = response.text
    body = _main(html) if "<main" in html else html
    # The page must show the world, or the snapshot records an empty screen.
    assert "Karakter" in body or "Ploegen" in body or "Los" in body, f"{screen} shows none of it"
    _compare(screen, body)
