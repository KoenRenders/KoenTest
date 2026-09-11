"""#878 — the design system leaves the admin bar but not the application.

Koen: *"Are you taking the design-system menu line out? You get there through 'Info'."*

The bar carried fifteen items, fourteen of which are screens where a board member does
work. `/admin/design-system` is reference material about buttons, colours and spacing —
useful while building, not while running an association.

**"Out of the menu" is not "gone", and that difference is what these tests hold.** The route
stays, behind `require_admin_ui`, and `admin_info.html` already has an *Openen* button to it.
Without a test on that, the next person removes the route as well because nothing points at
it any more. The deeper checks on that route — that it renders the whole kit, and refuses
without a session — live in `test_design_system_pagina.py`; this file is about the bar.

Broken on purpose to check that these tests can go red: the entry put back into `_ADMIN_NAV`
→ the first two fall over; and the *Openen* button removed from `admin_info.html` → the last
one falls over, with the page then unreachable from the interface.
"""
from pathlib import Path

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.ui import admin_nav

pytestmark = pytest.mark.ui_serverrendered

ROOT = Path(__file__).resolve().parents[1]


def _admin_session(client, db, email="ds-bar@example.com"):
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(email))


def test_the_bar_no_longer_offers_the_design_system():
    hrefs = [item["href"] for item in admin_nav("/admin/werkbank")]

    assert "/admin/design-system" not in hrefs
    assert "/admin/info" in hrefs, (
        "Info is weg — en dat is juist de weg naar het design system")
    assert len(hrefs) >= 10, f"de balk telt nog maar {len(hrefs)} items — te veel weg"


def test_the_page_still_opens_and_its_bar_renders_normally(client, db_session):
    """De kern van "uit het menu, niet weg".

    En het detail waar dit op kan stukvallen: `design_system_ui.py` roept
    `admin_nav("/admin/design-system")` aan om het actieve item te markeren. Dat item
    bestaat niet meer, dus er is geen actief item — de balk hoort dan gewoon te renderen
    in plaats van leeg te vallen.
    """
    _admin_session(client, db_session)

    resp = client.get("/admin/design-system")

    assert resp.status_code == 200, resp.text[:200]
    for label in ("Werkbank", "Activiteiten", "Info"):
        assert label in resp.text, f"{label} ontbreekt in de balk op deze pagina"
    assert 'href="/admin/design-system"' not in resp.text.split("</nav>")[0], (
        "de balk verwijst nog naar zichzelf")


def test_none_of_the_bar_items_is_marked_active_here():
    """Geen actief item is een geldige toestand; één verkeerd actief item niet."""
    items = admin_nav("/admin/design-system")

    assert items, "de balk is leeg"
    assert not [i for i in items if i["active"]], (
        f"er staat toch iets actief: {[i['href'] for i in items if i['active']]}")


def test_info_still_links_to_it(client, db_session):
    """Zonder deze weg is de pagina onbereikbaar vanuit de interface, en dan is ze in de
    praktijk wél weg."""
    _admin_session(client, db_session, "ds-info@example.com")

    resp = client.get("/admin/info")

    assert resp.status_code == 200
    assert 'href="/admin/design-system"' in resp.text, (
        "Info verwijst niet meer naar het design system")
