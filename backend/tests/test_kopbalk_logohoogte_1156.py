"""The logo's height and the band's height each have one home (#1156, #1588).

Koen asked during his HDEV round how much larger the logo could be without
making the band higher (#1156). Until #1588 the answer was a derivation in the
template: two variables on the header's row (`--balk`, `--lucht`) and the logo's
height as what was left.

**#1588 (CR-11 pilot B) moved the geometry out of the template.** The band is
64 px on a phone, 112 px from 768 px and 80 px from 1 200 px — the grid
`.site-header-grid` in `scripts/build-css.sh` — and the logo is 48 px at every
width (`.site-brand img`). What a server test can still guard is the property
#1156 was about: each measure stands ONCE, in the CSS, and the template carries
no second number beside it that would drift the day someone changes the rule.
That the band is that high on the screen is for a browser to measure —
`tests_e2e/test_kopbalk_logohoogte.py`.

**#1621 (Koen, 5 October 2026; CR-11 Q69) gave the trade of #1156 back.** With
#1588 these tests were rewritten to "48 px at every width" and kept only an
upper bound — the logo plus 16 px had to FIT the lowest band (`<=`). So the
logo shrank from 64 to 48 px on a desktop while everything here stayed green:
nothing said the logo takes the room its row gives. Now each logo height EQUALS
its row minus 2 × 8 px: 48 in the rows of 64, 64 in the band of 80.

What turns these tests red: a `class` or `style` on the logo's `<img>` (a
second number beside the rule), a size utility or a per-branch class on the
header's row, a fourth or a changed height in the grid's rules, a logo height
that is not its row minus 16 px (proven: the 64 px rule removed, and set to
56 px).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_footer_branding import _render

pytestmark = pytest.mark.ui_serverrendered

LOGO = "/api/v1/media/7"
BUILD_CSS = Path(__file__).resolve().parents[2] / "scripts" / "build-css.sh"
#: A Tailwind utility that sets a height, a width or a vertical padding.
SIZE_UTILITY = re.compile(r"(?<![\w-])(?:md:|lg:|sm:)?(?:min-|max-)?(?:h|w|py|pt|pb|size)-\S+")


def _header(html: str) -> str:
    return re.search(r"<header\b.*?</header>", html, re.S).group(0)


def _row(html: str) -> str:
    """The opening tag of the row that holds the brand, the links and the account."""
    found = re.search(r"<div class=\"[^\"]*\bsite-header-grid\b[^\"]*\"[^>]*>", _header(html))
    assert found, "the header's row was not found"
    return found.group(0)


def _brand(html: str) -> str:
    found = re.search(r"<a\b[^>]*data-site-brand[^>]*>.*?</a>", _header(html), re.S)
    assert found, "the brand link was not found"
    return found.group(0)


def _css_rules(selector: str) -> list[str]:
    """Every declaration block of exactly `selector` in the shell's CSS."""
    css = BUILD_CSS.read_text()
    rules = re.findall(r"(?m)^\s*" + re.escape(selector) + r"\{([^}]*)\}", css)
    assert rules, f"no rule for {selector} in build-css.sh — the gate would look nowhere"
    return rules


def _px(rule: str, prop: str) -> int:
    found = re.search(r"(?:^|;)" + prop + r":(\d+)px(?:;|$)", rule)
    assert found, f"{prop} is not a pixel value in: {rule}"
    return int(found.group(1))


def test_the_logo_height_stands_in_the_css_and_nowhere_else():
    """The logo's height is `.site-brand img{height:…}` — the base rule and the
    one from 1 200 px (#1621) — and nothing else.

    #1588 replaced the `calc(var(--balk) - 2 * var(--lucht))` on the `<img>` by
    the rule; a size utility on the image would be a second number beside it.
    """
    rule, wide = _css_rules(".site-brand img")
    assert (_px(rule, "height"), _px(wide, "height")) == (48, 64)
    assert "width:auto" in rule, "the logo keeps its proportions"

    img = re.search(r"<img\b[^>]*>", _brand(_render(site_logo_url=LOGO)))
    assert img, "the logo is not in the brand link"
    assert f'src="{LOGO}"' in img.group(0)
    assert "class=" not in img.group(0) and "style=" not in img.group(0), (
        f"the logo carries its own size beside the CSS rule: {img.group(0)}"
    )


