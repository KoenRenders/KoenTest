"""E2E: the Assistent panel in a browser (#1562, CR-11 pilot A, K8 — PR 1).

What a server test cannot see:

- **docked from 1 440 px**: 400 px at the right under the top bar, and the
  content MOVES ASIDE — 1 232 px remain at 1 920 and 768 px at 1 440, where the
  record's summary becomes its strip; the top bar keeps its width; nothing
  overflows;
- **a dialog below 1 440 px** (at most 560 × 720, the background blocked) and
  **a sheet on a phone** (560 px from y = 284, with a handle);
- **X or Escape closes** and returns the focus to the trigger; **a click beside
  the panel does not close it**;
- **the context follows the screen**: another record or another filter is
  another context and a fresh conversation; a page of the same list is not;
- **a late answer to a previous context is not shown**;
- **a question that was not answered stays in the field**, and a suggestion asks
  itself;
- **the trigger is dimmed on a module the assistant does not know** and the
  panel then holds one sentence;
- **the public bell**: 56 px at the bottom right, a window of 400 × 640 above
  it, the sheet on a phone — the same component;
- **the question field is as high as its content** however the value changed
  (#1617): a suggestion, typing, a question that stays after a failed answer;
  one line again after an answer; at most its maximum, then it scrolls inside
  itself and the panel keeps its layout.

The e2e backend has no model key and answers in its test mode; a failed answer
and a late one are played by intercepting the request. Nothing is changed in
the database.

Proven red (each on this branch, restored after):
- `margin-right` on `#main` taken out of the CSS → the docked test fails (the
  content lies under the panel);
- the dialog's media query removed → the dialog test fails;
- `@click.outside` closing added to the panel → the click-beside test fails;
- the focus not returned in `hide()` → the Escape test fails;
- the 204 for an unchanged context removed → the same-list test fails (the
  conversation is gone after a page);
- the panel made to keep its block when the context changes (always 204) → the
  late-answer test fails: the old conversation is still there to answer into;
- the field always emptied after a request → the failed-question test fails.

#1617, red against master `13c00be2` (measured, the six cases of the field
test): after a suggestion the field kept its one line — `clientHeight` 36
against a `scrollHeight` of two lines — and a typed question stood 2 px short
(the height left the border out). On this branch, `raakjeFit` taken out of
`ask()` → "cut off while asking" (the fit after the failed answer hides it
afterwards, which is why the field is measured with the answer held back);
taken out of the failed branch of `raakjeAfterAnswer` → still green, the
field was fitted when the suggestion filled it — that call is for a question
typed into a field that was not laid out.
"""

import os
import re
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_met_sessie, pagina_klaar  # noqa: E402

_BOXES = """() => {
  const box = e => { if (!e || !e.checkVisibility()) return null; const r = e.getBoundingClientRect();
    return {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height), r: Math.round(r.right), b: Math.round(r.bottom)}; };
  const q = s => document.querySelector(s);
  return {
    panel: box(q('.raakje-panel')), backdrop: box(q('.raakje-backdrop')), handle: box(q('.raakje-panel-handle')),
    header: box(q('header')), content: box(q('.admin-content')), card: box(q('[data-summary-card]')),
    form: box(q('[data-form-column]')), field: box(q('.raakje-panel textarea')), bell: box(q('[data-raakje-bell]')),
    scroll: document.documentElement.scrollWidth, width: innerWidth, height: innerHeight,
  };
}"""


_TWO_FRAMES = "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _admin(browser, size):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(base_url=BASE, viewport={"width": size[0], "height": size[1]})
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
    return page


@pytest.fixture(scope="module")
def activity(browser) -> str:
    """The address of the seeded activity the payments list names."""
    page = _admin(browser, (1440, 900))
    page.goto("/admin/betalingen")
    pagina_klaar(page)
    found = re.search(
        r"/admin/activiteiten/(\d+)\?terug=", page.locator("#betalingen-lijst").inner_html()
    )
    page.close()
    assert found, "the seeded payments list names no activity"
    return f"/admin/activiteiten/{found.group(1)}"


