"""E2E: the figures above the Betalingen tab of a household and of a registration (#2128).

The hand-drawn band of tiles became the kit's three figures: Netto te betalen · Nog te
ontvangen · Nog terug te betalen. Read from the rendered DOM, at 390 and 1 100 px:

- each of the three labels stands once, and no "Ontvangen" figure is left;
- the three figures stand on one line (equal top) at 1 100 px; at 390 px they wrap like the
  approved concept's, each inside the window, and the page does not scroll sideways at either;
- an open amount carries the warning colour, the amount that is nothing does not;
- the amounts are those of the payments made for this file: a household with a membership
  paid (30), a registration paid (20) with a refund of 5 still to pay out, and a second
  registration of 20 not paid yet.

Prints are taken when `E2E_PRINT_DIR` is set. Broken on purpose (19 October 2026): the
include of `ui.figures` left out of `_bt_boven.html` → every test here is red.
"""

import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

BASE_ID = 991_000
MEMBER_ID = BASE_ID + 10
PERSON_ID = BASE_ID + 11
MEMBERSHIP_ID = BASE_ID + 12
PAID, OPEN = BASE_ID + 20, BASE_ID + 21
LABELS = ["Netto te betalen", "Nog te ontvangen", "Nog terug te betalen"]
FIGURES = """() => [...document.querySelectorAll('#bt-boven [data-figures] [data-figure]')].map(f => {
  const box = f.getBoundingClientRect();
  return { value: f.innerText.trim(), top: Math.round(box.top), left: Math.round(box.left),
    right: Math.round(box.right), warning: f.className.includes('text-brand-warning'),
    label: f.parentElement.querySelector('[data-figure-label]').innerText.trim() };
})"""


def _seed() -> None:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.models import (
        Activity,
        ActivityDate,
        ActivityProduct,
        ActivitySubRegistration,
        Registration,
        RegistrationItem,
    )
    from app.domains.mdm.api import Member, MemberPerson, PaymentMethod, Person
    from app.domains.membership.api import Membership
    from app.domains.payment.api import PayableType, PaymentRecord, PaymentStatus, PaymentType

    db = SessionLocal()
    try:
        db.add(Activity(id=BASE_ID, name="Cijfers2128"))
        db.flush()
        db.add(ActivityDate(activity_id=BASE_ID, start_date=date(2099, 6, 1)))
        db.add(
            ActivitySubRegistration(
                id=BASE_ID + 1,
                activity_id=BASE_ID,
                name="Deelname",
                registration_type_code="INDIVIDUAL",
                price=Decimal("0"),
                is_free=True,
            )
        )
        db.flush()
        db.add(
            ActivityProduct(
                id=BASE_ID + 2,
                component_id=BASE_ID + 1,
                name="Ticket",
                price=Decimal("10.00"),
                is_free=False,
            )
        )
        db.add(Member(id=MEMBER_ID))
        db.add(
            Person(
                id=PERSON_ID,
                first_name="Cijfer",
                last_name="Tweeduizend",
                date_of_birth=date(1975, 5, 5),
                gender_code="F",
            )
        )
        db.flush()
        db.add(MemberPerson(member_id=MEMBER_ID, person_id=PERSON_ID, relation_type="HOOFDLID"))
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
        for registration_id in (PAID, OPEN):
            db.add(
                Registration(
                    id=registration_id,
                    activity_id=BASE_ID,
                    component_id=BASE_ID + 1,
                    person_id=PERSON_ID,
                    registered_at=datetime(2026, 9, 1, 10, tzinfo=timezone.utc),
                    registration_type="INDIVIDUAL",
                    contact_name="Cijfer Tweeduizend",
                    contact_email="cijfer@example.org",
                    phone="0470000000",
                    payment_method=PaymentMethod.TRANSFER,
                )
            )
            db.flush()
            db.add(
                RegistrationItem(
                    registration_id=registration_id, product_id=BASE_ID + 2, quantity=2
                )
            )
        db.flush()

        def record(n, payable_type, payable_id, amount, status, *, kind=PaymentType.CHARGE, **x):
            db.add(
                PaymentRecord(
                    id=f"00000000-0000-4000-8000-{BASE_ID * 1000 + n:012d}",
                    payable_type=payable_type,
                    payable_id=payable_id,
                    amount=Decimal(amount),
                    method=PaymentMethod.TRANSFER,
                    status=status,
                    type=kind,
                    created_at=datetime(2026, 9, 2, 10, n, tzinfo=timezone.utc),
                    **x,
                )
            )
            db.flush()

        paid_at = datetime(2026, 9, 3, 10, tzinfo=timezone.utc)
        record(
            1, PayableType.REGISTRATION, PAID, "20.00", PaymentStatus.PAID,
            amount_paid=Decimal("20.00"), paid_at=paid_at,
        )  # fmt: skip
        record(
            2, PayableType.REGISTRATION, PAID, "-5.00", PaymentStatus.PENDING,
            kind=PaymentType.REFUND,
            refund_of_id=f"00000000-0000-4000-8000-{BASE_ID * 1000 + 1:012d}",
        )  # fmt: skip
        record(3, PayableType.REGISTRATION, OPEN, "20.00", PaymentStatus.PENDING)
        record(
            4, PayableType.MEMBERSHIP, MEMBERSHIP_ID, "30.00", PaymentStatus.PAID,
            amount_paid=Decimal("30.00"), paid_at=paid_at,
        )  # fmt: skip
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def world():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    _seed()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _open(world, path: str, width: int):
    browser, session = world
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, session, BASE)
    page.goto(path)
    pagina_klaar(page)
    return page


def _print(page, name: str) -> None:
    folder = os.environ.get("E2E_PRINT_DIR")
    if not folder:
        return
    os.makedirs(folder, exist_ok=True)
    height = page.evaluate("document.documentElement.scrollHeight")
    page.set_viewport_size({"width": page.viewport_size["width"], "height": height})
    page.screenshot(path=os.path.join(folder, name), caret="initial")


SCREENS = {
    "gezin": (f"/admin/leden/gezin/{MEMBER_ID}/betalingen", ["€ 65,00", "€ 20,00", "€ 5,00"]),
    "inschrijving": (f"/admin/inschrijvingen/{PAID}/betalingen", ["€ 15,00", "€ 0,00", "€ 5,00"]),
}


@pytest.mark.parametrize("width", [390, 1100])
@pytest.mark.parametrize("screen", sorted(SCREENS))
def test_the_three_figures_stand_once_on_one_line(world, screen, width):
    path, amounts = SCREENS[screen]
    page = _open(world, path, width)
    try:
        figures = page.evaluate(FIGURES)
        print("MEASURE figures", screen, width, figures)
        assert [f["label"] for f in figures] == LABELS, figures
        assert [f["value"] for f in figures] == amounts, figures
        assert page.locator("#bt-boven .kpi-strip").count() == 0
        assert "Ontvangen" not in page.locator("#bt-boven").inner_text().replace(
            "Nog te ontvangen", ""
        )
        assert [f["warning"] for f in figures] == [False, amounts[1] != "€ 0,00", True]
        if width >= 1100:
            assert len({f["top"] for f in figures}) == 1, f"not on one line: {figures}"
        assert max(f["right"] for f in figures) <= width, (
            f"a figure runs past the window: {figures}"
        )
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
        _print(page, f"{screen}-{width}.png")
    finally:
        page.close()
