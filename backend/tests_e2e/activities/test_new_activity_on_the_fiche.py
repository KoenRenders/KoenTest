"""E2E: "+ Nieuwe activiteit" opens the fiche itself, empty (#1649; CR-11 Q84).

In a real browser, because the page is what creates: the empty fiche in edit
mode with its bar, Raakje's proposal landing in its empty fields and its first
date row, the one "Opslaan" that makes the record and lands on its page, and
"Annuleren" that makes nothing.

The e2e backend has no model: the proposal is the REAL answer of the new
fiche's proposer route for a scripted model, put where htmx adds it (as
`test_activity_proposer.py` does for an existing activity).

Broken on purpose (6 October 2026): the form's target left at `#aa-detail` →
after Opslaan the head still reads "Nieuwe activiteit"; the blank date row not
rendered → the proposal's date finds no row with an empty base and the page
opens without a date field; the new context taken out of `assistant_context`
→ the panel says nothing about a new activity; `HX-Push-Url` dropped → the
address stays `/nieuw` after the save.
"""

import json
import os
import re
import sys
import uuid

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.activities.test_activity_proposer import (  # noqa: E402
    _answer,
    _answer_arrives,
    _db,
    _turn,
)
from tests_e2e.schermen import BASE, htmx_stil, login_met_sessie, pagina_klaar  # noqa: E402

NEW = "/admin/activiteiten/nieuw"
REQUEST = "Schaatsen met Draak in de schaatsbaan Herentals op zondag 8 november om 10 uur"


def _named(name: str) -> list[dict]:
    from app.domains.activities.api import Activity

    db = _db()
    try:
        return [
            {
                "id": a.id,
                "status": a.status.value,
                "location": a.location,
                "description": a.description,
                "dates": [
                    (d.start_date.isoformat(), d.start_time and d.start_time.strftime("%H:%M"))
                    for d in a.dates
                ],
            }
            for a in db.query(Activity).filter(Activity.name == name).all()
        ]
    finally:
        db.close()


def _total() -> int:
    from app.domains.activities.api import Activity

    db = _db()
    try:
        return db.query(Activity).execution_options(include_deleted=True).count()
    finally:
        db.close()


def _remove(name: str) -> None:
    from app.domains.activities import service
    from app.domains.activities.api import Activity

    db = _db()
    try:
        for a in db.query(Activity).filter(Activity.name == name).all():
            service.delete_activity(db, a.id, actor="e2e-1649@example.com")
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _page(setup, path: str, width: int):
    b, session = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.posts = []
    page.on("request", lambda r: page.posts.append(r.url) if r.method != "GET" else None)
    login_met_sessie(page, session)
    page.goto(path)
    pagina_klaar(page)
    return page


