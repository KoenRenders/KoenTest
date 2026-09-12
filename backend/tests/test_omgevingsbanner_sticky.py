"""Omgevingsbanner blijft staan bij het scrollen (#610).

De banner (#464) stond als losse div vóór het sticky element en scrolde dus weg —
je keek daarna naar een scherm dat niet van productie te onderscheiden was, precies
wat de banner moet voorkomen. Hij is nu zelf sticky en het element eronder start op
de bannerhoogte.

De val die deze test afdekt: op PROD is er géén banner, dus daar moet de offset weer
0 zijn. Anders staat er op productie een gat van 24px waar de inhoud onder de header
door scrolt. De opmaak zelf toetsen we niet — enkel dat de twee standen kloppen.
"""


from jinja2 import Environment, FileSystemLoader
from pathlib import Path

import pytest


pytestmark = pytest.mark.ui_serverrendered

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "ui" / "templates"

BASIS = dict(nav_pages=[], sponsors=[], gebruiker=None, footer_block=None,
             current_year=2026, chat_enabled=False, canonical_url=None,
             base_url="", site_name="Raak Voorbeeld", site_tagline="",
             facebook_url=None, instagram_url=None, tiktok_url=None,
             actief="dashboard", admin_nav=[])


def _render(schil: str, omgeving: str) -> str:
    # #889: één plek voor de globals die een schil nodig heeft. Deze vier regels stonden
    # in twee bestanden en vielen bij élke nieuwe global opnieuw om — eerst bij #773
    # (`statisch`), daarna bij #889 (`path_for`). Zie tests/_shell_env.py.
    from tests._shell_env import bare_shell_env

    env = bare_shell_env()
    return env.get_template(schil).render(**BASIS, omgeving=omgeving)


# Let op de z-index in de site_base-waarden: de banner draagt zelf `sticky top-0`,
# dus "staat top-0 in de HTML?" zegt niets. We toetsen op de klasse van het element
# eronder — de header is z-40, de banner z-50.
@pytest.mark.parametrize("schil,sticky_aan,sticky_uit", [
    ("site_base.html", 'sticky top-6 z-40', 'sticky top-0 z-40'),
    ("admin_base.html", 'md:top-6 md:h-[calc(100vh-1.5rem)]', 'md:top-0 md:h-screen'),
])
def test_banner_op_hdev_duwt_het_sticky_element_omlaag(schil, sticky_aan, sticky_uit):
    html = _render(schil, "hdev")
    assert "testomgeving (geen productie)" in html
    assert "sticky top-0 z-50 h-6" in html, "de banner is zelf niet sticky"
    assert sticky_aan in html
    assert sticky_uit not in html


@pytest.mark.parametrize("schil,sticky_uit", [
    ("site_base.html", 'sticky top-0 z-40'),
    ("admin_base.html", 'md:top-0 md:h-screen'),
])
def test_op_prod_geen_banner_en_dus_geen_offset(schil, sticky_uit):
    """Zonder deze regel krijgt productie een gat van 24px onder de header."""
    html = _render(schil, "prod")
    assert "testomgeving" not in html
    assert sticky_uit in html
    assert "top-6" not in html
