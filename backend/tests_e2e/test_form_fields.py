"""E2E: the form grid, the field and the activity fiche in its two states (CR-11 block 6, #1558).

Measured from the rendered DOM (design-system-end-state §1.3, §1.4, §3.1, §3.2,
§3.5):

- the reading group is left-aligned: the form starts on the page margin, on
  the same x as the record head and the tabs, 768 px wide, with the summary
  24 px beside it — never centred;
- the grid: a half field 361 px and a quarter 174.5 px in a section of 768 px,
  a control 40 px high with a radius of 6 px, a field with one line of help
  88.5 px; on a phone one column and controls of 44 px;
- the switch: the knob at the left of its label, 8 px apart;
- the fiche reads and edits as a whole: "Bewerken" opens the editor, one
  "Opslaan" writes and returns to reading;
- cancelling is an action in the head's menu, with a question first.

Screenshots go outside the repo.
"""

import os
import sys
from datetime import date, time, timedelta

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

NAME = "Veldentest met soep"

_FRAME = """() => {
  const q = s => document.querySelector(s);
  const r = e => { const b = e.getBoundingClientRect(); return {x: Math.round(b.left), y: Math.round(b.top + scrollY), w: Math.round(b.width * 10) / 10, h: Math.round(b.height * 10) / 10, right: Math.round(b.right)}; };
  const main = q('#main');
  return {
    page: [document.documentElement.scrollWidth, innerWidth],
    margin: Math.round(main.getBoundingClientRect().left + parseFloat(getComputedStyle(main).paddingLeft)),
    frame_right: Math.round(main.getBoundingClientRect().right - parseFloat(getComputedStyle(main).paddingRight)),
    head: r(q('[data-record-head]')), tabs: r(q('[data-related-tabs]')),
    form: r(q('[data-form-column]')), summary: r(q('[data-summary-column]')),
    mode: q('[data-form-flow]').dataset.mode,
    // the one form is `display:contents` (#1559): its children are the flow's blocks
    blocks: [...q('[data-form-flow]').children].flatMap(e => e.matches('form') ? [...e.children] : [e]).filter(e => e.checkVisibility() && e.getBoundingClientRect().height > 0)
      .map(e => e.matches('[data-rare-settings]') ? 'rare' : e.matches('[data-provisional-bar]') ? 'bar' : e.matches('[data-form-section]') ? 'section' : e.matches('form') ? 'form' : 'card'),
    sections: [...document.querySelectorAll('[data-form-flow] [data-form-section]')].map(s => ({title: s.querySelector('h2').innerText, ...r(s)})),
    fields: [...document.querySelectorAll('#aa-section-activity [data-field], #aa-section-audience [data-field], #aa-section-internal [data-field]')].map(f => ({name: f.dataset.field, ...r(f)})),
    controls: [...document.querySelectorAll('#aa-act-form input:not([type=checkbox]):not([type=file]):not([type=hidden]), #aa-act-form select, #aa-act-form [data-kind=switch] label, #aa-act-form [data-upload] label')].map(e => Math.round(e.getBoundingClientRect().height)),
  };
}"""

_KIT = """() => {
  const root = document.querySelector('[data-kit-form=edit]');
  const r = e => { const b = e.getBoundingClientRect(); return {x: Math.round(b.left), y: Math.round(b.top + scrollY), w: Math.round(b.width * 10) / 10, h: Math.round(b.height * 10) / 10}; };
  const f = n => root.querySelector(`[data-field^=${n}]`);
  const c = n => f(n).querySelector('input, select, textarea');
  const track = root.querySelector('[data-switch-track]').getBoundingClientRect();
  const label = root.querySelector('[data-switch-label]').getBoundingClientRect();
  return {
    section: r(root.querySelector('[data-form-section]')),
    name: r(f('kit_name')), slug: r(f('kit_slug')), location: r(f('kit_location')), description: r(f('kit_description')),
    max: r(f('kit_max')), price: r(f('kit_price')), date: r(f('kit_date')), time: r(f('kit_time')),
    control: {h: Math.round(c('kit_name').getBoundingClientRect().height), radius: getComputedStyle(c('kit_name')).borderRadius,
              select: Math.round(c('kit_audience').getBoundingClientRect().height)},
    switch_gap: Math.round(label.left - track.right), knob_left: track.left < label.left,
    switch_track: [Math.round(track.width), Math.round(track.height)],
    switch_mid: Math.round(track.top + track.height / 2 + scrollY),
    select_mid: Math.round(c('kit_audience').getBoundingClientRect().top + c('kit_audience').getBoundingClientRect().height / 2 + scrollY),
    switch_on: getComputedStyle(root.querySelector('[data-switch-track]')).backgroundColor,
    rare_open: root.querySelector('[data-rare-settings]').open,
    rare_last: root.querySelector('[data-form-column]').lastElementChild.matches('[data-rare-settings]'),
  };
}"""


