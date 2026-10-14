"""E2E: the Werkbank on the kit (#1931; end state §5.1, §5.2).

What only a browser shows:

- **the row's own "Afgehandeld"** ticks the task off in place: the row leaves
  the list, the count of Open and the figure in the title row follow, and the
  search field above the list keeps what was typed;
- **a refusal is read on the page**: a task that is no longer the viewer's to
  handle answers with a sentence on the list's message line, and the row
  stays; a task of another role opened by its address is "Taak niet gevonden";
- **the task's record**: Afhandelen opens the decision, "Afgehandeld" is the
  one save, and the page goes back to the list it was opened from;
- **nothing scrolls sideways** at 390 px, on the list and on the record, and
  on a phone a row's button is 44 px high.

The tasks are made for this file and removed again. Set `E2E_PRINTS` to a
folder to keep prints of the list and of the record (outside the repository).

Broken on purpose (13 October 2026, each put back):
- the row's `hx-target` made `#bestaat-niet` → the row stays on the list;
- `_refused` answering a plain 404 instead of the kit's refusal → nothing is
  swapped in and the message line stays empty;
- the redirect of the record's save made `/admin/werkbank` always → the wait
  for the list's own address times out.
"""

from __future__ import annotations

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

LIST = "/admin/werkbank"
ADMIN_ONLY = "werkbank-alleen-beheerder@example.com"
MARK = "E2E-1931"


def _db():
    import app.main  # noqa: F401  the whole app, so the domain facades import in order
    from app.database import SessionLocal

    return SessionLocal()


def _make(db, title: str, *, kind="kernel.job_gefaald", role="ADMIN") -> int:
    from app.domains.workflow.api import create_task

    task = create_task(
        db,
        kind=kind,
        title=f"{MARK} {title}",
        subject_type="kernel_job",
        subject_id="0",
        required_role=role,
    )
    db.flush()
    return task.id