def _open(page, url):
    """The screen at `url` with the panel open and its context loaded."""
    page.goto(url)
    pagina_klaar(page)
    trigger = page.locator("[data-raakje-trigger]")
    trigger.wait_for(state="visible")
    if page.locator(".raakje-panel").is_hidden():
        trigger.click()
    page.locator(".raakje-panel [data-context-key]").wait_for(state="visible")
    htmx_stil(page)
    return trigger


def _context(page) -> str:
    return page.locator("[data-panel-context]").inner_text().strip()


def _ask(page, question: str) -> None:
    page.locator(".raakje-panel textarea").fill(question)
    page.locator(".raakje-panel textarea").press("Enter")


def test_docked_the_content_moves_aside_and_nothing_is_covered(browser, activity):
    for width, remaining in ((1920, 1232), (1440, 768)):
        page = _admin(browser, (width, 1080))
        _open(page, activity)
        m = page.evaluate(_BOXES)
        page.close()
        panel = m["panel"]
        assert panel["w"] == 400 and panel["r"] == width and panel["b"] == m["height"], m
        # Under the top bar, which keeps the window's width.
        assert panel["y"] == m["header"]["b"] and m["header"]["r"] == width, m
        assert m["backdrop"] is None, "a docked panel blocks nothing"
        # The content ends where the panel begins: moved aside, not covered.
        assert m["content"]["w"] == remaining and m["content"]["r"] <= panel["x"], m
        assert m["scroll"] == width, m
        if width == 1920:
            # The reading group fits: the summary stays beside the form.
            assert m["card"]["w"] == 300 and m["card"]["x"] >= m["form"]["r"], m
        else:
            # 768 px remain: the summary is the strip above the form, which
            # keeps its width.
            assert m["card"]["w"] == 768 and m["card"]["b"] <= m["form"]["y"], m
            assert m["form"]["w"] == 768, m


def test_below_1440_the_panel_is_a_dialog_over_a_blocked_background(browser, activity):
    page = _admin(browser, (1200, 900))
    _open(page, activity)
    m = page.evaluate(_BOXES)
    panel = m["panel"]
    assert panel["w"] == 560 and panel["h"] == 720, m
    # Centred, and the content keeps its place under it.
    assert (
        abs((panel["x"] + panel["r"]) / 2 - 600) <= 1
        and abs((panel["y"] + panel["b"]) / 2 - 450) <= 1
    )
    assert m["backdrop"] and m["backdrop"]["w"] == 1200 and m["backdrop"]["h"] == 900, m
    assert page.locator(".raakje-panel").get_attribute("aria-modal") == "true"
    page.close()


def test_on_a_phone_the_panel_is_a_sheet_with_a_handle(browser, activity):
    page = _admin(browser, (390, 844))
    _open(page, activity)
    m = page.evaluate(_BOXES)
    page.close()
    panel = m["panel"]
    assert (panel["x"], panel["y"], panel["w"], panel["h"]) == (0, 284, 390, 560), m
    assert m["handle"] and m["handle"]["y"] >= 284 and m["handle"]["b"] <= 300, m
    # The question field is inside the sheet, above the window's bottom.
    assert 284 < m["field"]["y"] and m["field"]["b"] <= 844, m
    assert m["scroll"] == 390, m


def test_escape_and_x_close_and_return_the_focus_and_a_click_beside_does_not(browser, activity):
    page = _admin(browser, (1200, 900))
    trigger = _open(page, activity)
    panel = page.locator(".raakje-panel")
    # A click beside the panel — on the blocked background — leaves it open, and
    # reaches nothing under it. (Two frames: Alpine hides a tick after a click.)
    before = page.url
    page.mouse.click(40, 450)
    page.evaluate(_TWO_FRAMES)
    assert panel.is_visible() and page.url == before
    page.keyboard.press("Escape")
    panel.wait_for(state="hidden")
    assert page.evaluate("() => document.activeElement.hasAttribute('data-raakje-trigger')")
    # And the X.
    trigger.click()
    panel.wait_for(state="visible")
    page.locator("[data-panel-close]").click()
    panel.wait_for(state="hidden")
    assert page.evaluate("() => document.activeElement.hasAttribute('data-raakje-trigger')")
    page.close()

    # Docked: a click on the content beside the panel does not close it either.
    page = _admin(browser, (1440, 1080))
    _open(page, activity)
    page.locator("h1").first.click()
    page.evaluate(_TWO_FRAMES)
    assert page.locator(".raakje-panel").is_visible()
    page.close()


