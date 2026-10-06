"""E2E: Raakje's proposal for an activity lands in the fiche (#1604).

In a real browser, because it is the page that takes a proposal: the panel
beside a fiche in edit mode is the proposer, the offered fields are marked, a
group without a row carries the mark itself, Toepassen fills the form and adds
the one date row, sends nothing, and the fiche's one "Opslaan" stores it.

The e2e backend has no model. The turn is therefore the REAL answer of the
route — asked in this process with a scripted model, the same way the
integration tests do — put into the panel's conversation where htmx would add
it. One test does ask through the browser, with the backend's mock model: it
proves the panel posts to the proposer and keeps a question that got no answer.

The two extensions of `form-proposal.js` are measured on the kit page (§13f):
a field that names a repeating group, and a value in parts with a tick.

Broken on purpose (5 October 2026), each red for its own reason: the edit
context taken out of `assistant_context` → the panel keeps the question
context and the turn test finds no proposer; `make` never passed in `apply` →
no date row is added and two fields are named as skipped; the first-row lookup
replaced by the last row → the second date is rewritten; the tick ignored in
`valueOf` → the ticked sentence stays out; the group's mark not set in `offer`
→ an empty group shows no proposal.
"""

import json
import os
import sys
from datetime import date, time

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_met_sessie, pagina_klaar  # noqa: E402

REQUEST = "Een herfstwandeling met soep op zaterdag 14 november om 14 uur in de parochiezaal."
TEXT = "Kom mee wandelen door de herfst. Achteraf is er soep in de parochiezaal."
MARKED = "Er is een tombola."
DATES = "#aa-group-dates"
ROWS = f"{DATES} > [data-group-rows] > [data-group-row]"


def _db():
    import app.main  # noqa: F401  the whole app, so the domain facades import in order
    from app.database import SessionLocal

    return SessionLocal()


def _seed(name: str, dates=()) -> int:
    from app.domains.activities.api import Activity, ActivityDate

    db = _db()
    try:
        activity = Activity(name=name)
        db.add(activity)
        db.flush()
        for day, begins in dates:
            db.add(ActivityDate(activity_id=activity.id, start_date=day, start_time=begins))
        db.commit()
        return activity.id
    finally:
        db.close()


def _remove(activity_id: int) -> None:
    from app.domains.activities import service

    db = _db()
    try:
        service.delete_activity(db, activity_id, actor="e2e-1604@example.com")
    finally:
        db.close()


def _stored(activity_id: int) -> dict:
    from app.domains.activities.api import Activity
    from app.domains.activities.models import ActivityHistory

    db = _db()
    try:
        a = db.query(Activity).filter(Activity.id == activity_id).one()
        return {
            "name": a.name,
            "location": a.location,
            "description": a.description,
            "dates": sorted((d.start_date, d.start_time, d.end_time) for d in a.dates),
            "history": db.query(ActivityHistory).filter_by(activity_id=activity_id).count(),
        }
    finally:
        db.close()


class _Scripted:
    name = "mock"
    model = "scripted"

    def __init__(self, *answers):
        self.answers = list(answers)

    def complete(self, messages, tools=None, tool_choice=None):
        from app.domains.chatbot.providers.base import AssistantMessage

        return AssistantMessage(
            content=self.answers.pop(0) if self.answers else json.dumps({"unsupported": []})
        )


def _turn(session: str, activity_id: int, request: str, *answers: str) -> str:
    """The proposer route's own answer for a scripted model, as HTML."""
    from fastapi.testclient import TestClient

    import app.main as main
    from app.config import settings
    from app.domains.auth.api import SESSION_COOKIE, csrf_token_for
    from app.domains.chatbot import api as chatbot

    before = chatbot.get_provider, settings.admin_chat_enabled
    provider = _Scripted(*answers)
    chatbot.get_provider = lambda model="": provider
    settings.admin_chat_enabled = True
    try:
        client = TestClient(main.app)
        client.cookies.set(SESSION_COOKIE, session)
        answer = client.post(
            f"/admin/activiteiten/{activity_id}/raakje/voorstel",
            headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
            data={"vraag": request},
        )
    finally:
        chatbot.get_provider, settings.admin_chat_enabled = before
    assert answer.status_code == 200, (answer.status_code, answer.text[:300])
    assert "data-form-proposal" in answer.text, answer.text[:600]
    return answer.text