def _activity() -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate

    db = SessionLocal()
    try:
        existing = db.query(Activity).filter(Activity.name == NAME).first()
        if existing is not None:
            return existing.id
        activity = Activity(
            name=NAME,
            slug="veldentest-met-soep",
            location="Parochiezaal",
            description="Samen op pad door het dorp. Na de wandeling een warme kom soep in de zaal.",
        )
        db.add(activity)
        db.flush()
        db.add(
            ActivityDate(
                activity_id=activity.id,
                start_date=date.today() + timedelta(days=75),
                start_time=time(14, 0),
            )
        )
        db.commit()
        return activity.id
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    activity_id = _activity()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), activity_id
        b.close()


def _page(setup, width: int, path: str):
    b, session, _id = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    login_met_sessie(page, session)
    page.goto(path)
    pagina_klaar(page)
    return page


@pytest.mark.parametrize("width", [1440, 1920])
@pytest.mark.parametrize("suffix", ["", "?bewerken=1"])
def test_the_reading_group_is_left_aligned_never_centred(setup, width, suffix):
    """Proven red with `margin-inline:auto` on `.record-columns`: at 1 920 px the
    form then starts 270 px right of the page margin."""
    page = _page(setup, width, f"/admin/activiteiten/{setup[2]}{suffix}")
    f = page.evaluate(_FRAME)
    print("MEASURE frame", width, suffix or "read", f["margin"], f["form"], f["summary"])
    assert f["form"]["x"] == f["margin"], "the form starts on the page margin"
    assert f["head"]["x"] == f["margin"] and f["tabs"]["x"] == f["margin"], (
        "on the same x as the head and the tabs"
    )
    assert f["form"]["w"] == 768
    assert f["summary"]["x"] == f["form"]["right"] + 24 and f["summary"]["w"] == 300
    assert f["frame_right"] - f["summary"]["right"] >= 0, "the room beyond the summary stays empty"
    assert f["page"][0] <= f["page"][1]
    page.close()


def test_the_kit_grid_gives_each_kind_its_width(setup):
    page = _page(setup, 1440, "/admin/design-system")
    k = page.evaluate(_KIT)
    print("MEASURE kit 1440", k)
    assert k["section"]["w"] == 768
    assert k["name"]["w"] == 361 and k["slug"]["w"] == 361, "two halves in 734 px"
    assert k["name"]["y"] == k["slug"]["y"] and k["slug"]["x"] - (k["name"]["x"] + 361) == 12
    assert k["location"]["y"] > k["name"]["y"] and k["location"]["w"] == 361, (
        "a half field alone on its row"
    )
    assert k["description"]["w"] == 734, "a textarea is full"
    for quarter in ("max", "price", "date", "time"):
        assert k[quarter]["w"] == 174.5, quarter
    assert len({k[q]["y"] for q in ("max", "price", "date", "time")}) == 1, (
        "four quarters on one row"
    )
    assert k["control"] == {"h": 40, "radius": "6px", "select": 40}
    assert k["slug"]["h"] == 88.5, "label, control and one line of help"
    assert k["name"]["h"] == 65
    assert k["knob_left"] and k["switch_gap"] == 8, "the knob at the left of its label, 8 px apart"
    # A track of 0 × 0 also stands "at the left, 8 px apart": the switch must be drawn.
    # (Found on the screenshot: a doubled quote took the track's classes away.)
    assert k["switch_track"] == [44, 24], "the track is drawn"
    assert abs(k["switch_mid"] - k["select_mid"]) <= 1, (
        "beside a labelled field the switch stands on the control's line"
    )
    assert k["switch_on"] not in ("rgba(0, 0, 0, 0)", "transparent"), "and coloured when on"
    assert k["rare_open"] is False and k["rare_last"]
    page.close()


def test_on_a_phone_the_grid_is_one_column_with_touch_controls(setup):
    page = _page(setup, 390, "/admin/design-system")
    k = page.evaluate(_KIT)
    print("MEASURE kit 390", k)
    tops = [k[n]["y"] for n in ("name", "slug", "location", "description")]
    assert tops == sorted(tops) and len(set(tops)) == 4, "one under the other, in order"
    assert len({k[n]["x"] for n in ("name", "slug", "max", "price", "date", "time")}) == 1
    assert len({k[n]["w"] for n in ("name", "slug", "max", "price")}) == 1, (
        "every field takes the column"
    )
    assert k["control"]["h"] == 44 and k["control"]["select"] == 44
    page.close()


