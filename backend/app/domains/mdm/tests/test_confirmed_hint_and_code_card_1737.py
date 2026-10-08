"""Two finishing points of CR-22 (#1737; Koen, 8 October 2026).

- **The hint under a person's e-mail addresses on the household screen** said
  "Met elk van deze adressen kan dit lid inloggen, en de nieuwsbrief gaat naar
  allemaal." Since #1711 a waiting address neither signs in nor gets the
  newsletter, so the screen promised what no longer holds. It says "bevestigd"
  now, twice.
- **The code page of a waiting address** stands on the card of the sign-in
  screens (`_sign_in_card.html`): one width for the three sister screens, set
  in one place. The width itself is measured in the browser
  (`tests_e2e/test_confirm_address.py`); here: the page uses that card.

Red (each restored after): the old sentence put back → the hint test names it;
`card.sign_in_card()` replaced by `ui.card()` in `confirm_address.html` → the
page carries no `data-sign-in-card`.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mdm.api import new_contact_detail
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family

pytestmark = pytest.mark.ui_serverrendered

EMAIL = "lid-1737@example.com"
WAITING = "wacht-1737@example.com"


def test_the_household_screen_promises_only_what_a_confirmed_address_does(client, db_session):
    household, _person = create_test_family(db_session, email=EMAIL)
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    page = client.get(f"/admin/leden/gezin/{household.id}")
    assert page.status_code == 200, page.text[:300]
    assert (
        "Met elk bevestigd adres kan dit lid inloggen, "
        "en de nieuwsbrief gaat naar elk bevestigd adres." in page.text
    )
    assert "Met elk van deze adressen" not in page.text and "naar allemaal" not in page.text
    # The rest of the hint stays.
    assert "Een gewijzigde tekst bewaar je met Opslaan" in page.text


def test_the_code_page_stands_on_the_card_of_the_sign_in_screens(client, db_session):
    _household, person = create_test_family(db_session, email=EMAIL)
    row = new_contact_detail(
        db_session, person, "EMAIL", WAITING, is_primary=False, confirmed=False
    )
    db_session.add(row)
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(EMAIL))
    code_page = client.get(f"/mijn/e-mailadres/{row.id}/bevestigen")
    assert code_page.status_code == 200, code_page.text[:300]
    sign_in = client.get("/aanmelden")
    for name, page in (("code page", code_page), ("Inloggen", sign_in)):
        assert page.text.count("data-sign-in-card") == 1, f"{name}: not on the shared card"
    # The step and its address are inside that card.
    card = code_page.text[code_page.text.index("data-sign-in-card") :]
    assert "data-confirm-address" in card and 'hx-post="/aanmelden/code"' in card
