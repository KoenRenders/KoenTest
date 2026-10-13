"""E2E: the row link of Leden and Personen carries what the way back needs (#1940).

Both lists used to carry every field of the toolbar to the record — `?status=…&q=…
&jaar=&sort=…&per_page=…` with the empty ones — because the list holder included
the toolbar's form in the boosted link. The list Activiteiten (#1930) is leaner:
the row link names the list as it stands in one key, `terug`, and nothing else.

From a filtered, sorted, second page of each list the test opens a record and goes
back, and measures:

- the address of the record holds only the key `terug`, and it is not empty;
- the list stands as it was left: the same rows, the search, the sort, the
  segment, the page size and the range "26–30 van 30", and the address of the list
  carries the same state.

The test makes thirty households of its own, one person each, and removes them.
Red against master `3baecbd9`: the record's address holds the toolbar's fields.
"""

import os
import sys
import uuid
from datetime import date
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin, pagina_klaar  # noqa: E402

HOUSEHOLDS = 30
PER_PAGE = 25


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="module")
def households():
    """Thirty households with one active member each, whose last name carries one
    tag, so a search finds exactly them. Gone again afterwards."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import Member, MemberPerson, Person
    from app.domains.membership.api import Membership
    from app.soft_delete import soft_delete

    tag = uuid.uuid4().hex[:8]
    year = date.today().year
    db = SessionLocal()
    ids: list[int] = []
    try:
        for n in range(HOUSEHOLDS):
            member = Member()
            db.add(member)
            db.flush()
            person = Person(
                first_name="Proef",
                last_name=f"Rijlink-{tag}-{n:02d}",
                date_of_birth=date(1980, 1, 1),
                gender_code="F",
            )
            db.add(person)
            db.flush()
            db.add(MemberPerson(member_id=member.id, person_id=person.id, relation_type="HOOFDLID"))
            db.add(
                Membership(
                    member_id=member.id,
                    year=year,
                    is_active=True,
                    valid_from=date(year, 1, 1),
                    valid_to=date(year, 12, 31),
                )
            )
            ids.append(member.id)
        db.commit()
    finally:
        db.close()
    yield {"tag": tag, "year": year}
    db = SessionLocal()
    try:
        for member in db.query(Member).filter(Member.id.in_(ids)):
            for membership in db.query(Membership).filter(Membership.member_id == member.id):
                soft_delete(membership)
            for link in member.member_persons:
                soft_delete(link.person)
                soft_delete(link)
            soft_delete(member)
        db.commit()
    finally:
        db.close()


def _board(browser):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    login_als_admin(page, email, make_session_value(email))
    return page


def _keys(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


def _rows(page) -> list[str]:
    return page.locator("tbody tr[data-row] [data-row-link]").all_inner_texts()


def _open_and_come_back(page, list_path: str, record_path_part: str) -> None:
    """Open the first row of the list, check the record's address, go back."""
    page.locator("tbody tr[data-row] [data-row-link]").first.click()
    page.wait_for_function(
        "part => location.pathname.includes(part) && !location.pathname.endsWith('/lijst')",
        arg=record_path_part,
    )
    pagina_klaar(page)
    keys = _keys(page.url)
    print("MEASURE record address", page.url)
    assert list(keys) == ["terug"], f"the record's address holds more than the way back: {page.url}"
    assert all(keys["terug"]), "the way back is empty"
    page.locator("[data-way-back]").first.click()
    page.wait_for_function("path => location.pathname === path", arg=list_path)
    pagina_klaar(page)


def test_leden_row_link_carries_only_the_way_back_and_the_list_stands_as_left(browser, households):
    tag, year = households["tag"], households["year"]
    page = _board(browser)
    start = f"/admin/leden?q={tag}&jaar={year}&sort=-naam&per_page={PER_PAGE}&page=2"
    page.goto(start)
    pagina_klaar(page)
    before = _rows(page)
    assert len(before) == HOUSEHOLDS - PER_PAGE, f"the second page holds {before}"
    assert before == sorted(before, reverse=True), "the sort is not by name, Z to A"

    _open_and_come_back(page, "/admin/leden", "/admin/leden/gezin/")

    assert _rows(page) == before, "the list does not stand as it was left"
    state = _keys(page.url)
    assert state == {
        "q": [tag],
        "jaar": [str(year)],
        "sort": ["-naam"],
        "per_page": [str(PER_PAGE)],
        "page": ["2"],
    }, f"the list's address lost its state: {page.url}"
    expect(page.locator("input[type=search]")).to_have_value(tag)
    expect(page.locator("input[name=sort]")).to_have_value("-naam")
    expect(page.locator("[data-toolbar-count]")).to_contain_text(
        f"{PER_PAGE + 1}–{HOUSEHOLDS} van {HOUSEHOLDS}"
    )
    assert page.locator("input[name=status]:checked").get_attribute("value") == "actief"
    page.close()


def test_personen_row_link_carries_only_the_way_back_and_the_list_stands_as_left(
    browser, households
):
    tag = households["tag"]
    page = _board(browser)
    start = f"/admin/personen?zicht=in&q={tag}&per_page={PER_PAGE}&page=2"
    page.goto(start)
    pagina_klaar(page)
    before = _rows(page)
    assert len(before) == HOUSEHOLDS - PER_PAGE, f"the second page holds {before}"

    # A person's row leads to the household's record.
    _open_and_come_back(page, "/admin/personen", "/admin/leden/gezin/")

    assert _rows(page) == before, "the list does not stand as it was left"
    assert _keys(page.url) == {
        "zicht": ["in"],
        "q": [tag],
        "per_page": [str(PER_PAGE)],
        "page": ["2"],
    }, f"the list's address lost its state: {page.url}"
    expect(page.locator("input[type=search]")).to_have_value(tag)
    assert page.locator("input[name=zicht]:checked").get_attribute("value") == "in"
    expect(page.locator("[data-toolbar-count]")).to_contain_text(
        f"{PER_PAGE + 1}–{HOUSEHOLDS} van {HOUSEHOLDS}"
    )
    page.close()