def test_the_fiche_on_a_phone_is_one_column_in_the_same_order(setup):
    read = _page(setup, 390, f"/admin/activiteiten/{setup[2]}")
    r = read.evaluate(_FRAME)
    read.close()
    edit = _page(setup, 390, f"/admin/activiteiten/{setup[2]}?bewerken=1")
    e = edit.evaluate(_FRAME)
    print(
        "MEASURE fiche 390",
        {"read": r["sections"], "edit": e["sections"], "controls": e["controls"]},
    )
    assert r["page"] == [390, 390] and e["page"] == [390, 390]
    assert [f["name"] for f in r["fields"]] == [f["name"] for f in e["fields"]], (
        "the same fields in the same order"
    )
    for state in (r, e):
        tops = [f["y"] for f in state["fields"]]
        assert tops == sorted(tops) and len(set(tops)) == len(tops), "one column"
        assert [s["title"] for s in state["sections"]] == ["Activiteit", "Publiek", "Intern"]
    assert e["controls"] and min(e["controls"]) >= 44, f"touch targets: {e['controls']}"
    assert e["blocks"][-2:] == ["rare", "bar"], "the closed section last, then the save"
    assert r["blocks"][-1] == "rare"
    edit.close()


def test_the_activity_section_keeps_its_measured_heights(setup):
    """Recorded for the handover; held loosely, so a text that wraps one line more
    does not turn the suite red — a section that doubles does."""
    read = _page(setup, 1440, f"/admin/activiteiten/{setup[2]}")
    r = read.evaluate(_FRAME)
    read.close()
    edit = _page(setup, 1440, f"/admin/activiteiten/{setup[2]}?bewerken=1")
    e = edit.evaluate(_FRAME)
    edit.close()
    print(
        "MEASURE section Activiteit 1440",
        {
            "read": r["sections"][0],
            "edit": e["sections"][0],
            "first_field": [r["fields"][0], e["fields"][0]],
        },
    )
    assert 250 <= r["sections"][0]["h"] <= 340
    assert 440 <= e["sections"][0]["h"] <= 560
    assert e["sections"][0]["h"] > r["sections"][0]["h"], (
        "the editor takes more room, in the same place"
    )
    assert r["fields"][0]["y"] == e["fields"][0]["y"], (
        "the first field starts on the same y in both states"
    )
    gaps = [b["y"] - (a["y"] + a["h"]) for a, b in zip(e["sections"], e["sections"][1:])]
    assert gaps == [32, 32], "32 px between sections"


def test_bewerken_opens_the_editor_and_one_save_returns_to_reading(setup):
    base = f"/admin/activiteiten/{setup[2]}"
    page = _page(setup, 1440, base)
    assert page.evaluate(_FRAME)["mode"] == "read"
    assert page.locator("#aa-act-form").count() == 0

    page.click('[data-head-controls] a:has-text("Bewerken")')
    pagina_klaar(page)
    assert page.url.endswith(f"{base}?bewerken=1")
    assert page.evaluate(_FRAME)["mode"] == "edit"
    page.fill("#location", "Dorpshuis")
    page.locator('[data-kind="switch"] label').click()
    assert page.locator("#members_only").is_checked()
    page.click('[data-provisional-bar] button:has-text("Opslaan")')
    page.wait_for_selector('[data-form-flow][data-mode="read"]')
    pagina_klaar(page)

    assert page.url.endswith(base), "the address lost its edit flag"
    assert page.locator('[data-field="location"] [data-value]').inner_text() == "Dorpshuis"
    assert page.locator('[data-field="members_only"] [data-value]').inner_text() == "ja"
    assert page.locator('[data-head-controls] a:has-text("Bewerken")').count() == 1, (
        "the head's primary is back"
    )
    assert "Dorpshuis" in page.locator("[data-facts]").inner_text(), "the head followed the save"
    page.reload()
    pagina_klaar(page)
    assert page.evaluate(_FRAME)["mode"] == "read", "a reload does not reopen the editor"

    # Annuleren leaves the editor without writing.
    page.goto(f"{base}?bewerken=1")
    pagina_klaar(page)
    page.fill("#location", "Niet bewaren")
    page.click('[data-provisional-bar] a:has-text("Annuleren")')
    pagina_klaar(page)
    assert page.url.endswith(base)
    assert page.locator('[data-field="location"] [data-value]').inner_text() == "Dorpshuis"
    page.close()


def test_cancelling_asks_first_and_shows_in_the_head(setup):
    base = f"/admin/activiteiten/{setup[2]}"
    page = _page(setup, 1440, base)
    page.click("[data-actions-trigger]")
    page.click('[data-actions-menu] [role=menuitem]:has-text("Activiteit annuleren")')
    dialog = page.locator('[role="dialog"]:visible')
    dialog.wait_for()
    assert "geen inschrijvingen meer" in dialog.inner_text()
    assert "Geannuleerd" not in page.locator("[data-badges]").inner_text(), (
        "nothing happens before the answer"
    )
    dialog.locator("button").last.click()
    page.wait_for_selector('[data-badges]:has-text("Geannuleerd")')
    pagina_klaar(page)

    page.click("[data-actions-trigger]")
    assert (
        page.locator('[data-actions-menu] [role=menuitem]:has-text("Activiteit annuleren")').count()
        == 0
    )
    page.click('[data-actions-menu] [role=menuitem]:has-text("Annulering intrekken")')
    page.wait_for_selector('[data-badges]:not(:has-text("Geannuleerd"))')
    page.close()
