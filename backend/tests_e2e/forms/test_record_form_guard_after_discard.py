"""E2E: after "Weggooien" the chosen action happens, and the guard guards again (#1660).

Measured on master beside #1659 (6 October 2026), on an activity in edit mode
with a typed, unsaved name:

- a FORM outside the record form (then: the Assistent's panel): "Weggooien"
  repeated a *click* on the form — no request at all — and left the guard off
  for the rest of the page: a link away then left without a question;
- a state command in Acties ("Terug naar concept", a button with its own
  question): its question, then "Deze pagina verlaten?", then its question
  AGAIN, then the request. An answer that failed left the typed name in the
  form and the guard off; so did "Annuleren" on that third question.

The guard now asks at `htmx:confirm` and resumes the request itself; its off
state lasts for that one request.

The outside form of the first two tests is put into the page by the test: since
#1659 the app has none (the panel is no way out any more), and the rule is the
guard's, for whatever stands outside the form. It posts to the proposer route
with `hx-swap="none"`: a request that changes nothing and leaves nothing.

Broken on purpose (6 October 2026), each red for its own reason: the resume
replaced by a click on the source → the form's submit never leaves; the reset
in `htmx:afterRequest` taken out → the link after a failed command leaves
unasked; the hand-over to the confirm host replaced by sending at once → the
command's own question is never asked.
"""

import os
import sys
from urllib.parse import parse_qsl

from playwright.sync_api import expect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.activities.test_activity_proposer import (  # noqa: E402, F401
    _remove,
    _seed,
    _stored,
    setup,
)
from tests_e2e.activities.test_new_activity_on_the_fiche import _page  # noqa: E402

DIALOG = "[data-dialog]"
LEAVE = "Deze pagina verlaten?"
TYPED = "Getypt en niet opgeslagen"
OWN = "De activiteit verdwijnt van de publieke site"

_STATE = """() => { const f = document.querySelector('form[data-record-form]'), store = window.Alpine.store('confirm');
  return {dialog: !!store.open, title: store.open ? store.title : null, text: store.open ? store.message : null,
          dirty: window.raakRecordForm.isDirty(), name: f.querySelector('[name=name]').value}; }"""

_OUTSIDE = """(url) => { const form = document.createElement('form');
  form.id = 'outside-1660'; form.setAttribute('hx-post', url); form.setAttribute('hx-swap', 'none');
  form.innerHTML = '<input name="vraag" value="Een vraag van buiten het formulier."><button type="submit" name="knop" value="ja">Verzend</button>';
  document.querySelector('form[data-record-form]').closest('[data-form-flow]').after(form);
  window.htmx.process(form); }"""


def _edit(setup, activity_id: int):  # noqa: F811
    page = _page(setup, f"/admin/activiteiten/{activity_id}?bewerken=1", 1440)
    page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
    page.sent = []
    page.on(
        "request",
        lambda r: (
            page.sent.append((r.url, parse_qsl(r.post_data or ""))) if r.method == "POST" else None
        ),
    )
    page.fill("#name", TYPED)
    return page


def _ask(page, title):
    """The dialog that is open: its title (None for a question without one)."""
    expect(page.locator(DIALOG)).to_be_visible()
    state = page.evaluate(_STATE)
    assert state["dialog"] and (state["title"] or None) == title, state
    return state


def _link_away_asks(page) -> None:
    page.locator("[data-record-head] a").first.click()
    _ask(page, LEAVE)
    page.click(f"{DIALOG} [data-dialog-cancel]")
    assert "bewerken=1" in page.url


def test_weggooien_sends_a_form_outside_the_record_form_and_the_guard_guards_again(setup):  # noqa: F811
    """Red on master twice: no request after "Weggooien", and the link away
    leaves without a question."""
    activity_id = _seed("Bewakertest formulier")
    page = _edit(setup, activity_id)
    try:
        page.evaluate(_OUTSIDE, f"/admin/activiteiten/{activity_id}/raakje/voorstel")
        page.click("#outside-1660 button")
        _ask(page, LEAVE)
        assert page.sent == [], "the request left before the answer"
        page.click(f"{DIALOG} [data-dialog-ok]")
        page.wait_for_function("!document.querySelector('.htmx-request')")
        expect(page.locator(DIALOG)).to_be_hidden()
        print("MEASURE after Weggooien on an outside form", page.sent, page.evaluate(_STATE))
        assert len(page.sent) == 1, "the submit the user chose did not happen exactly once"
        url, fields = page.sent[0]
        assert url.endswith(f"/admin/activiteiten/{activity_id}/raakje/voorstel")
        assert ("vraag", "Een vraag van buiten het formulier.") in fields
        # Not the button's own name and value: htmx takes those from the button
        # that was clicked last and forgets it when the focus moves — to the
        # dialog, here and for every `data-confirm` on a form. Measured, not built.
        assert ("knop", "ja") not in fields

        # the page is still here with the typed value: the guard guards again
        state = page.evaluate(_STATE)
        assert state["name"] == TYPED and state["dirty"], state
        _link_away_asks(page)
        assert page.errors == []
    finally:
        page.close()
        _remove(activity_id)


