"""E2E #1853 — an e-mail row on a person's card refuses a text that is no address.

The route tests (`mdm/tests/test_email_rows_refuse_what_is_no_address_1853.py`)
hold the rule and the door's answer; this file holds what only a browser can, at
390 px: that the sentence is on the screen, in the card that was saved, in view,
and that what was typed is still there.

What the browser lets through by itself: an e-mail field accepts `naam@domein`
without a dot (its own check asks an @ and something on both sides); the rule
asks a domain. No attribute is taken off here.

The same in Mijn gezin: `test_email_row_in_mijn_gezin_says_why.py`; on the
organisation screen: `test_organisatie_adres_blijft.py`.

Set `E2E_PRINTS` to a folder to keep a print (outside the repository).

Proven red (locally, restored): `EmailAddressInvalid` taken out of mdm's
`says_why_in` → the banner never comes, the page shows its general message.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.members.test_household_cards_say_why import (  # noqa: E402, F401
    _measure,
    _open,
    _partner_card,
    _sideways,
    household,
    page,
)
from tests_e2e.schermen import htmx_stil  # noqa: E402

RULE = "Vul een geldig e-mailadres in."
NO_DOT = "bram@zonderpunt"


def test_a_row_on_a_persons_card_says_why(page, household):  # noqa: F811
    _open(page, household)
    card = _partner_card(page)
    card_id = card.get_attribute("id")
    person = card_id.split("-")[1]
    card.get_by_role("button", name="Bewerken").click()
    card.get_by_role("button", name="+ E-mailadres").click()
    htmx_stil(page)
    row = card.locator(f"#emails-{person} input").last
    row.fill(NO_DOT)
    before = _sideways(page)

    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith(f"/persoon/{person}")
    ) as answered:
        card.get_by_role("button", name="Opslaan").click()

    assert answered.value.status == 422
    _measure(page, f"#{card_id}-melding", f"#{card_id}", RULE, "emailrij-kaart", before)
    # What was typed is still there: the answer is the banner alone.
    assert row.input_value() == NO_DOT
