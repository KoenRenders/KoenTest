"""E2E: a second request to the Assistent on a fiche with unsaved values (#1659).

Koen on HDEV, 6 October 2026: a first proposal applied on a new activity, then
a second request for the day → "Deze pagina verlaten? Je wijzigingen zijn nog
niet opgeslagen." Measured before the fix: the request is an htmx POST from the
panel, there is no navigation; the form's guard stopped every non-GET request
from outside the form once the form held a change, and the panel stands
outside it. One typed letter was enough — Toepassen had nothing to do with it.
"Blijven" left the request unsent and the question in its field.

In a real browser, because it is the page that decides: the guard is a script,
and the fields that travel with the request are picked by a selector.

The e2e backend has no model, so the two halves are measured the way
`test_activity_proposer` does: the request really leaves the browser (the
backend's mock answers with a turn that failed), and the proposal for it is the
route's REAL answer, asked in this process with a scripted model for the very
fields the browser sent.

Broken on purpose (6 October 2026), each red for its own reason: the panel's
exception taken out of `record-form.js` → the dialog, and no request; the
form's values taken off the panel's edit context → the request carries the
question alone.

Found by this test while it was built: sent along as included fields
(`hx-include`), a date row without its required day stopped the request in
silence — htmx validates a field it includes. Koen's case exactly (hours
applied, the day still to come). The values therefore travel as computed
values (`raakRecordForm.valuesOf`), which nothing validates.
"""

import json
import os
import sys
import uuid
from datetime import date
from urllib.parse import parse_qsl

from playwright.sync_api import expect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import htmx_stil, pagina_klaar  # noqa: E402
from tests_e2e.test_activity_proposer import (  # noqa: E402
    _answer,
    _answer_arrives,
    _remove,
    _seed,
    _stored,
    _turn,
    setup,  # noqa: F401  the browser and the session
)
from tests_e2e.test_new_activity_on_the_fiche import NEW, _named, _page, _total  # noqa: E402

PANEL = ".raakje-panel"
ROWS = "#aa-group-dates > [data-group-rows] > [data-group-row]"
FIRST = "Schaatsen in de schaatsbaan van 10 tot 12 uur."
SECOND = "Het is op vrijdag 11 december."

_STATE = """() => { const store = window.Alpine.store('confirm');
  return {dialog: !!store.open, dirty: window.raakRecordForm.isDirty(),
          turns: document.querySelectorAll('.raakje-panel [data-activity-turn]').length}; }"""


def _watch(page) -> list:
    """Every request to the proposer, with the fields it carried."""
    sent: list = []

    def note(request) -> None:
        if request.method == "POST" and request.url.endswith("/raakje/voorstel"):
            sent.append(parse_qsl(request.post_data or "", keep_blank_values=True))

    page.on("request", note)
    return sent


def _open(page, key: str):
    page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
    page.locator("[data-raakje-trigger]").first.click()
    panel = page.locator(PANEL)
    panel.locator(f'[data-context-key="{key}"]').wait_for(state="visible")
    htmx_stil(page)
    return panel


def _send(page, panel, text: str) -> None:
    """With the send button, as Koen did."""
    panel.locator("[data-raakje-form] textarea").fill(text)
    panel.locator("[data-raakje-form] button[type=submit]").last.click()


def _as_form(pairs: list) -> dict:
    form: dict = {}
    for name, value in pairs:
        if name not in ("vraag", "historie"):
            form.setdefault(name, []).append(value)
    return form