def test_blijven_sends_nothing_and_leaves_everything_as_it_is(setup):  # noqa: F811
    activity_id = _seed("Bewakertest blijven")
    page = _edit(setup, activity_id)
    try:
        page.evaluate(_OUTSIDE, f"/admin/activiteiten/{activity_id}/raakje/voorstel")
        page.click("#outside-1660 button")
        _ask(page, LEAVE)
        page.click(f"{DIALOG} [data-dialog-cancel]")
        expect(page.locator(DIALOG)).to_be_hidden()
        state = page.evaluate(_STATE)
        assert page.sent == [] and state["name"] == TYPED and state["dirty"], (page.sent, state)
        assert page.locator("#outside-1660 input").input_value() == (
            "Een vraag van buiten het formulier."
        )
        # and the same action asks again: nothing was remembered
        page.click("#outside-1660 button")
        _ask(page, LEAVE)
        page.click(f"{DIALOG} [data-dialog-cancel]")
        _link_away_asks(page)
    finally:
        page.close()
        _remove(activity_id)


def _state_command(page):
    page.locator("[data-actions-trigger]").first.click()
    page.locator('button[hx-post$="/status"]').first.click()


def test_a_state_command_asks_leaving_then_its_own_question_once_and_then_goes(setup):  # noqa: F811
    """Red on master: its own question, the leaving one, and its own again."""
    activity_id = _seed("Bewakertest statusopdracht")
    page = _edit(setup, activity_id)
    try:
        _state_command(page)
        _ask(page, LEAVE)
        page.click(f"{DIALOG} [data-dialog-ok]")
        own = _ask(page, None)
        assert own["text"].startswith(OWN), own
        assert page.sent == []
        page.click(f"{DIALOG} [data-dialog-ok]")
        page.wait_for_function(
            "document.querySelector('form[data-record-form] [name=name]').value !== 'Getypt en niet opgeslagen'"
        )
        expect(page.locator(DIALOG)).to_be_hidden()
        assert [url.rsplit("/", 1)[1] for url, _fields in page.sent] == ["status"]
        state = page.evaluate(_STATE)
        assert state["name"] == "Bewakertest statusopdracht" and not state["dirty"], state
        assert _stored(activity_id)["name"] == "Bewakertest statusopdracht"
        assert page.errors == []
    finally:
        page.close()
        _remove(activity_id)


def test_after_a_command_that_failed_or_was_called_off_the_guard_still_guards(setup):  # noqa: F811
    """Red on master: after either, the link away left without a question and
    the typed value was lost."""
    activity_id = _seed("Bewakertest mislukte opdracht")
    page = _edit(setup, activity_id)
    try:
        # called off at the command's own question, after "Weggooien"
        _state_command(page)
        _ask(page, LEAVE)
        page.click(f"{DIALOG} [data-dialog-ok]")
        _ask(page, None)
        page.click(f"{DIALOG} [data-dialog-cancel]")
        expect(page.locator(DIALOG)).to_be_hidden()
        assert page.sent == [] and page.evaluate(_STATE)["dirty"]
        page.keyboard.press("Escape")  # the Acties menu
        _link_away_asks(page)

        # sent, and the server answers with an error
        page.route("**/status", lambda route: route.fulfill(status=500, body="kapot"))
        _state_command(page)
        _ask(page, LEAVE)
        page.click(f"{DIALOG} [data-dialog-ok]")
        _ask(page, None)
        page.click(f"{DIALOG} [data-dialog-ok]")
        page.wait_for_function("!document.querySelector('.htmx-request')")
        expect(page.locator(DIALOG)).to_be_hidden()
        state = page.evaluate(_STATE)
        print("MEASURE after a failed command", page.sent, state)
        assert len(page.sent) == 1 and state["name"] == TYPED and state["dirty"], state
        page.keyboard.press("Escape")
        _link_away_asks(page)
    finally:
        page.close()
        _remove(activity_id)
