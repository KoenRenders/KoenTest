"""E2E: a proposal for the form (CR-11 block 10, #1562; design-system-end-state §3.15).

The mechanism, without a model behind it: a proposal is field names + values +
the value each field had when it was asked (its base). In a real browser,
because everything here happens in the page:

- offered: the fields it touches are marked ("Voorstel · nog niet toegepast",
  a blue line, the brand tint), the block says "n velden ingevuld als voorstel";
- Toepassen fills the fields IN THE FORM and sends nothing — only the form's own
  save writes (on the activity: the action bar's Opslaan, block 9);
- a field changed since the proposal was asked is left alone and named: a
  proposal never overwrites in silence;
- Negeren takes the marks away and changes nothing.

The kit page carries the demo; the activity proves the one save.
"""

import json
import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

NAME = "Voorsteltest zonder inschrijving"


def _seed() -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity

    db = SessionLocal()
    try:
        existing = db.query(Activity).filter(Activity.name == NAME).first()
        if existing is not None:
            return existing.id
        activity = Activity(name=NAME, location="Parochiezaal", description="Samen op pad.")
        db.add(activity)
        db.commit()
        return activity.id
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    activity_id = _seed()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), activity_id
        b.close()


def _open(setup, path: str, width: int = 1440):
    b, session, _id = setup
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.requests = []
    page.on(
        "request",
        lambda req: page.requests.append(req.url) if req.method != "GET" else None,
    )
    login_met_sessie(page, session)
    page.goto(path)
    pagina_klaar(page)
    return page


KIT = "[data-kit-proposal]"
BLOCK = f"{KIT} [data-form-proposal]"

_STATE = """(names) => names.map(name => { const f = document.querySelector(`[data-field="${name}"]`), c = f.querySelector('input:not([type=hidden]), textarea, select');
  const note = f.querySelector('[data-proposal-note]'); const s = getComputedStyle(c);
  return {name, value: c.value, proposed: f.hasAttribute('data-proposed'), applied: f.hasAttribute('data-proposal-applied'),
          note: note ? note.innerText : '', line: s.borderLeftWidth, tint: s.backgroundColor}; })"""
FIELDS = ["kit_prop_name", "kit_prop_place", "kit_prop_text"]
WHITE = "rgb(255, 255, 255)"


def test_an_offered_proposal_marks_its_fields_and_changes_nothing(setup):
    """Proven red by not calling `offer` when the block arrives: no field is marked."""
    page = _open(setup, "/admin/design-system")
    page.locator(BLOCK).scroll_into_view_if_needed()
    assert page.locator(f"{BLOCK} [data-proposal-summary]").inner_text() == (
        "3 velden ingevuld als voorstel"
    )
    assert page.locator(f"{BLOCK} [data-proposal-labels]").inner_text() == (
        "Naam · Locatie · Omschrijving"
    )
    state = page.evaluate(_STATE, FIELDS)
    print("MEASURE proposal offered", state)
    assert [f["value"] for f in state] == ["Wandeling", "Parochiezaal", "Samen op pad."], (
        "offered is not filled"
    )
    for field in state:
        assert field["proposed"] and not field["applied"]
        assert field["note"] == "Voorstel · nog niet toegepast"
        assert field["line"] == "3px" and field["tint"] != WHITE, "a blue line and the tint"
    assert page.requests == []
    page.close()


def test_toepassen_fills_the_form_skips_a_field_changed_meanwhile_and_sends_nothing(setup):
    """A proposal with a stale base is refused for that field. Proven red by
    dropping the base comparison from `apply`: the typed location is overwritten
    in silence."""
    page = _open(setup, "/admin/design-system")
    page.locator(BLOCK).scroll_into_view_if_needed()
    page.fill("#kit-prop-place", "Dorpshuis")  # changed after the proposal was asked
    page.click(f"{BLOCK} [data-proposal-apply]")
    state = {f["name"]: f for f in page.evaluate(_STATE, FIELDS)}
    assert state["kit_prop_name"]["value"] == "Herfstwandeling met soep"
    assert state["kit_prop_text"]["value"] == "Een wandeling van acht kilometer, met soep achteraf."
    assert state["kit_prop_place"]["value"] == "Dorpshuis", "never overwritten in silence"
    for name in ("kit_prop_name", "kit_prop_text"):
        assert state[name]["applied"] and not state[name]["proposed"]
        assert state[name]["note"] == "Ingevuld door Assistent · nog niet opgeslagen"
    assert not state["kit_prop_place"]["applied"] and state["kit_prop_place"]["note"] == ""
    result = page.locator(f"{BLOCK} [data-proposal-result]")
    expect(result).to_be_visible()
    assert result.inner_text() == (
        "2 velden ingevuld. 1 veld overgeslagen: intussen gewijzigd (Locatie)."
    )
    assert not page.locator(f"{BLOCK} [data-proposal-actions]").is_visible(), "applied once"
    assert page.requests == [], "Toepassen writes to the form, not to the server"
    assert not [e for e in page.errors if "roposal" in e], page.errors
    page.close()


