"""The sign-in page is named "Inloggen" (#1642; CR-11 Q78, end state §5.3).

Koen, 5 October 2026: the header's link has read "Inloggen" since #1588, and
the page it leads to said "Aanmelden" — the word the site also uses for the
newsletter. The page's heading, its tab title and the button after the code
say "Inloggen" now. The ADDRESS stays `/aanmelden`, and a screen without a
session still leads there with its way back (#1458).

Red against master `850af476`: the heading and the title read "Aanmelden".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_serverrendered

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "domains" / "auth" / "templates"


def _main(html: str) -> str:
    """The page's own content: the footer says "Aanmelden" for the newsletter."""
    return html[html.index("<main") : html.index("</main>")]


def test_the_page_its_title_and_its_heading_say_inloggen(client):
    response = client.get("/aanmelden")
    assert response.status_code == 200
    title = re.search(r"<title>(?:\[\w+\] )?(.*?)</title>", response.text, re.S).group(1)
    assert title.strip() == "Inloggen — Raak"
    main = _main(response.text)
    assert re.search(r"<h1[^>]*>\s*Inloggen\s*</h1>", main)
    assert "Aanmelden" not in main, "the page still says Aanmelden for signing in"


def test_the_button_after_the_code_says_inloggen():
    code_step = (TEMPLATES / "_aanmelden_code.html").read_text()
    buttons = re.findall(r"ui\.btn_primary\(_\('([^']+)'\)\)", code_step)
    assert buttons == ["Inloggen"], buttons
    expired = (TEMPLATES / "login_verlopen.html").read_text()
    assert '_("Opnieuw inloggen")' in expired and 'aanmelden")' not in expired.replace(
        'path_for("/aanmelden")', ""
    )


def test_the_address_stays_and_a_screen_without_a_session_leads_there(client):
    """Only the name changed: the path and the redirect with its way back did not."""
    assert client.get("/inloggen", follow_redirects=False).status_code == 404
    response = client.get("/admin/betalingen", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/aanmelden?terug=")
    expired = (TEMPLATES / "login_verlopen.html").read_text()
    assert 'path_for("/aanmelden")' in expired
