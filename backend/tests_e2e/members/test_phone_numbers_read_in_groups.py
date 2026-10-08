"""E2E: a stored phone number reads in groups, and the input keeps what is stored (#1675).

In a browser, because it is what a person reads: the member's own page (Mijn
gezin, on a phone) and the back office's record of the same household show the
number through the kit's field. The household is signed up with the mobile
number as the national import stores it — ten digits without a space.

Red against master: both screens read "0470000000".
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.members.test_household_pages import (  # noqa: E402
    _household,
    _open,
    _remove,
    _session,
    _sign_up,
    browser,  # noqa: F401
)

STORED = "0470000000"
READ = "0470 00 00 00"
_NUMBERS = """() => [...document.querySelectorAll('[data-field$=".mobile"]')].map(f => {
  const shown = f.querySelector('[data-value]'), input = f.querySelector('input');
  return {shown: shown ? shown.innerText.trim() : null, input: input ? input.value : null}; })"""


def test_mijn_gezin_and_the_member_record_read_the_number_in_groups(browser):  # noqa: F811
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = _sign_up(browser, "nummer1675", partner=False)
    try:
        assert _household(email)["persons"]["Hoofd"]["mobile"] == STORED

        page = _open(
            browser, "/leden/gezin", viewport={"width": 390, "height": 844}, session=_session(email)
        )
        read = page.evaluate(_NUMBERS)
        print("MEASURE Mijn gezin at 390, read", read)
        assert read and read[0]["shown"] == READ, read
        assert page.evaluate("document.documentElement.scrollWidth") == 390
        page.goto("/leden/gezin?bewerken=1")
        page.wait_for_selector('[data-field$=".mobile"] input')
        edit = page.evaluate(_NUMBERS)
        assert edit[0]["input"] == STORED, "the input must carry what is stored"
        page.close()

        member_id = _household(email)["member_id"]
        admin = _open(
            browser,
            f"/admin/leden/gezin/{member_id}",
            session=make_session_value(SEEDED_ADMIN_EMAIL),
        )
        # The record shows the household through the member card, not a kit field.
        record = admin.locator("#main").inner_text()
        print(
            "MEASURE the member record reads",
            READ in record,
            "and the stored form",
            STORED in record,
        )
        assert READ in record, "the member record does not show the number in groups"
        assert STORED not in record, "the member record still shows the stored digits"
        admin.close()
        assert _household(email)["persons"]["Hoofd"]["mobile"] == STORED, "reading stored something"
    finally:
        _remove(email)