def test_the_context_follows_the_screen(browser, activity):
    page = _admin(browser, (1440, 1080))
    _open(page, activity)
    title = page.locator("[data-record-head] h1").inner_text().strip()
    assert _context(page) == f"over {title}"
    record_key = page.locator("[data-context-key]").get_attribute("data-context-key")

    # A tab of the same record: the same context, and the conversation stays.
    _ask(page, "Blijft dit staan?")
    page.locator("#assistent-gesprek").get_by_text("Blijft dit staan?", exact=True).wait_for()
    htmx_stil(page)
    page.get_by_role("link", name=re.compile("^Inschrijvingen")).first.click()
    pagina_klaar(page)
    assert page.locator(".raakje-panel").is_visible(), "the panel closed over a navigation"
    assert page.locator("[data-context-key]").get_attribute("data-context-key") == record_key
    assert (
        page.locator("#assistent-gesprek").get_by_text("Blijft dit staan?", exact=True).count() == 1
    )

    # Another screen: another context, a fresh conversation.
    page.locator("#admin-nav-zijbalk a[href='/admin/betalingen']").click()
    pagina_klaar(page)
    page.wait_for_function(
        "key => document.querySelector('[data-context-key]').dataset.contextKey !== key",
        arg=record_key,
    )
    assert re.fullmatch(r"over \d+ betalingen?", _context(page)), _context(page)
    assert (
        page.locator("#assistent-gesprek").get_by_text("Blijft dit staan?", exact=True).count() == 0
    )

    # The list's filter is part of the context: the line names it and counts.
    all_key = page.locator("[data-context-key]").get_attribute("data-context-key")
    # (A boosted navigation runs a view transition; until it ends the page takes
    # no click.)
    page.wait_for_function("() => document.getAnimations().length === 0")
    page.locator("#bt-filter input[name=zicht][value=openstaand]").check(force=True)
    page.wait_for_function(
        "key => document.querySelector('[data-context-key]').dataset.contextKey !== key",
        arg=all_key,
    )
    assert re.fullmatch(
        r"over \d+ openstaande betalingen? \(filter Openstaand\)", _context(page)
    ), _context(page)

    # A search term cannot be carried over: the reason, and no question field.
    page.locator('#bt-filter input[type="search"]').fill("zzz")
    page.locator("[data-panel-blocked]").wait_for(state="visible")
    assert "de zoekterm" in page.locator("[data-panel-blocked]").inner_text()
    assert page.locator(".raakje-panel textarea").count() == 0
    page.close()


def test_a_late_answer_to_a_previous_context_is_not_shown(browser, activity):
    """The question is still on its way when the screen changes: its answer
    belongs to a conversation that is gone."""
    page = _admin(browser, (1440, 1080))
    _open(page, activity)
    held = []

    def hold(route):
        held.append(route)

    page.route("**/admin/rapporten/raakje/activiteit/**", hold)
    _ask(page, "Een trage vraag")
    page.wait_for_function("() => true")  # the request is out; it waits in `held`
    page.locator("#admin-nav-zijbalk a[href='/admin/leden']").click()
    pagina_klaar(page)
    page.wait_for_function(
        "() => document.querySelector('[data-context-key]').dataset.contextKey === 'tenant'"
    )
    # Now the late answer arrives.
    for route in held:
        route.fulfill(
            status=200,
            content_type="text/html",
            body='<input type="hidden" name="historie" id="rp-raakje-historie" value="LATE" hx-swap-oob="true">'
            "<div><div data-raakje-answer>LAAT ANTWOORD</div></div>",
        )
    htmx_stil(page)
    assert page.get_by_text("LAAT ANTWOORD").count() == 0
    assert page.locator("#rp-raakje-historie").input_value() != "LATE"
    page.close()