@pytest.fixture(scope="module")
def world():
    """Four tasks and a board member with the role ADMIN only."""
    from app.domains.auth.api import User, UserRole, make_session_value
    from app.domains.workflow.models import WorkflowTask
    from tests.conftest import SEEDED_ADMIN_EMAIL

    db = _db()
    try:
        user = db.query(User).filter(User.email == ADMIN_ONLY).first()
        if user is None:
            user = User(email=ADMIN_ONLY, is_active=True)
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role_code="ADMIN"))
        user_id = user.id
        ids = {
            "row": _make(db, "vanuit de rij"),
            "stale": _make(db, "niet meer van mij"),
            "record": _make(db, "op het record"),
            "finance": _make(db, "van de penningmeester", role="FINANCE"),
        }
        db.commit()
    finally:
        db.close()
    admin = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield {
            "browser": browser,
            "ids": ids,
            "admin": make_session_value(admin),
            "admin_only": make_session_value(ADMIN_ONLY),
        }
        browser.close()
    db = _db()
    try:
        db.query(WorkflowTask).filter(WorkflowTask.title.like(f"{MARK}%")).delete(
            synchronize_session=False
        )
        db.query(UserRole).filter(UserRole.user_id == user_id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _page(world, session: str, width: int):
    page = world["browser"].new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    login_met_sessie(page, world[session])
    return page


def _print(page, name: str) -> None:
    folder = os.environ.get("E2E_PRINTS")
    if folder:
        os.makedirs(folder, exist_ok=True)
        page.screenshot(path=os.path.join(folder, name))


def _no_sideways_scroll(page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_afgehandeld_in_the_row_ticks_the_task_off_in_place(world):
    page = _page(world, "admin", 1440)
    try:
        page.goto(f"{LIST}?q={MARK}")
        pagina_klaar(page)
        row = page.locator(f'tr[data-task="{world["ids"]["row"]}"]')
        expect(row).to_be_visible()
        rows_before = page.locator("tr[data-task]").count()
        open_before = page.locator("#werkbank-filter-n-open").inner_text()
        figure_before = page.locator("[data-figure]").first.inner_text()
        _print(page, "werkbank-lijst-1440.png")

        row.locator("[data-row-action]").click()

        # the row is still on the list when its answer landed nowhere
        expect(row).to_have_count(0)
        assert page.locator("tr[data-task]").count() == rows_before - 1
        expect(page.locator("#werkbank-filter-n-open")).not_to_have_text(open_before)
        expect(page.locator("[data-figure]").first).not_to_have_text(figure_before)
        assert page.locator("input[type=search]").first.input_value() == MARK, (
            "the answer wiped the search field"
        )
        assert page.errors == []
    finally:
        page.close()


def test_a_refusal_is_read_on_the_page(world):
    """The viewer has the list open; the task then becomes another role's. Its
    row's button answers with a sentence, and the row stays where it is."""
    from app.domains.workflow.models import WorkflowTask

    page = _page(world, "admin_only", 1440)
    try:
        page.goto(f"{LIST}?q={MARK}")
        pagina_klaar(page)
        row = page.locator(f'tr[data-task="{world["ids"]["stale"]}"]')
        expect(row).to_be_visible()
        assert page.locator(f'tr[data-task="{world["ids"]["finance"]}"]').count() == 0, (
            "a task of another role is on the list"
        )
        db = _db()
        try:
            db.get(WorkflowTask, world["ids"]["stale"]).required_role = "FINANCE"
            db.commit()
        finally:
            db.close()

        row.locator("[data-row-action]").click()

        # the page says why
        expect(page.locator("#werkbank-melding")).to_contain_text("Taak niet gevonden")
        expect(row).to_be_visible()

        page.goto(f"{LIST}/taken/{world['ids']['finance']}")
        pagina_klaar(page)
        expect(page.locator("main")).to_contain_text("Taak niet gevonden")
        assert "penningmeester" not in page.locator("main").inner_text()
    finally:
        page.close()


def test_the_record_opens_its_decision_and_the_save_goes_back(world):
    page = _page(world, "admin", 1440)
    try:
        page.goto(f"{LIST}?q={MARK}&status=all")
        pagina_klaar(page)
        page.locator(f'tr[data-task="{world["ids"]["record"]}"] a[data-row-link]').click()
        pagina_klaar(page)
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        assert page.locator('[name="besluit"]').count() == 0
        _print(page, "werkbank-taak-open-1440.png")

        page.locator("[data-head-controls] a", has_text="Afhandelen").click()
        pagina_klaar(page)
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "edit")
        page.locator('[name="besluit"]').fill("Nagekeken, mag dicht")
        _print(page, "werkbank-taak-afhandelen-1440.png")
        page.locator("[data-action-bar] button", has_text="Afgehandeld").click()

        # the save goes back to the list the record was opened from, in its state
        page.wait_for_url(
            lambda url: url.split("?")[0].endswith(LIST) and "status=all" in url and MARK in url
        )
        pagina_klaar(page)
        row = page.locator(f'tr[data-task="{world["ids"]["record"]}"]')
        expect(row).to_contain_text("Afgehandeld")
        assert row.locator("[data-row-action]").count() == 0, "a done task still offers a button"

        row.locator("a[data-row-link]").click()
        pagina_klaar(page)
        expect(page.locator("#wb-besluit")).to_contain_text("Nagekeken, mag dicht")
        assert page.locator("[data-head-controls]").count() == 0, "a done task has a primary"
        _print(page, "werkbank-taak-afgehandeld-1440.png")
        assert page.errors == []
    finally:
        page.close()


def test_on_a_phone_nothing_scrolls_sideways_and_the_button_is_a_target(world):
    page = _page(world, "admin", 390)
    try:
        page.goto(f"{LIST}?q={MARK}&status=all")
        pagina_klaar(page)
        expect(page.locator("tr[data-task]").first).to_be_visible()
        assert _no_sideways_scroll(page)
        _print(page, "werkbank-lijst-390.png")
        buttons = page.locator("tr[data-task] [data-row-action]")
        assert buttons.count() >= 1, "no open task with a button — looked nowhere"
        assert buttons.first.bounding_box()["height"] >= 44, "the row's button is no touch target"

        page.goto(f"{LIST}/taken/{world['ids']['record']}")
        pagina_klaar(page)
        expect(page.locator("[data-record-head] h1")).to_contain_text(MARK)
        assert _no_sideways_scroll(page)
        _print(page, "werkbank-taak-390.png")
    finally:
        page.close()


#: #1990: Koen's longest title on HDEV, the title #1991 gives it, and two more.
LONG_TITLES = (
    "Refund a6574dd9-4c82-4b62-9ef2-fc75386676bf bevestigen (membership #77)",
    "Terugbetaling lidgeld #77 bevestigen",
    "Betaling van inschrijving #12 nakijken",
    "Overschrijving zonder mededeling toewijzen aan een gezin",
)
#: The kit's width of the Werkbank's actions column (the widest step), and of a name.
ACTIONS = 240
NAME = 380
COLUMNS = """() => {
  const frame = document.querySelector('[data-table-frame]');
  const heads = [...frame.querySelectorAll('thead th')].filter(th => th.checkVisibility());
  const box = el => el.getBoundingClientRect();
  return {
    frame_right: box(frame).right,
    name: box(heads[0]).width,
    actions: box(heads[heads.length - 1]).width,
    actions_right: box(heads[heads.length - 1]).right,
    lines: [...frame.querySelectorAll('tbody [data-row-link]')].map(a =>
      [a.textContent.trim(), Math.round(box(a).height / parseFloat(getComputedStyle(a).lineHeight))]),
    sideways: document.documentElement.scrollWidth > window.innerWidth,
  };
}"""


def test_the_title_takes_the_room_the_table_has_to_spare(world):
    """#1990: the title column takes what the table has to spare, so on a wide
    screen a title reads on one or two lines; the actions keep their width at
    the right edge; nothing scrolls sideways at 1 024, 1 440 or 1 920 px.

    Broken on purpose (14 October 2026, put back): the Werkbank's title column
    back at `"width": 252` → at 1 920 px the actions column is 666 px wide."""
    db = _db()
    try:
        ids = [_make(db, f"1990 {title}") for title in LONG_TITLES]
        db.commit()
    finally:
        db.close()
    try:
        for width in (1024, 1440, 1920):
            page = _page(world, "admin", width)
            page.goto(f"{LIST}?q={MARK} 1990")
            pagina_klaar(page)
            m = page.evaluate(COLUMNS)
            assert len(m["lines"]) == len(LONG_TITLES), m["lines"]
            assert not m["sideways"], f"{width} px scrolls sideways"
            assert abs(m["actions"] - ACTIONS) <= 1, f"{width} px: actions {m['actions']}"
            assert abs(m["actions_right"] - m["frame_right"]) <= 2, f"{width} px: {m}"
            if width == 1920:
                assert m["name"] >= NAME, f"1 920 px: the title column is {m['name']} px"
                assert all(n <= 2 for _t, n in m["lines"]), m["lines"]
            print("MEASURE 1990", width, round(m["name"]), m["lines"])
            if width >= 1440:
                _print(page, f"werkbank-1990-{width}.png")
            page.close()
    finally:
        db = _db()
        try:
            from app.domains.workflow.models import WorkflowTask

            db.query(WorkflowTask).filter(WorkflowTask.id.in_(ids)).delete(
                synchronize_session=False
            )
            db.commit()
        finally:
            db.close()
