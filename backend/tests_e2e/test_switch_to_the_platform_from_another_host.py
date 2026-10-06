"""E2E: "Werkruimte wisselen" → Platform from a host that is no platform host (#1668).

Found on UAT after v2.13.0: on a department's own domain the switcher opened
the department again. The e2e app has both kinds of host: the one the suite
runs on serves Raak Millegem on every path (no platform host, as a department's
own domain), and `platform.localhost` is the platform host.

Two hosts, two session cookies — a session belongs to one host:

- logged in on both: the platform's back office opens, on the platform host;
- logged in on the department's host only: the platform host asks to log in
  first, with the way back to the choice — never the department's back office.

Red against master: both ended on the department's host, in Raak Millegem's
back office.
"""

import os
import sys
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, PLATFORM, pagina_klaar  # noqa: E402
from tests_e2e.test_switch_to_the_platform import _SIDEBAR  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _page(browser, *hosts: str):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(viewport={"width": 1440, "height": 900})
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    page.context.add_cookies([{"name": "raak_session", "value": session, "url": h} for h in hosts])
    return page


def _choose_the_platform(page) -> None:
    page.goto(BASE + "/admin/werkruimte-wisselen")
    pagina_klaar(page)
    here = page.evaluate(_SIDEBAR)
    assert here["name"] == "Raak Millegem", "the suite's own host is the department's"
    link = page.locator("#main a").filter(has_text="Digital Platform").first
    href = link.get_attribute("href")
    print("MEASURE the platform's link on the department's host", href)
    assert href.startswith(PLATFORM + "/"), f"the platform is linked on this host: {href}"
    link.click()
    page.wait_for_load_state("load")
    pagina_klaar(page)


def test_logged_in_on_both_hosts_the_platform_opens_on_the_platform_host(browser):
    page = _page(browser, BASE, PLATFORM)
    try:
        _choose_the_platform(page)
        assert page.url == PLATFORM + "/admin", page.url
        there = page.evaluate(_SIDEBAR)
        print("MEASURE after the switch", page.url, there["name"])
        assert there["name"] == "Digital Platform"
        assert "/admin/activiteiten" not in there["hrefs"], "this is the department's menu"
    finally:
        page.context.close()


def test_logged_in_on_the_departments_host_only_the_platform_host_asks_to_log_in(browser):
    page = _page(browser, BASE)
    try:
        _choose_the_platform(page)
        url = urlsplit(page.url)
        print("MEASURE after the switch without a session there", page.url)
        assert f"{url.scheme}://{url.netloc}" == PLATFORM, "the browser stayed on the department"
        assert url.path == "/aanmelden"
        back = parse_qs(url.query).get("terug", [""])[0]
        assert back.startswith("/admin/werkruimte-wisselen/"), (
            f"the way back is not the choice that was made: {back}"
        )
        assert page.locator("#admin-zijbalk").count() == 0, "a back office opened"
    finally:
        page.context.close()