def test_negeren_takes_the_marks_away_and_leaves_the_values(setup):
    page = _open(setup, "/admin/design-system")
    page.locator(BLOCK).scroll_into_view_if_needed()
    page.click(f"{BLOCK} [data-proposal-dismiss]")
    state = page.evaluate(_STATE, FIELDS)
    assert [f["value"] for f in state] == ["Wandeling", "Parochiezaal", "Samen op pad."]
    assert not any(f["proposed"] or f["applied"] or f["note"] for f in state)
    assert all(f["line"] != "3px" for f in state)
    assert page.locator(f"{BLOCK} [data-proposal-result]").inner_text() == "Voorstel genegeerd."
    assert page.requests == []
    page.close()


def _proposal_on_the_fiche(page, fields: list[dict]) -> None:
    """Put a proposal block on the page the way the panel's answer does: the
    kit's own markup (taken from the kit page's macro output), with these fields."""
    page.evaluate(
        """(fields) => { const block = document.createElement('form');
             block.setAttribute('data-form-proposal', ''); block.id = 'test-proposal';
             block.dataset.wordProposed = 'Voorstel · nog niet toegepast';
             block.dataset.wordApplied = 'Ingevuld door Assistent · nog niet opgeslagen';
             block.dataset.wordDoneOne = '1 veld ingevuld.'; block.dataset.wordDoneMany = '{n} velden ingevuld.';
             block.innerHTML = '<script type="application/json" data-proposal-fields></scr' + 'ipt>'
               + '<div data-proposal-actions><button type="button" data-proposal-apply>Toepassen</button></div><p data-proposal-result hidden></p>';
             block.querySelector('[data-proposal-fields]').textContent = JSON.stringify(fields);
             document.querySelector('.admin-content').appendChild(block); window.raakFormProposal.scan(); }""",
        fields,
    )


def test_on_the_activity_toepassen_writes_nothing_and_opslaan_saves(setup):
    """Block 9's one save is respected: after Toepassen the form is changed and
    unsaved — a reload shows the old values — and Opslaan writes them, with one
    history row for the activity. The record form reads "changed" from the
    values themselves, so this holds however the value arrived; that the field
    also TELLS its listeners (a counter, a growing field) is proven on the
    newsletter's preview text, where the counter follows an applied proposal
    (`test_newsletter_panel.py`; seen red with the input event left out)."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity
    from app.domains.activities.models import ActivityHistory

    _b, _s, activity_id = setup
    page = _open(setup, f"/admin/activiteiten/{activity_id}?bewerken=1")
    page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
    _proposal_on_the_fiche(
        page,
        [
            {"name": "location", "label": "Locatie", "value": "Dorpshuis", "base": "Parochiezaal"},
            {
                "name": "description",
                "label": "Omschrijving",
                "value": "Acht kilometer, met soep.",
                "base": "Samen op pad.",
            },
        ],
    )
    assert page.locator('[data-field="location"]').get_attribute("data-proposed") is not None
    assert page.evaluate("window.raakRecordForm.isDirty()") is False, "offered changes nothing"

    page.click("#test-proposal [data-proposal-apply]")
    assert page.locator("#location").input_value() == "Dorpshuis"
    assert page.evaluate("window.raakRecordForm.isDirty()") is True, "the form knows it changed"
    assert page.requests == [], "nothing was sent"

    def stored():
        db = SessionLocal()
        try:
            activity = db.query(Activity).filter(Activity.id == activity_id).one()
            history = db.query(ActivityHistory).filter_by(activity_id=activity_id).count()
            return activity.location, activity.description, history
        finally:
            db.close()

    location, description, history = stored()
    assert (location, description) == ("Parochiezaal", "Samen op pad."), "not in the database"

    page.click("[data-action-bar] [data-form-save]")
    page.wait_for_selector('[data-form-flow][data-mode="read"]')
    after = stored()
    assert after[:2] == ("Dorpshuis", "Acht kilometer, met soep.")
    assert after[2] == history + 1, "one row in Wijzigingen, written by Opslaan"
    assert page.errors == []

    # back to what the next run expects
    db = SessionLocal()
    try:
        activity = db.query(Activity).filter(Activity.id == activity_id).one()
        activity.location, activity.description = "Parochiezaal", "Samen op pad."
        db.commit()
    finally:
        db.close()
    page.close()


def test_the_kit_block_carries_its_fields_as_data_not_as_markup(setup):
    """The values travel as JSON in the block: a value with markup in it is text
    for the field, never markup of the page."""
    page = _open(setup, "/admin/design-system")
    raw = page.locator(f"{BLOCK} [data-proposal-fields]").inner_text()
    fields = json.loads(raw)
    assert [f["name"] for f in fields] == FIELDS
    assert all(set(f) == {"name", "label", "value", "base"} for f in fields)
    page.close()
