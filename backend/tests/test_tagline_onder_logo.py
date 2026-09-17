"""No tagline under a logo that already carries it (#1001).

Koen, 17 September 2026, after uploading the SVG logo of Raak Millegem: the logo
holds the name and the tagline, and the header repeated the tagline as text.

With a logo the visible tagline goes; it moves into the logo's alt so a screen
reader still reads it. The <title> keeps it either way — that is text, not image.

Broken to see it red (measured): the tagline line moved back outside the
logo/wordmark choice in `site_base.html` → the first test fails.
"""
import re

from tests.test_footer_branding import _render

LEUZE = "Bruisende buurt"
KOPREGEL = f'font-medium text-yellow-300">{LEUZE}</span>'


def _header(html: str) -> str:
    return re.search(r"<header\b.*?</header>", html, re.S).group(0)


def test_with_a_logo_the_tagline_is_in_the_alt_and_not_as_text():
    html = _render(site_tagline=LEUZE, site_logo_url="/api/v1/media/7")
    kop = _header(html)

    assert KOPREGEL not in kop
    assert f'alt="Raak Voorbeeld — {LEUZE}"' in kop
    assert kop.count(LEUZE) == 1, "the tagline appears in the header outside the alt"


def test_without_a_logo_the_tagline_stays_as_today():
    kop = _header(_render(site_tagline=LEUZE, site_logo_url=None))
    assert KOPREGEL in kop


def test_the_title_carries_the_tagline_in_both_cases():
    for logo in ("/api/v1/media/7", None):
        html = _render(site_tagline=LEUZE, site_logo_url=logo)
        titel = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
        assert f"Raak Voorbeeld — {LEUZE}" in titel, logo


def test_a_logo_without_tagline_has_the_name_as_alt():
    kop = _header(_render(site_tagline="", site_logo_url="/api/v1/media/7"))
    assert 'alt="Raak Voorbeeld"' in kop
