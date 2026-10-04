"""E2E, CR-19 C6 test 13 (#1477), second flow: an association — every module on —
shows what it showed before the module switch existed (R2).

What is compared is what a module could take away: the admin menu (link and
label), the dashboard tiles (their labels), and the public home (navigation,
headings, buttons, footer). It is compared with a snapshot recorded on the old
code: tag `v2.12.0`, commit `55f30627`, the last release before CR-19's first
phase (#1475), the one PROD ran when this was written.

Normalised, so it compares structure and not data: activity names and years are
masked, a value of a tile is left out, the copyright year is masked, and a list
shown twice (the phone and the wide menu) is read as a set. The workspace brand
link at the top of the sidebar is left out: CR-11 (#1482) gave it an initial,
which is not a module's doing.

Recording: run this file as a script in an e2e container of the old code; it
prints the snapshot. `python tests_e2e/test_association_unchanged_by_modules.py`.
Proven red (locally, on this branch): the snapshot with "Nieuwsbrief" removed
from the home buttons fails with that line in the diff.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SNAPSHOT = Path(__file__).parent / "snapshots" / "association_v2_12_0.json"

_MENU = """() => [...document.querySelectorAll('aside a[href^="/admin"], nav a[href^="/admin"]')]
  .map(a => [a.getAttribute('href'), a.textContent.replace(/\\s+/g, ' ').trim()])"""
_HOME = """() => ({
  nav: [...document.querySelectorAll('header a')].map(a => a.textContent.replace(/\\s+/g, ' ').trim()),
  headings: [...document.querySelectorAll('main h1, main h2, main h3, footer h2, footer h3')]
    .map(h => h.textContent.replace(/\\s+/g, ' ').trim()),
  buttons: [...document.querySelectorAll('main a, main button')]
    .map(a => a.textContent.replace(/\\s+/g, ' ').trim()).filter(t => t && t.length < 40),
  footer: (document.querySelector('footer') || {innerText: ''}).innerText
    .split('\\n').map(s => s.trim()).filter(Boolean),
})"""
#: The changes since v2.12.0 that are decisions, not a module taking something
#: away — applied to the recording before the comparison, so the recording stays
#: what v2.12.0 showed and every change is named here, with its issue.
#: #1535 (Koen): platform administration is the platform's menu; a tenant
#: workspace has its own organisation and settings in their place.
#: #1562 (K8, Koen): the assistant has no page and no menu item any more — it is
#: the panel behind the top bar's trigger. `None` is an item that left.
DELIBERATE_MENU_CHANGES: dict[str, str | None] = {
    "/admin/organisaties Organisaties": "/admin/organisatie Onze organisatie",
    "/admin/tenants Tenants": "/admin/instellingen Instellingen",
    "/admin/rapporten/raakje AI · Raakje": None,
}

_YEAR = re.compile(r"\b20\d\d\b")
#: A tile's value — a count or an amount — is data, not what a module shows.
_VALUE = re.compile(r"^[€\d\s.,%-]+$")


def _activity_names() -> set[str]:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity

    db = SessionLocal()
    try:
        return {a.name for a in db.query(Activity).all() if a.name}
    finally:
        db.close()


def _mask(text: str, names: set[str]) -> str:
    for name in sorted(names, key=len, reverse=True):
        text = text.replace(name, "<activiteit>")
    return _YEAR.sub("<jaar>", text)


def extract(browser, base: str, session: str) -> dict:
    """The association as the snapshot holds it, from a running server."""
    from tests_e2e.schermen import login_met_sessie, pagina_klaar

    names = _activity_names()
    page = browser.new_page(base_url=base, viewport={"width": 1440, "height": 1000})
    try:
        login_met_sessie(page, session)
        page.goto("/admin")
        pagina_klaar(page)
        menu = [
            f"{href} {label}" for href, label in page.evaluate(_MENU) if "Werkruimte" not in label
        ]
        lines = [s.strip() for s in page.locator("main").inner_text().split("\n")]
        tiles = [
            s
            for s in lines
            if s
            and not _VALUE.match(s)
            and s not in ("Rapport", "Dashboard")
            and not s.startswith("Cijfers van")
        ]
    finally:
        page.close()
    # The home as a visitor sees it: no session, so no "Admin" or "Uitloggen".
    page = browser.new_page(base_url=base, viewport={"width": 1440, "height": 1000})
    try:
        page.goto("/", wait_until="load")
        pagina_klaar(page)
        home = page.evaluate(_HOME)
    finally:
        page.close()
    return {
        "menu": sorted(set(menu)),
        "dashboard_tiles": tiles,
        "home_nav": sorted({t for t in home["nav"] if t}),
        "home_headings": sorted({_mask(t, names) for t in home["headings"]}),
        "home_buttons": sorted({_mask(t, names) for t in home["buttons"]}),
        "footer": [_mask(t, names) for t in home["footer"]],
    }


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def test_the_association_shows_what_it_showed_on_v2_12_0(browser):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL
    from tests_e2e.schermen import BASE

    before = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    menu = before["shown"]["menu"]
    assert set(DELIBERATE_MENU_CHANGES) <= set(menu), "a deliberate change names no recorded item"
    before["shown"]["menu"] = sorted(
        changed for item in menu if (changed := DELIBERATE_MENU_CHANGES.get(item, item)) is not None
    )
    now = extract(browser, BASE, make_session_value(SEEDED_ADMIN_EMAIL))

    assert set(now) == set(before["shown"]), "the snapshot and the extraction disagree on shape"
    differences = {
        part: {"v2.12.0": before["shown"][part], "now": now[part]}
        for part in now
        if now[part] != before["shown"][part]
    }
    assert not differences, json.dumps(differences, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright

    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL
    from tests_e2e.schermen import BASE

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        shown = extract(b, BASE, make_session_value(SEEDED_ADMIN_EMAIL))
        b.close()
    print(
        json.dumps(
            {"recorded_on": "v2.12.0 (55f30627)", "shown": shown}, ensure_ascii=False, indent=1
        )
    )
