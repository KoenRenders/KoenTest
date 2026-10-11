"""E2E: Leden in the browser (#1899, CR-11 roll-out slice 1; end state §5.1).

- the list opens on **Actief**, in the admin shell with "Leden" marked in the
  menu, on the kit's table: three columns, no actions column, at 1440 and at
  390 px no wider than the window;
- the segment **Te vernieuwen** and the search cut the list without replacing
  the search field; the count in the toolbar and the count on the segment
  follow, and say what the list shows;
- a row is the way in to the household's record.

The test makes two households of its own — one that is to renew by the
campaign's rule (a member in the reference year only), one that covers the
target year too — and removes them afterwards.

On master the list is a column of cards with chips; there is no
`tr[data-household]` and no segment "vernieuwen".
"""

import os
import sys
import uuid
from datetime import date

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, login_als_admin, pagina_klaar  # noqa: E402

PAGE = "/admin/leden"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _board(browser, width: int, height: int):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    login_als_admin(page, email, make_session_value(email))
    return page


@pytest.fixture(scope="module")
def households():
    """Two households whose main member carries one tag in the last name: `renew`
    was a member in the campaign's reference year only, `renewed` covers the
    target year as well. Gone again afterwards."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import Member, MemberPerson, Person
    from app.domains.membership.api import Membership, renewal_years
    from app.soft_delete import soft_delete

    tag = uuid.uuid4().hex[:8]
    reference, target = renewal_years()
    db = SessionLocal()
    made: dict = {"tag": tag}
    try:
        for key, years in (("renew", [reference]), ("renewed", [reference, target])):
            member = Member()
            db.add(member)
            db.flush()
            person = Person(
                first_name="Proef",
                last_name=f"Lijst-{tag}-{key}",
                date_of_birth=date(1980, 1, 1),
                gender_code="F",
            )
            db.add(person)
            db.flush()
            db.add(MemberPerson(member_id=member.id, person_id=person.id, relation_type="HOOFDLID"))
            for year in years:
                db.add(
                    Membership(
                        member_id=member.id,
                        year=year,
                        is_active=True,
                        valid_from=date(year, 1, 1),
                        valid_to=date(year, 12, 31),
                    )
                )
            made[key] = member.id
        db.commit()
    finally:
        db.close()
    yield made
    db = SessionLocal()
    try:
        for key in ("renew", "renewed"):
            member = db.query(Member).filter(Member.id == made[key]).first()
            if member is None:
                continue
            for membership in db.query(Membership).filter(Membership.member_id == member.id):
                soft_delete(membership)
            for link in member.member_persons:
                soft_delete(link.person)
                soft_delete(link)
            soft_delete(member)
        db.commit()
    finally:
        db.close()


SHAPE = """() => { const q = s => document.querySelector(s), all = s => [...document.querySelectorAll(s)];
  const first = q('tr[data-row]');
  return {title: q('h1').innerText.trim(),
          marked: all('nav a[aria-current="page"]').map(a => a.getAttribute('href')),
          status: (q('input[name=status]:checked') || {}).value,
          segments: all('input[name=status]').map(i => i.value),
          figures: all('[data-figure-label]').map(e => e.innerText.trim().replace(/ \\d{4}$/, '')),
          heads: all('thead th').filter(th => th.checkVisibility()).map(th => th.innerText.trim()),
          rows: all('tr[data-row]').length,
          row_actions: all('tr[data-row] [data-row-menu-trigger], tr[data-row] button').length,
          first_row_y: first ? Math.round(first.getBoundingClientRect().top + scrollY) : null,
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize(("width", "height"), [(1440, 900), (390, 844)])
def test_the_list_opens_on_actief_on_the_kit_table(browser, households, width, height):
    page = _board(browser, width, height)
    page.goto(PAGE)
    pagina_klaar(page)
    shape = page.evaluate(SHAPE)
    print("MEASURE leden", width, shape)
    assert shape["title"] == "Leden" and shape["status"] == "actief", shape
    assert shape["segments"] == ["actief", "vernieuwen", "opgezegd"], "no Alle, three segments"
    assert shape["figures"] == ["Actieve gezinnen", "Actieve personen", "Te vernieuwen"], shape
    assert PAGE in shape["marked"], "Leden is not the marked menu item"
    assert shape["rows"] >= 1 and shape["row_actions"] == 0, "a row carries an action"
    if width >= 1440:
        assert shape["heads"] == ["Gezin", "Personen", "Lidmaatschap"], shape["heads"]
    assert shape["page"][0] == shape["page"][1], "wider than the window"
    expect(
        page.locator('#leden-filter [data-more-menu] a[href="/admin/leden-import"]')
    ).to_have_count(1)
    expect(page.get_by_role("link", name="+ Nieuw lid")).to_be_visible()
    page.close()


def test_te_vernieuwen_and_the_search_cut_the_list(browser, households):
    page = _board(browser, 1440, 900)
    page.goto(PAGE)
    pagina_klaar(page)
    with htmx_afgerond(page):
        page.locator("#leden-filter label", has_text="Te vernieuwen").click()
    renew = page.locator(f'tr[data-household="{households["renew"]}"]')
    search = page.locator('#leden-filter input[type="search"]')
    with htmx_afgerond(page):
        search.press_sequentially(households["tag"], delay=30)
    # The search cuts: of the two households with the tag, one is to renew.
    expect(page.locator("tr[data-row]")).to_have_count(1)
    expect(renew).to_be_visible()
    expect(page.locator(f'tr[data-household="{households["renewed"]}"]')).to_have_count(0)
    assert search.input_value() == households["tag"], "the search field was replaced"
    expect(page.locator("#leden-filter-count")).to_have_text("1–1 van 1")
    expect(page.locator("#leden-filter-n-vernieuwen")).to_have_text("(1)")
    assert "status=vernieuwen" in page.url and households["tag"] in page.url, page.url

    # A row is the way in to the household's record.
    renew.locator("a[data-row-link]").click()
    page.wait_for_url(f"**/admin/leden/gezin/{households['renew']}**")
    page.close()
