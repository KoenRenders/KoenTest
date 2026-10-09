"""E2E: a request in the Assistent's panel always ends in words, and is sent once (#1667).

Koen on HDEV, 6 October 2026: his question stood twice in the conversation and
the panel kept saying "Raakje zoekt het voor je uit…". Measured before the fix,
in this browser:

- a turn the server answered WITHOUT words (no reply, no field) showed the
  user's own question and nothing under it, and emptied the field — so he sent
  it again: the two sends in the log were two sends, 14 seconds apart;
- a second Enter or a click on the send button WHILE a request runs sends
  nothing (htmx drops it): one send was already one turn;
- a request that ends with no answer at all — no connection, a server error —
  left the panel silent, and one that never ends kept the busy line forever:
  the form had no time limit.

What the server does with an answer that says nothing is measured in
`tests/integration/test_described_day_and_name_words_1667.py`; here the page.

Broken on purpose (6 October 2026), each red for its own reason: the failure
line taken out of `raakjeAfterAnswer` → the three tests without an answer; the
time limit taken off the form → the request of the time-limit test never ends.
"""

import json
import os
import sys

from playwright.sync_api import expect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.activities.test_activity_proposer import _remove, _seed, setup  # noqa: E402, F401
from tests_e2e.activities.test_new_activity_on_the_fiche import _page  # noqa: E402
from tests_e2e.schermen import htmx_stil  # noqa: E402

PANEL = ".raakje-panel"
SENTENCE = "Raakje kon geen antwoord geven — probeer het opnieuw. Je vraag staat er nog."
QUESTION = "Zet het op de derde laatste vrijdag van december."

_STATE = """() => { const busy = document.querySelector('.raakje-panel [role=status].htmx-indicator');
  const failed = [...document.querySelectorAll('.raakje-panel [data-panel-conversation] [data-turn-failed]')];
  return {busy: getComputedStyle(busy).opacity, failed: failed.map(e => e.innerText.trim().replace('🔈', '').trim()),
          field: document.querySelector('.raakje-panel [data-raakje-form] textarea').value,
          timeout: JSON.parse(document.querySelector('.raakje-panel [data-raakje-form]').getAttribute('hx-request') || '{}').timeout}; }"""


def _open(setup, activity_id: int, handler):  # noqa: F811
    page = _page(setup, f"/admin/activiteiten/{activity_id}?bewerken=1", 1440)
    page.asked = []

    def route(found):
        page.asked.append(found.request.post_data or "")
        handler(found)

    page.route("**/raakje/voorstel", route)
    page.locator("[data-raakje-trigger]").first.click()
    panel = page.locator(PANEL)
    panel.locator(f'[data-context-key="activity-edit:{activity_id}"]').wait_for(state="visible")
    htmx_stil(page)
    return page, panel


def _send(panel) -> None:
    field = panel.locator("[data-raakje-form] textarea")
    field.fill(QUESTION)
    field.press("Enter")


def _says_it_failed(page, panel) -> dict:
    expect(panel.locator("[data-panel-conversation] [data-turn-failed]")).to_have_count(1)
    page.wait_for_function(
        "getComputedStyle(document.querySelector('.raakje-panel [role=status].htmx-indicator')).opacity === '0'"
    )
    state = page.evaluate(_STATE)
    assert state["failed"] == [SENTENCE], state
    assert state["field"] == QUESTION, "the question did not stay in its field"
    return state


def test_without_a_connection_the_panel_says_so_and_keeps_the_question(setup):  # noqa: F811
    """Red on master: nothing in the conversation."""
    activity_id = _seed("Paneeltest geen verbinding")
    page, panel = _open(setup, activity_id, lambda found: found.abort())
    try:
        _send(panel)
        print("MEASURE no connection", _says_it_failed(page, panel))
        assert page.errors == []
    finally:
        page.close()
        _remove(activity_id)


def test_a_server_error_says_so_too(setup):  # noqa: F811
    activity_id = _seed("Paneeltest serverfout")
    page, panel = _open(
        setup, activity_id, lambda found: found.fulfill(status=500, body="Internal Server Error")
    )
    try:
        _send(panel)
        _says_it_failed(page, panel)
        assert "Internal Server Error" not in panel.inner_text()
    finally:
        page.close()
        _remove(activity_id)


def test_a_request_that_never_ends_stops_at_the_time_limit(setup):  # noqa: F811
    """Red on master: no limit on the form — the busy line stays for good. The
    real limit is minutes; the test shortens it on the form it found."""
    activity_id = _seed("Paneeltest tijdslimiet")
    held = []
    page, panel = _open(setup, activity_id, held.append)
    try:
        limit = page.evaluate(_STATE)["timeout"]
        assert limit and limit >= 180_000, f"no time limit above the server's own: {limit}"
        page.evaluate(
            "document.querySelector('.raakje-panel [data-raakje-form]').setAttribute('hx-request', '{\"timeout\": 400}')"
        )
        _send(panel)
        print("MEASURE time limit", _says_it_failed(page, panel), len(held))
        assert len(held) == 1
    finally:
        page.close()
        _remove(activity_id)


def test_a_second_enter_while_a_request_runs_sends_nothing(setup):  # noqa: F811
    """One send is one turn. Already true before #1667 (htmx drops the second);
    kept as a guard, because Koen's log showed the same request twice."""
    activity_id = _seed("Paneeltest dubbel verzenden")
    held = []
    page, panel = _open(setup, activity_id, held.append)
    try:
        _send(panel)
        page.wait_for_function(
            "getComputedStyle(document.querySelector('.raakje-panel [role=status].htmx-indicator')).opacity === '1'"
        )
        field = panel.locator("[data-raakje-form] textarea")
        field.press("Enter")
        panel.locator("[data-raakje-form] button[type=submit]").last.click()
        # No wait on the clock: a second request, sent or queued, would be held
        # like the first — the busy line below then never goes, and the count
        # at the end says two.
        held[0].fulfill(
            status=200,
            content_type="text/html",
            body="<div data-activity-turn><div data-raakje-answer>Zeg me waar het doorgaat.</div></div>",
        )
        # An answer with only a reply: it is the turn's text, and the busy line goes.
        expect(panel.locator("[data-activity-turn]")).to_have_count(1)
        expect(panel.locator("[data-activity-turn]")).to_contain_text("Zeg me waar het doorgaat.")
        page.wait_for_function(
            "getComputedStyle(document.querySelector('.raakje-panel [role=status].htmx-indicator')).opacity === '0'"
        )
        state = page.evaluate(_STATE)
        assert state["failed"] == [] and state["field"] == "", state
        assert len(page.asked) == 1 and len(held) == 1, f"sent {len(page.asked)} times"
        assert json.dumps(page.asked[0]).count("vraag=") == 1
    finally:
        page.close()
        _remove(activity_id)