def test_a_question_that_was_not_answered_stays_in_the_field(browser, activity):
    page = _admin(browser, (1440, 1080))
    _open(page, activity)
    endpoint = "**/admin/rapporten/raakje/activiteit/**"
    # The server's own failed answer, as `_ask` sends it: the sentence, and the
    # header that says the question was not answered.
    page.route(
        endpoint,
        lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            headers={"X-Raakje-Failed": "1"},
            body='<div role="alert">Raakje kon geen antwoord geven — probeer het opnieuw. '
            "Je vraag staat er nog.</div>",
        ),
    )
    _ask(page, "Hoeveel inschrijvingen zijn er?")
    page.locator("#assistent-gesprek").get_by_text("Raakje kon geen antwoord geven").wait_for()
    assert page.locator(".raakje-panel textarea").input_value() == "Hoeveel inschrijvingen zijn er?"

    # An answered question empties the field. A suggestion asks itself: the
    # question goes out as it stands (the e2e backend's test-mode answer).
    page.unroute(endpoint)
    suggestion = page.locator("[data-suggestion]").nth(1)
    asked = suggestion.get_attribute("data-question")
    suggestion.click()
    page.locator("#assistent-gesprek").get_by_text(asked, exact=True).wait_for()
    page.locator("#assistent-gesprek [data-raakje-answer]").wait_for()
    htmx_stil(page)
    assert page.locator(".raakje-panel textarea").input_value() == ""
    page.close()


_FIELD = """() => {
  const f = document.querySelector('.raakje-panel textarea'), p = document.querySelector('.raakje-panel');
  const hint = [...p.querySelectorAll('p')].pop().getBoundingClientRect(), b = p.getBoundingClientRect();
  return {client: f.clientHeight, scroll: f.scrollHeight, value: f.value,
          max: parseFloat(getComputedStyle(f).maxHeight), offset: f.offsetHeight,
          inside: Math.round(hint.bottom) <= Math.round(b.bottom) && Math.round(f.getBoundingClientRect().right) <= Math.round(b.right),
          page: document.documentElement.scrollWidth};
}"""
_TWO_LINES = "Hoeveel gezinnen zijn er dit jaar per gemeente ingeschreven voor een activiteit?"
_FAILED = (
    '<div role="alert">Raakje kon geen antwoord geven — probeer het opnieuw. '
    "Je vraag staat er nog.</div>"
)


def _public(browser, size):
    page = browser.new_page(base_url=BASE, viewport={"width": size[0], "height": size[1]})
    page.goto("/")
    pagina_klaar(page)
    page.locator("[data-raakje-bell]").click()
    page.locator(".raakje-panel").wait_for(state="visible")
    return page


@pytest.mark.parametrize("shell", ["admin", "public"])
@pytest.mark.parametrize("size", [(1440, 1080), (1200, 900), (390, 844)])
def test_the_question_field_is_as_high_as_its_content(browser, activity, shell, size):
    """#1617: docked, dialog and sheet, in the back office and under the bell.
    The answers are played by intercepting the request, so the test decides
    whether the question stays (not answered) or goes (answered)."""
    if shell == "admin":
        page = _admin(browser, size)
        _open(page, activity)
    else:
        page = _public(browser, size)
    where = f"{shell} @{size[0]}"
    endpoint = "**" + page.locator(".raakje-panel form").get_attribute("hx-post") + "*"
    field = page.locator(".raakje-panel textarea")
    one_line = page.evaluate(_FIELD)
    assert one_line["value"] == "" and one_line["client"] == one_line["scroll"], (where, one_line)

    # A suggestion of more than one line. The answer is held back, so the field
    # is measured WHILE the question is under way — what Koen saw — and again
    # after an answer that failed: the question stays, at its height.
    held = []
    page.route(endpoint, lambda route: held.append(route))
    suggestion = page.locator("[data-suggestion]").first
    suggestion.evaluate("(e, q) => { e.dataset.question = q; }", _TWO_LINES)
    with page.expect_request(endpoint):
        suggestion.click()
    asking = page.evaluate(_FIELD)
    assert asking["value"] == _TWO_LINES, (where, asking)
    assert asking["client"] == asking["scroll"], f"{where}: cut off while asking — {asking}"
    assert len(held) == 1, f"{where}: {len(held)} requests"
    held[0].fulfill(
        status=200, content_type="text/html", headers={"X-Raakje-Failed": "1"}, body=_FAILED
    )
    page.locator(".raakje-panel").get_by_text("Raakje kon geen antwoord geven").wait_for()
    htmx_stil(page)
    stayed = page.evaluate(_FIELD)
    print("MEASURE field", where, "one line", one_line["client"], "suggestion", stayed)
    assert stayed["value"] == _TWO_LINES, (where, stayed)
    assert stayed["scroll"] > one_line["scroll"], (
        f"{where}: the suggestion fits one line — {stayed}"
    )
    assert stayed["client"] == stayed["scroll"], f"{where}: a line is cut off — {stayed}"
    assert stayed["inside"] and stayed["page"] == size[0], (where, stayed)

    # Answered: the field is one line again.
    page.unroute(endpoint)
    page.route(
        endpoint,
        lambda route: route.fulfill(
            status=200, content_type="text/html", body="<div data-raakje-answer>Zeven.</div>"
        ),
    )
    field.press("Enter")
    page.locator(".raakje-panel [data-raakje-answer]").last.wait_for()
    htmx_stil(page)
    emptied = page.evaluate(_FIELD)
    assert emptied["value"] == "" and emptied["client"] == one_line["client"], (where, emptied)

    # Typed: the same height as the suggestion gave.
    field.fill(_TWO_LINES)
    typed = page.evaluate(_FIELD)
    assert typed["client"] == typed["scroll"] == stayed["scroll"], (where, typed, stayed)

    # Far more than fits: the field stops at its maximum and scrolls inside
    # itself; the hint line under it stays inside the panel.
    field.fill(" ".join([_TWO_LINES] * 8))
    full = page.evaluate(_FIELD)
    assert full["offset"] == full["max"] == 120, (where, full)
    assert full["scroll"] > full["client"] and full["inside"], (where, full)
    assert full["page"] == size[0], (where, full)
    page.close()