_SHAPE = """() => { const r = e => { if (!e) return null; const b = e.getBoundingClientRect(); return {x: Math.round(b.left), y: Math.round(b.top + scrollY), w: Math.round(b.width), bottom: Math.round(b.bottom)}; };
  const q = s => document.querySelector(s), bar = q('[data-action-bar]');
  return {mode: q('[data-form-flow]').dataset.mode, title: q('#aa-recordkop h1').innerText.trim(),
          badges: [...q('#aa-recordkop').querySelectorAll('h1 ~ * span, [data-record-badges] span')].map(e => e.innerText.trim()).filter(Boolean),
          name: r(q('#name')), name_value: q('#name').value, focused: document.activeElement && document.activeElement.id,
          dates: document.querySelectorAll('#aa-group-dates > [data-group-rows] > [data-group-row]').length,
          components: document.querySelectorAll('#aa-group-components > [data-group-rows] > [data-group-row]').length,
          bar: r(bar), window: innerHeight, delete: !!q('[data-form-delete]'), actions: !!q('[data-actions-trigger]'),
          tabs: !!q('[data-related-tabs]'), summary: !!q('[data-summary-column]'),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize("width", [1440, 390])
def test_the_new_fiche_takes_a_proposal_and_one_opslaan_makes_the_activity(setup, width):
    """Red on master: a start screen with five fields; the Assistent beside it
    knows nothing of a new activity."""
    _b, session = setup
    name = f"Schaatsen met Draak {uuid.uuid4().hex[:6]}"
    before = _total()
    page = _page(setup, NEW, width)
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        m = page.evaluate(_SHAPE)
        print("MEASURE new fiche", width, m)
        assert m["mode"] == "edit" and m["title"] == "Nieuwe activiteit"
        assert m["name_value"] == "" and m["dates"] == 1 and m["components"] == 0
        assert not m["delete"] and not m["actions"] and not m["tabs"] and not m["summary"]
        assert m["bar"]["bottom"] == m["window"], "the bar does not stand at the window's bottom"
        assert m["page"] == [width, width]
        assert m["focused"] == "name", "attention goes to the first field"
        expect(page.locator("#aa-recordkop")).to_contain_text("Concept")
        assert _total() == before, "opening the page made a record"

        # ── Raakje: the context of a new activity, and its proposal ──
        trigger = page.locator("[data-raakje-trigger]").first
        trigger.click()
        panel = page.locator(".raakje-panel")
        panel.locator('[data-context-key="activity-new"]').wait_for(state="visible")
        htmx_stil(page)
        assert panel.locator("[data-panel-context]").inner_text() == (
            "voorstel voor een nieuwe activiteit"
        )
        assert panel.locator("[data-raakje-form]").get_attribute("hx-post") == (
            f"{NEW}/raakje/voorstel"
        )
        html = _turn(
            session,
            "nieuw",
            REQUEST,
            _answer(
                name=name,
                location="schaatsbaan Herentals",
                description="Kom mee schaatsen. Achteraf is er warme chocomelk.",
                date={"start_date": "2026-11-08", "start_time": "10:00"},
                date_source="zondag 8 november",
            ),
            json.dumps({"unsupported": [{"sentence": 2, "reason": "staat niet in je vraag"}]}),
        )
        page.posts.clear()
        _answer_arrives(page, html)
        block = panel.locator("[data-form-proposal]")
        expect(block.locator("[data-proposal-summary]")).to_have_text(
            "5 velden ingevuld als voorstel"
        )
        assert page.locator('[data-field="name"]').get_attribute("data-proposed") is not None
        block.locator("[data-proposal-apply]").click()
        expect(block.locator("[data-proposal-result]")).to_have_text("5 velden ingevuld.")
        assert page.locator("#name").input_value() == name
        assert page.locator("#location").input_value() == "schaatsbaan Herentals"
        assert page.locator("#description").input_value() == "Kom mee schaatsen."
        rows = page.locator("#aa-group-dates > [data-group-rows] > [data-group-row]")
        expect(rows).to_have_count(1)  # the row the fiche opened with, no second one
        assert rows.locator('input[name$=".start_date"]').input_value() == "2026-11-08"
        assert rows.locator('input[name$=".start_time"]').input_value() == "10:00"
        assert page.posts == [], "Toepassen sent something"
        assert _total() == before and _named(name) == [], "nothing exists before Opslaan"

        # ── Opslaan makes it, and lands on its page ──
        if width < 768:
            panel.locator("[data-panel-close]").click()
        page.locator("[data-action-bar] [data-form-save]").click()
        page.wait_for_url(re.compile(r"/admin/activiteiten/\d+$"))
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        expect(page.locator("#aa-recordkop h1")).to_have_text(name)
        expect(page.locator("#toasts")).to_contain_text("Opgeslagen")
        expect(page.locator("[data-related-tabs]")).to_be_visible()
        made = _named(name)
        assert len(made) == 1 and _total() == before + 1
        assert made[0]["status"] == "draft"
        assert (made[0]["location"], made[0]["description"]) == (
            "schaatsbaan Herentals",
            "Kom mee schaatsen.",
        )
        assert made[0]["dates"] == [("2026-11-08", "10:00")]
        assert int(page.url.rsplit("/", 1)[1]) == made[0]["id"]
        # a reload shows the record, not a second empty form
        page.reload()
        pagina_klaar(page)
        expect(page.locator("#aa-recordkop h1")).to_have_text(name)
        # and the list shows it as a draft
        page.goto("/admin/activiteiten?scope=all")
        pagina_klaar(page)
        card = page.locator(f'a[href^="/admin/activiteiten/{made[0]["id"]}"]').first
        expect(card).to_be_visible()
        assert page.errors == []
    finally:
        page.close()
        _remove(name)


def test_annuleren_makes_nothing_and_asks_only_when_something_was_typed(setup):
    before = _total()
    page = _page(setup, NEW, 1440)
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        page.locator("[data-form-cancel]").click()
        page.wait_for_url(f"{BASE}/admin/activiteiten")
        assert _total() == before

        page.goto(NEW)
        pagina_klaar(page)
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        page.fill("#name", "Wordt niets")
        page.locator("[data-form-cancel]").click()
        dialog = page.locator("[data-dialog]")
        expect(dialog.locator("[data-dialog-title]")).to_have_text("Wijzigingen weggooien?")
        dialog.locator("[data-dialog-ok]").click()
        page.wait_for_url(f"{BASE}/admin/activiteiten")
        assert _total() == before and _named("Wordt niets") == []
        assert page.errors == []
    finally:
        page.close()


def test_an_empty_name_and_an_empty_date_are_refused_in_the_banner_and_nothing_exists(setup):
    before = _total()
    page = _page(setup, NEW, 390)
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        page.fill("#location", "Parochiezaal")
        page.locator("[data-action-bar] [data-form-save]").click()
        banner = page.locator("[data-save-refusal]")
        expect(banner).to_be_visible()
        expect(banner).to_contain_text("controleer 2 velden")
        expect(page.locator("#name")).to_have_attribute("aria-invalid", "true")
        expect(page.locator("#name")).to_be_focused()
        expect(page.locator("#location")).to_have_value("Parochiezaal")  # what was typed stays
        assert page.url == f"{BASE}{NEW}" and _total() == before
        assert page.errors == []
    finally:
        page.close()
