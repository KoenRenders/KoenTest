"""Omgevingsbanner blijft staan bij het scrollen (#610) — in the back office.

De banner (#464) stond als losse div vóór het sticky element en scrolde dus weg —
je keek daarna naar een scherm dat niet van productie te onderscheiden was, precies
wat de banner moet voorkomen. In the back office the banner is sticky itself and
the element under it starts at the banner's height.

On the public shell #1588 (CR-11 pilot B) decided otherwise: the banner stands in
the document flow above the header and scrolls away, and the header sticks at
y 0 through its CSS class (`.site-header`), with or without a banner.

De val die deze test afdekt: op PROD is er géén banner, dus daar moet de offset weer
0 zijn. Anders staat er op productie een gat van 24px waar de inhoud onder de header
door scrolt. De opmaak zelf toetsen we niet — enkel dat de twee standen kloppen.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_serverrendered

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "ui" / "templates"

BASIS = dict(
    nav_pages=[],
    sponsors=[],
    gebruiker=None,
    current_year=2026,
    chat_enabled=False,
    canonical_url=None,
    base_url="",
    site_name="Raak Voorbeeld",
    site_tagline="",
    site_header_color=None,
    facebook_url=None,
    instagram_url=None,
    tiktok_url=None,
    actief="dashboard",
    admin_nav=[],
)


def _render(schil: str, omgeving: str) -> str:
    # #889: één plek voor de globals die een schil nodig heeft. Deze vier regels stonden
    # in twee bestanden en vielen bij élke nieuwe global opnieuw om — eerst bij #773
    # (`statisch`), daarna bij #889 (`path_for`). Zie tests/_shell_env.py.
    from tests._shell_env import bare_shell_env

    env = bare_shell_env()
    return env.get_template(schil).render(**BASIS, omgeving=omgeving)


# The banner carries `sticky top-0` itself, so "is top-0 in the HTML?" says
# nothing. We test the class of the element under it.
@pytest.mark.parametrize(
    "schil,sticky_aan,sticky_uit",
    [
        ("admin_base.html", "admin-sidebar top-6", "admin-sidebar top-0"),
    ],
)
def test_banner_op_hdev_duwt_het_sticky_element_omlaag(schil, sticky_aan, sticky_uit):
    html = _render(schil, "hdev")
    assert "testomgeving (geen productie)" in html
    assert "sticky top-0 z-50 h-6" in html, "de banner is zelf niet sticky"
    assert sticky_aan in html
    assert sticky_uit not in html


@pytest.mark.parametrize(
    "schil,sticky_uit",
    [
        ("admin_base.html", "admin-sidebar top-0"),
    ],
)
def test_op_prod_geen_banner_en_dus_geen_offset(schil, sticky_uit):
    """Zonder deze regel krijgt productie een gat van 24px onder de header."""
    html = _render(schil, "prod")
    assert "testomgeving" not in html
    assert sticky_uit in html
    assert "top-6" not in html


# ── The public shell: the banner in the document flow (#1588) ────────────────

SITE_HEADER = '<header class="site-header" :inert="menu">'


def _site_header_rule() -> str:
    css = (Path(__file__).resolve().parents[2] / "scripts" / "build-css.sh").read_text()
    rules = re.findall(r"(?m)^\.site-header\{([^}]*)\}", css)
    assert len(rules) == 1, f"expected one .site-header rule, found {len(rules)}"
    return rules[0]


def test_on_the_public_shell_the_banner_stands_in_the_flow_above_the_header():
    """#1588: the banner is not sticky on the public site and pushes nothing down.

    Until then the banner was `sticky top-0 z-50` and the header started under it
    (`top-6`). Now the banner scrolls away and the header sticks at y 0.
    """
    html = _render("site_base.html", "hdev")
    banner = re.search(r"<div data-env-banner[^>]*>([^<]*)</div>", html)
    assert banner, "the banner is not rendered on HDEV"
    assert "HDEV — testomgeving (geen productie)" in banner.group(1)
    assert "sticky" not in banner.group(0) and "top-0" not in banner.group(0)
    assert html.count("data-env-banner") == 1
    assert SITE_HEADER in html
    assert html.index("data-env-banner") < html.index(SITE_HEADER), "the banner stands above"
    assert "top-6" not in html, "an offset for the banner's height is back"


def test_on_the_public_shell_the_header_is_the_same_on_prod():
    """No banner on PROD, and the header's tag is literally the one of HDEV."""
    html = _render("site_base.html", "prod")
    assert "testomgeving" not in html and "data-env-banner" not in html
    assert SITE_HEADER in html
    assert "top-6" not in html


def test_the_public_header_sticks_at_the_top_through_its_css_class():
    """The stickiness left the template (`sticky top-0 z-40`) for `.site-header`."""
    rule = _site_header_rule()
    for declaration in ("position:sticky", "top:0", "z-index:40"):
        assert declaration in rule.split(";"), f"{declaration} is not in .site-header: {rule}"