def test_on_an_unknown_module_the_trigger_is_dimmed_and_the_panel_says_why(browser):
    page = _admin(browser, (1440, 1080))
    page.goto("/admin/media")
    pagina_klaar(page)
    trigger = page.locator("[data-raakje-trigger]")
    trigger.wait_for(state="visible")
    assert trigger.get_attribute("data-available") == "false"
    # Dimmed, not disabled: it takes the focus and opens the panel.
    trigger.focus()
    assert page.evaluate("() => document.activeElement.hasAttribute('data-raakje-trigger')")
    page.keyboard.press("Enter")
    page.locator("[data-panel-blocked]").wait_for(state="visible")
    assert page.locator("[data-panel-blocked]").inner_text().strip() == (
        "Raakje kent deze gegevens nog niet."
    )
    assert page.locator(".raakje-panel textarea").count() == 0
    # Back on a module it knows, the trigger is active again.
    page.locator("#admin-nav-zijbalk a[href='/admin/leden']").click()
    pagina_klaar(page)
    page.wait_for_function(
        "() => document.querySelector('[data-raakje-trigger]').dataset.available === 'true'"
    )
    page.close()


def test_the_public_bell_opens_the_same_panel(browser):
    for size in ((1440, 1080), (390, 844)):
        page = browser.new_page(base_url=BASE, viewport={"width": size[0], "height": size[1]})
        page.goto("/")
        pagina_klaar(page)
        bell = page.locator("[data-raakje-bell]")
        closed = page.evaluate(_BOXES)
        assert closed["bell"]["w"] == 56 and closed["bell"]["h"] == 56, closed
        assert closed["bell"]["r"] == size[0] - 16 and closed["bell"]["b"] == size[1] - 16, closed
        assert closed["panel"] is None
        bell.click()
        page.locator(".raakje-panel").wait_for(state="visible")
        m = page.evaluate(_BOXES)
        panel = m["panel"]
        if size[0] == 1440:
            # A window above the bell; the page behind it stays usable.
            assert (panel["w"], panel["h"]) == (400, 640) and panel["b"] <= m["bell"]["y"], m
            assert m["backdrop"] is None, m
        else:
            assert (panel["x"], panel["y"], panel["w"], panel["h"]) == (0, 284, 390, 560), m
        assert page.locator("[data-panel-title]").inner_text().strip() == "Raakje"
        assert page.locator("[data-suggestion]").count() == 3
        assert page.locator(".raakje-panel form").get_attribute("hx-post") == "/raakje/vraag"
        page.keyboard.press("Escape")
        page.locator(".raakje-panel").wait_for(state="hidden")
        assert page.evaluate("() => document.activeElement.hasAttribute('data-raakje-bell')")
        assert m["scroll"] == size[0], m
        page.close()