def test_the_band_heights_stand_once_and_the_logo_fits():
    """64 / 112 / 80 px: one height per breakpoint, and the logo fits the lowest.

    The numbers are the invariant of block 11, so they stand in the grid's
    rules and nowhere in the template — the `--balk` / `--lucht` variables of
    #1156 are gone with the padding they were derived from.
    """
    rules = _css_rules(".site-header-grid")
    assert [_px(rule, "height") for rule in rules] == [64, 112, 80]
    assert "grid-template-rows:64px 48px" in rules[1], "two rows from 768 px"

    # #1621: the logo takes what its row gives — EQUAL to the row minus 2 × 8 px,
    # not merely fitting it. The row of the logo per breakpoint: 64 on a phone,
    # the first row of 64 from 768 px, the band of 80 from 1 200 px.
    phone, wide = (_px(rule, "height") for rule in _css_rules(".site-brand img"))
    first_row = int(re.search(r"grid-template-rows:(\d+)px 48px", rules[1]).group(1))
    assert phone == _px(rules[0], "height") - 16 == first_row - 16, (
        f"the logo is {phone} px in a row of {_px(rules[0], 'height')} and of {first_row} px"
    )
    assert wide == _px(rules[2], "height") - 16, (
        f"the logo is {wide} px in the band of {_px(rules[2], 'height')} px from 1 200 px"
    )
    css = BUILD_CSS.read_text()
    assert css.index(".site-brand img{height:64px}") > css.index("@media (min-width:1200px){"), (
        "the 64 px rule stands outside the 1 200 px block"
    )

    source = _render(site_logo_url=LOGO)
    for old in ("--balk", "--lucht", "h-10 md:h-12", "py-4 flex"):
        assert old not in _header(source), f"{old} is back in the header"
    assert not SIZE_UTILITY.search(_row(source)), (
        f"the row sets a size beside the CSS grid: {_row(source)}"
    )


def test_the_band_is_the_same_with_and_without_a_logo():
    """Until #1588 the wordmark branch had its own padding (`py-4`), and so its
    own band height — 71 px against 80 with a logo. Now the grid sets the
    height, so the row is literally the same element in both branches.
    """
    with_logo = _row(_render(site_logo_url=LOGO))
    without = _row(_render(site_logo_url=None))

    assert with_logo == without == '<div class="site-container site-header-grid">'
    brand = _brand(_render(site_logo_url=None))
    assert "<img" not in brand and "Raak Voorbeeld</span>" in brand, (
        "without a logo the name stands in the brand link"
    )


def test_het_aanraakvlak_van_de_menuknop_hangt_niet_aan_de_padding():
    """#804: 44 px is de ondergrens voor een vinger.

    The button stands in the same row as the logo. Its size is its own
    (`w-11 h-11`), not something the row's geometry gives it — and the CSS
    class it carries for the grid sets no size either.
    """
    kop = _header(_render(site_logo_url=LOGO))

    # Up to the closing tag, not to the first `>`: the click handler holds an arrow.
    knop = re.search(r"<button\b[^<]*?data-menu-button.*?</button>", kop, re.S)
    assert knop, "de menuknop is niet gevonden"
    klassen = re.search(r'class="([^"]*)"', knop.group(0)).group(1).split()
    assert "w-11" in klassen and "h-11" in klassen, (
        "de menuknop draagt haar 44px-aanraakvlak niet meer"
    )
    assert 'aria-label="Menu"' in knop.group(0)
    for rule in _css_rules(".site-menu-button"):
        assert not re.search(r"(?:^|;)(?:min-|max-)?(?:width|height):", rule), (
            f"the grid class overrides the button's own size: {rule}"
        )
