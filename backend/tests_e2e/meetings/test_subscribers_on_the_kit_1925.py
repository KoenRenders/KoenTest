"""E2E: the newsletter's subscribers on the kit's table (#1925; Koen, 16 October
2026, "7 ja").

A row carries ONE visible action, "Uitschrijven" — none on an address that is
already unsubscribed — and "Verwijderen" behind its ⋯, red and last. Walked at
390 and 1 440 px: the table stays inside its frame, the page does not scroll
sideways, the buttons are touch targets; then Uitschrijven and Verwijderen are
used through the browser, each with its question. `MEASURE` lines print what
was measured; set `E2E_PRINTS` to keep a print of each width.

Made-up subscribers on the example domain, removed again afterwards.

Broken on purpose (16 October 2026): the delete item moved back out of the
menu as a visible button → "one visible action" is red; `action` given to an
unsubscribed address → the unsubscribed row shows a button and is red.

The width and Bron (Koen, 16 October 2026, "b"), measured at 1 024, 1 150 and
1 440 px against Personen, a `list_page`. Broken on purpose, each put back:
master's two templates → the content is 1 024 px against 1 038 and 1 168, red at
1 150 and 1 440; master's priorities (Voornaam 2, Bron 1) → at 1 150 px Voornaam
shows and Bron does not, red.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

LIST = "/admin/nieuwsbrieven/abonnees"


@pytest.fixture(scope="module")
def subscribers():
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.newsletter.models import Subscriber, SubscriberSource, SubscriberStatus

    tag = secrets.token_hex(3)
    db = SessionLocal()
    made = []
    try:
        for name, status in (
            ("bevestigd", SubscriberStatus.CONFIRMED),
            ("uitgeschreven", SubscriberStatus.UNSUBSCRIBED),
            ("weg", SubscriberStatus.CONFIRMED),
        ):
            s = Subscriber(
                email=f"{name}-{tag}@example.com",
                first_name=name.capitalize(),
                status=status,
                source=SubscriberSource.ADMIN,
                unsubscribe_token=secrets.token_hex(16),
            )
            db.add(s)
            db.flush()
            made.append(s.id)
        db.commit()
        yield tag
    finally:
        db.rollback()
        db.query(Subscriber).filter(Subscriber.id.in_(made)).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        yield b
        b.close()


def _open(browser, width):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
    page.goto(LIST)
    pagina_klaar(page)
    return page


def _row(page, address):
    return page.locator("[data-subscriber-row]", has_text=address)


@pytest.mark.parametrize("width", [390, 1440])
def test_one_visible_action_and_the_rest_behind_the_menu(browser, subscribers, width):
    tag = subscribers
    page = _open(browser, width)
    try:
        confirmed = _row(page, f"bevestigd-{tag}@example.com")
        gone = _row(page, f"uitgeschreven-{tag}@example.com")
        assert confirmed.locator("[data-row-action]").all_inner_texts() == ["Uitschrijven"]
        assert gone.locator("[data-row-action]").count() == 0, "an unsubscribed address has none"
        for row in (confirmed, gone):
            assert row.locator("[data-row-menu-trigger]").count() == 1
            assert row.locator("button", has_text="Verwijderen").is_hidden(), "behind ⋯"
        frame = page.locator("[data-table-frame]").bounding_box()
        trigger = confirmed.locator("[data-row-menu-trigger]").bounding_box()
        scroll = page.evaluate("document.documentElement.scrollWidth")
        print(
            f"MEASURE {width}: frame {frame['x']:.0f}..{frame['x'] + frame['width']:.0f}, "
            f"⋯ {trigger['width']:.0f}×{trigger['height']:.0f}, page {scroll}"
        )
        assert scroll == width, "the page scrolls sideways"
        assert trigger["height"] >= (44 if width < 768 else 36)
        folder = os.environ.get("E2E_PRINTS")
        if folder:
            os.makedirs(folder, exist_ok=True)
            page.screenshot(
                path=os.path.join(folder, f"1925-abonnees-{width}.png"), full_page=False
            )
    finally:
        page.close()


_SHOWN = """() => {
  const content = document.querySelector('.admin-content').getBoundingClientRect();
  const head = key => [...document.querySelectorAll('[data-table-frame] th')]
    .find(th => th.innerText.trim() === key);
  const shown = th => !!th && th.getBoundingClientRect().width > 0;
  return {content: Math.round(content.width),
          bron: shown(head('Bron')), voornaam: shown(head('Voornaam'))};
}"""


@pytest.mark.parametrize("width", [1024, 1150, 1440])
def test_the_list_is_as_wide_as_the_kits_lists_and_shows_bron_first(browser, subscribers, width):
    """Koen, 16 October 2026, "b, en gelieve de lijst zo breed te maken als de nieuwe
    lijstschermen via de kit": the content is as wide as Personen's (a `list_page`),
    and where only one of the two optional columns fits, it is Bron."""
    page = _open(browser, width)
    try:
        here = page.evaluate(_SHOWN)
        page.goto("/admin/personen")
        pagina_klaar(page)
        kit = page.evaluate(
            "Math.round(document.querySelector('.admin-content').getBoundingClientRect().width)"
        )
        print(
            f"MEASURE {width}: content {here['content']} (Personen {kit}), "
            f"Bron {here['bron']}, Voornaam {here['voornaam']}"
        )
        assert here["content"] == kit, "the list is narrower than the kit's list screens"
        assert here["bron"] or not here["voornaam"], "Voornaam shows where Bron does not"
    finally:
        page.close()


_BREAKS = """() => [...document.querySelectorAll('[data-subscriber-row] [data-cell=name]')].map(td => {
  const [before, after] = [...td.childNodes].filter(n => n.nodeType === 3);
  const tops = node => { const r = document.createRange(); r.selectNodeContents(node);
                         return [...r.getClientRects()].map(x => Math.round(x.top)); };
  return {text: td.innerText, before: before && before.textContent,
          beforeTops: before ? [...new Set(tops(before))] : [], afterTops: after ? tops(after) : []};
})"""


def test_an_address_breaks_after_the_at_on_a_phone(browser, subscribers):
    """The master CLI's eye on the 390 px print (16 October 2026): an address broke
    inside a word ("…@example.co" / "m"), its cell beside the row's action. It may
    break after the "@" (`<wbr>`) and nowhere inside the part before it.

    Broken on purpose (16 October 2026, put back): the `<wbr>` taken out of
    `_nb_abonnees.html` → the address is one text node and the test is red."""
    page = _open(browser, 390)
    try:
        cells = [c for c in page.evaluate(_BREAKS) if subscribers in c["text"]]
        print(f"MEASURE 390: {cells}")
        assert len(cells) == 3
        for cell in cells:
            assert cell["before"] and cell["before"].endswith("@"), cell
            assert len(cell["beforeTops"]) == 1, f"the part before the @ wraps: {cell}"
            assert min(cell["afterTops"]) > cell["beforeTops"][0], f"no break at the @: {cell}"
    finally:
        page.close()


def test_unsubscribe_and_delete_through_the_browser(browser, subscribers):
    tag = subscribers
    page = _open(browser, 1440)
    try:
        confirmed = _row(page, f"bevestigd-{tag}@example.com")
        confirmed.locator("[data-row-action]").click()
        # The in-app question (#595), not the browser's confirm.
        page.get_by_role("button", name="Bevestigen").click()
        expect(confirmed.locator("[data-row-action]")).to_have_count(0)

        doomed = _row(page, f"weg-{tag}@example.com")
        doomed.locator("[data-row-menu-trigger]").click()
        doomed.locator("[data-row-menu] button", has_text="Verwijderen").click()
        page.get_by_role("button", name="Bevestigen").click()
        expect(_row(page, f"weg-{tag}@example.com")).to_have_count(0)
    finally:
        page.close()