def _answer(**fields) -> str:
    return json.dumps({"reply": "Voorstel klaar.", **fields}, ensure_ascii=False)


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _page(setup, path: str, width: int = 1440):
    b, session = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.requests = []
    page.on("request", lambda req: page.requests.append(req.url) if req.method != "GET" else None)
    login_met_sessie(page, session)
    page.goto(path)
    pagina_klaar(page)
    return page


def _open_panel(page, key: str) -> None:
    trigger = page.locator("[data-raakje-trigger]").first
    trigger.wait_for(state="visible")
    if page.locator(".raakje-panel").is_hidden():
        trigger.click()
    page.locator(f'.raakje-panel [data-context-key="{key}"]').wait_for(state="visible")
    htmx_stil(page)


def _answer_arrives(page, html: str) -> None:
    """Add the turn under the conversation, as htmx does with the route's answer
    (`hx-swap="beforeend"`), and let the page settle on it."""
    page.evaluate(
        """(html) => { const talk = document.querySelector('.raakje-panel [data-panel-conversation]');
             talk.insertAdjacentHTML('beforeend', html); window.htmx.process(talk);
             window.raakFormProposal.scan(); }""",
        html,
    )


_FICHE = """() => { const f = n => document.querySelector(`[data-field="${n}"]`);
  const group = document.querySelector('#aa-group-dates');
  const rows = [...group.querySelectorAll(':scope > [data-group-rows] > [data-group-row]')];
  const val = (row, n) => { const c = row.querySelector(`[data-field$=".${n}"] input`); return c ? c.value : null; };
  const state = n => ({value: f(n).querySelector('input:not([type=hidden]), textarea').value,
                       proposed: f(n).hasAttribute('data-proposed'), applied: f(n).hasAttribute('data-proposal-applied')});
  const note = [...group.children].find(e => e.hasAttribute('data-proposal-note'));
  return {name: state('name'), location: state('location'), description: state('description'),
          group: {proposed: group.hasAttribute('data-proposed'), note: note ? note.innerText : ''},
          rows: rows.map(r => ({date: val(r, 'start_date'), from: val(r, 'start_time'), until: val(r, 'end_time'),
                                marked: r.querySelectorAll('[data-proposal-applied]').length})),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize("width", [1440, 390])
def test_a_proposal_fills_the_fiche_adds_one_date_row_and_only_opslaan_writes(setup, width):
    """Red on master: the panel beside a fiche in edit mode asks questions, and
    there is no proposer to answer."""
    _b, session = setup
    activity_id = _seed(f"Voorsteltest Raakje {width}")
    try:
        before = _stored(activity_id)
        page = _page(setup, f"/admin/activiteiten/{activity_id}?bewerken=1", width)
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        _open_panel(page, f"activity-edit:{activity_id}")
        panel = page.locator(".raakje-panel")
        assert panel.locator("[data-panel-context]").inner_text() == (
            f"voorstel voor Voorsteltest Raakje {width}"
        )
        assert panel.locator("[data-raakje-form]").get_attribute("hx-post") == (
            f"/admin/activiteiten/{activity_id}/raakje/voorstel"
        )

        html = _turn(
            session,
            activity_id,
            REQUEST,
            _answer(
                name="Herfstwandeling met soep",
                location="Parochiezaal",
                description=f"{TEXT} {MARKED}",
                date={"start_date": "2026-11-14", "start_time": "14:00"},
                date_source="zaterdag 14 november om 14 uur",
            ),
            json.dumps({"unsupported": [{"sentence": 3, "reason": "staat niet in de vraag"}]}),
        )
        _answer_arrives(page, html)

        block = panel.locator("[data-form-proposal]")
        expect(block.locator("[data-proposal-summary]")).to_have_text(
            "5 velden ingevuld als voorstel"
        )
        assert block.locator("[data-proposal-labels]").inner_text() == (
            "Naam · Locatie · Omschrijving · Datum · Van"
        )
        offered = page.evaluate(_FICHE)
        print("MEASURE proposal offered", width, offered)
        assert offered["name"] == {
            "value": f"Voorsteltest Raakje {width}",
            "proposed": True,
            "applied": False,
        }
        assert offered["location"]["proposed"] and offered["description"]["proposed"]
        assert offered["rows"] == [], "offered adds no row"
        assert offered["group"] == {"proposed": True, "note": "Voorstel · nog niet toegepast"}
        assert page.evaluate("window.raakRecordForm.isDirty()") is False, "offered changes nothing"
        assert not block.locator('input[name="keep"]').is_checked(), "left out by default"

        block.locator("[data-proposal-apply]").click()
        expect(block.locator("[data-proposal-result]")).to_have_text("5 velden ingevuld.")
        applied = page.evaluate(_FICHE)
        print("MEASURE proposal applied", width, applied)
        assert applied["name"]["value"] == "Herfstwandeling met soep" and applied["name"]["applied"]
        assert applied["location"]["value"] == "Parochiezaal"
        assert applied["description"]["value"] == TEXT, "the marked sentence stayed out"
        assert applied["rows"] == [
            {"date": "2026-11-14", "from": "14:00", "until": "", "marked": 2}
        ], "one row, with the day and the hour"
        assert applied["group"] == {"proposed": False, "note": ""}
        assert applied["page"] == [width, width], "the page widened"
        assert page.evaluate("window.raakRecordForm.isDirty()") is True
        assert page.requests == [], "Toepassen sent nothing"
        assert _stored(activity_id) == before, "not in the database"

        if width < 768:
            page.locator(".raakje-panel [data-panel-close]").click()
        page.locator("[data-action-bar] [data-form-save]").click()
        page.wait_for_selector('[data-form-flow][data-mode="read"]')
        after = _stored(activity_id)
        assert (after["name"], after["location"], after["description"]) == (
            "Herfstwandeling met soep",
            "Parochiezaal",
            TEXT,
        )
        assert after["dates"] == [(date(2026, 11, 14), time(14, 0), None)]
        assert after["history"] == before["history"] + 1, "one change, written by Opslaan"
        assert page.errors == []
        page.close()
    finally:
        _remove(activity_id)


def test_the_first_date_row_is_moved_and_the_second_is_untouched(setup):
    """Two dates. The proposal names the group, so it means the row the fiche
    shows first; the other row holds what it held, mark and all."""
    _b, session = setup
    activity_id = _seed(
        "Voorsteltest Raakje twee datums",
        dates=((date(2026, 11, 28), time(20, 0)), (date(2026, 11, 14), time(14, 0))),
    )
    try:
        page = _page(setup, f"/admin/activiteiten/{activity_id}?bewerken=1")
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        _open_panel(page, f"activity-edit:{activity_id}")
        html = _turn(
            session,
            activity_id,
            "Verplaats naar zaterdag 21 november van 10 tot 12 uur.",
            _answer(
                date={"start_date": "2026-11-21", "start_time": "10:00", "end_time": "12:00"},
                date_source="zaterdag 21 november van 10 tot 12 uur",
            ),
        )
        _answer_arrives(page, html)
        offered = page.evaluate(_FICHE)
        assert [r["date"] for r in offered["rows"]] == ["2026-11-14", "2026-11-28"]
        assert not offered["group"]["proposed"], "a group with a row marks its fields, not itself"
        assert page.locator(f"{ROWS}").nth(0).locator("[data-proposed]").count() == 3
        assert page.locator(f"{ROWS}").nth(1).locator("[data-proposed]").count() == 0

        page.locator(".raakje-panel [data-proposal-apply]").click()
        expect(page.locator(".raakje-panel [data-proposal-result]")).to_have_text(
            "3 velden ingevuld."
        )
        applied = page.evaluate(_FICHE)
        print("MEASURE second row", applied["rows"])
        assert applied["rows"] == [
            {"date": "2026-11-21", "from": "10:00", "until": "12:00", "marked": 3},
            {"date": "2026-11-28", "from": "20:00", "until": "", "marked": 0},
        ]
        assert page.requests == [] and page.errors == []
        page.close()
    finally:
        _remove(activity_id)


def test_the_panel_swaps_to_the_proposer_on_bewerken_and_keeps_an_unanswered_question(setup):
    """Reading, the panel answers questions about the activity; in edit mode it
    proposes. Asked through the browser, the backend's mock model gives no JSON:
    the turn says so and the question stays in the field."""
    activity_id = _seed("Voorsteltest Raakje paneel")
    try:
        page = _page(setup, f"/admin/activiteiten/{activity_id}")
        _open_panel(page, f"activity:{activity_id}")
        form = page.locator(".raakje-panel [data-raakje-form]")
        assert form.get_attribute("hx-post") == f"/admin/rapporten/raakje/activiteit/{activity_id}"

        page.goto(f"/admin/activiteiten/{activity_id}?bewerken=1")
        pagina_klaar(page)
        _open_panel(page, f"activity-edit:{activity_id}")
        form = page.locator(".raakje-panel [data-raakje-form]")
        assert form.get_attribute("hx-post") == f"/admin/activiteiten/{activity_id}/raakje/voorstel"

        field = form.locator("textarea")
        field.fill("Schrijf een omschrijving.")
        field.press("Enter")
        turn = page.locator(".raakje-panel [data-activity-turn]")
        turn.wait_for()
        assert turn.get_attribute("data-turn-failed") is not None
        expect(field).to_have_value("Schrijf een omschrijving.")
        assert any(url.endswith("/raakje/voorstel") for url in page.requests)
        assert page.errors == []
        page.close()
    finally:
        _remove(activity_id)


# ── The two extensions of the mechanism, on the kit page ─────────────────────

KIT = "[data-kit-proposal-row]"
_KIT = """() => { const kit = document.querySelector('[data-kit-proposal-row]'), group = kit.querySelector('[data-repeating-group="kit_pd_order"]');
  const rows = [...group.querySelectorAll(':scope > [data-group-rows] > [data-group-row]')];
  const note = [...group.children].find(e => e.hasAttribute('data-proposal-note'));
  return {story: kit.querySelector('#kit-prop-story').value,
          group: {proposed: group.hasAttribute('data-proposed'), note: note ? note.innerText : ''},
          rows: rows.map(r => [...r.querySelectorAll('input:not([type=hidden])')].map(c => c.value)),
          first: [...document.querySelectorAll('[data-kit-proposal] [data-form-proposal]')].map(b => b.dataset.proposalState)}; }"""


def _kit(setup):
    page = _page(setup, "/admin/design-system")
    page.locator(KIT).scroll_into_view_if_needed()
    return page


def test_on_the_kit_a_group_without_a_row_carries_the_mark_and_toepassen_adds_one(setup):
    page = _kit(setup)
    page.locator(f"{KIT} [data-kit-proposal-show]").click()
    block = page.locator(f"{KIT} [data-form-proposal]")
    block.wait_for()
    offered = page.evaluate(_KIT)
    print("MEASURE kit group offered", offered)
    assert offered["rows"] == [] and offered["story"] == ""
    assert offered["group"] == {"proposed": True, "note": "Voorstel · nog niet toegepast"}
    assert offered["first"] == ["closed"], "a newer proposal replaces the one that was open"

    block.locator("[data-proposal-apply]").click()
    applied = page.evaluate(_KIT)
    assert applied["rows"] == [["2031-06-14", "14:00"]]
    assert applied["story"] == "Kom mee wandelen.", "the marked sentence stays out by default"
    assert applied["group"] == {"proposed": False, "note": ""}
    assert block.locator("[data-proposal-result]").inner_text() == "3 velden ingevuld."
    assert page.requests == [] and page.errors == []
    page.close()


def test_on_the_kit_a_ticked_sentence_is_kept(setup):
    page = _kit(setup)
    page.locator(f"{KIT} [data-kit-proposal-show]").click()
    block = page.locator(f"{KIT} [data-form-proposal]")
    block.locator('input[name="keep"]').check()
    block.locator("[data-proposal-apply]").click()
    assert page.evaluate(_KIT)["story"] == "Kom mee wandelen. Er is een tombola."
    assert page.requests == []
    page.close()


def test_on_the_kit_a_first_row_changed_meanwhile_is_skipped_and_no_other_row_is_filled(setup):
    """Two rows added in the page (keys the server never saw), a day typed in the
    first: its date is left alone and named, its hour — still empty — is filled,
    and the second row gets nothing."""
    page = _kit(setup)
    add = page.locator(f"{KIT} [data-group-add]")
    add.click()
    add.click()
    page.locator(f"{KIT} [data-group-row]").nth(0).locator('input[type="date"]').fill("2031-07-01")
    page.locator(f"{KIT} [data-kit-proposal-show]").click()
    block = page.locator(f"{KIT} [data-form-proposal]")
    block.locator("[data-proposal-apply]").click()
    state = page.evaluate(_KIT)
    print("MEASURE kit rows", state["rows"])
    assert state["rows"] == [["2031-07-01", "14:00"], ["", ""]]
    assert block.locator("[data-proposal-result]").inner_text() == (
        "2 velden ingevuld. 1 veld overgeslagen: intussen gewijzigd (Datum)."
    )
    page.close()