def test_on_a_new_activity_the_second_request_asks_nothing_and_the_day_lands_on_the_row_with_the_hours(
    setup,  # noqa: F811
):
    """Red on master: the dialog "Deze pagina verlaten?", and no request."""
    _b, session = setup
    name = f"Schaatsen {uuid.uuid4().hex[:6]}"
    before = _total()
    page = _page(setup, NEW, 1440)
    sent = _watch(page)
    try:
        panel = _open(page, "activity-new")

        # ── first turn: name, place, description and the hours — no day ──
        first = _turn(
            session,
            "nieuw",
            FIRST,
            _answer(
                name=name,
                location="schaatsbaan",
                description="Kom mee schaatsen in de schaatsbaan.",
                date={"start_time": "10:00", "end_time": "12:00"},
            ),
        )
        _answer_arrives(page, first)
        block = panel.locator("[data-form-proposal]").last
        block.locator("[data-proposal-apply]").click()
        expect(block.locator("[data-proposal-result]")).to_have_text("5 velden ingevuld.")
        row = page.locator(ROWS)
        expect(row).to_have_count(1)
        assert row.locator('input[name$=".start_time"]').input_value() == "10:00"
        assert row.locator('input[name$=".start_date"]').input_value() == ""
        assert page.evaluate(_STATE)["dirty"], "the applied values are unsaved changes"

        # ── second turn, sent from the browser ──
        turns = page.evaluate(_STATE)["turns"]
        _send(page, panel, SECOND)
        page.wait_for_function(
            f"document.querySelectorAll('.raakje-panel [data-activity-turn]').length > {turns}"
        )
        state = page.evaluate(_STATE)
        print("MEASURE second request, new activity", state, len(sent))
        assert not state["dialog"], 'a request to the Assistent asked "Deze pagina verlaten?"'
        assert len(sent) == 1, "the request did not leave the browser exactly once"
        form = _as_form(sent[0])
        key = form["d_order"][0]
        assert dict(sent[0])["vraag"] == SECOND
        assert form["name"] == [name] and form["location"] == ["schaatsbaan"]
        assert form["description"] == ["Kom mee schaatsen in de schaatsbaan."]
        assert form[f"d.{key}.start_time"] == ["10:00"] and form[f"d.{key}.end_time"] == ["12:00"]
        assert form[f"d.{key}.start_date"] == [""]
        assert not [n for n in form if n.startswith(("c.", "p.", "o.")) or n == "csrf_token"], (
            "more than the fields a proposal reads travelled along"
        )
        # nothing applied earlier is lost
        assert page.locator("#name").input_value() == name
        assert row.locator('input[name$=".end_time"]').input_value() == "12:00"

        # ── the proposal for exactly what the browser sent ──
        second = _turn(
            session,
            "nieuw",
            SECOND,
            _answer(
                name=name,
                location="schaatsbaan",
                date={"start_date": "2026-12-11", "start_time": "10:00", "end_time": "12:00"},
                date_source="vrijdag 11 december",
            ),
            form=form,
        )
        _answer_arrives(page, second)
        block = panel.locator("[data-form-proposal]").last
        expect(block.locator("[data-proposal-summary]")).to_have_text(
            "1 veld ingevuld als voorstel"
        )
        block.locator("[data-proposal-apply]").click()
        expect(block.locator("[data-proposal-result]")).to_have_text("1 veld ingevuld.")
        expect(row).to_have_count(1)  # the day came on the row that carries the hours
        assert row.locator('input[name$=".start_date"]').input_value() == "2026-12-11"
        assert row.locator('input[name$=".start_time"]').input_value() == "10:00"
        assert row.locator('input[name$=".end_time"]').input_value() == "12:00"
        assert page.locator("#name").input_value() == name
        assert _total() == before and _named(name) == [], "nothing exists before Opslaan"
        assert page.errors == []
    finally:
        page.close()


def test_on_an_existing_activity_the_request_goes_and_a_menu_link_still_asks(setup):  # noqa: F811
    """Red on master: the dialog on the request. The guard itself did not go: a
    link away from the form with unsaved values asks, before and after."""
    activity_id = _seed("Voorsteltest tweede vraag", dates=[(date(2026, 11, 14), None)])
    page = _page(setup, f"/admin/activiteiten/{activity_id}?bewerken=1", 1440)
    sent = _watch(page)
    try:
        panel = _open(page, f"activity-edit:{activity_id}")
        page.fill("#name", "Getypt en niet opgeslagen")
        _send(page, panel, "Stel een betere naam voor.")
        panel.locator("[data-activity-turn]").wait_for()
        state = page.evaluate(_STATE)
        print("MEASURE request on a changed form, existing activity", state, len(sent))
        assert not state["dialog"] and len(sent) == 1
        assert _as_form(sent[0])["name"] == ["Getypt en niet opgeslagen"]
        assert page.locator("#name").input_value() == "Getypt en niet opgeslagen"
        assert state["dirty"], "the request made the form forget its changes"

        # a way out still asks
        page.locator("[data-record-head] a").first.click()
        dialog = page.locator("[data-dialog]")
        expect(dialog.locator("[data-dialog-title]")).to_have_text("Deze pagina verlaten?")
        dialog.locator("[data-dialog-cancel]").click()
        assert "bewerken=1" in page.url
        assert page.locator("#name").input_value() == "Getypt en niet opgeslagen"
        assert _stored(activity_id)["name"] == "Voorsteltest tweede vraag"
        assert page.errors == []
    finally:
        page.close()
        _remove(activity_id)


def test_a_first_request_on_an_unchanged_form_sends_what_is_stored(setup):  # noqa: F811
    """The fields that travel on a form nobody touched are the stored record:
    the first request behaves as it did (the server side of this is
    `test_a_first_request_on_a_form_nobody_changed_is_the_request_of_before`)."""
    activity_id = _seed("Voorsteltest eerste vraag", dates=[(date(2026, 11, 14), None)])
    page = _page(setup, f"/admin/activiteiten/{activity_id}?bewerken=1", 1440)
    sent = _watch(page)
    try:
        panel = _open(page, f"activity-edit:{activity_id}")
        _send(page, panel, "Schrijf een omschrijving.")
        panel.locator("[data-activity-turn]").wait_for()
        pagina_klaar(page)
        form = _as_form(sent[0])
        key = form["d_order"][0]
        print("MEASURE first request, unchanged form", json.dumps(form))
        assert len(sent) == 1 and len(form["d_order"]) == 1
        assert (form["name"], form["location"], form["description"]) == (
            ["Voorsteltest eerste vraag"],
            [""],
            [""],
        )
        assert form[f"d.{key}.start_date"] == ["2026-11-14"] and form[f"d.{key}.start_time"] == [""]
        assert not page.evaluate(_STATE)["dirty"]
    finally:
        page.close()
        _remove(activity_id)
