"""The payment-method choice stands once, in the kit (CR-21 phase 0, #1748).

Four screens asked "Online betalen" or "Overschrijving" with the same field call, the
same two options and the same two sentences under them: the registration form, Lid
worden, Lidmaatschap betalen and the design-system page — and the webshop's order page
would have been the fifth. `ui.payment_choice` is the one place now; this gate refuses a
second.

- no template outside `_macros.html` writes the option's words or a field named
  `payment_method` by hand;
- the screens that ask it call `ui.payment_choice(`.

Proven red (8 October 2026), additively: a `{{ ui.field("payment_method", …) }}` added
to `lid_worden.html` → "a payment choice written by hand"; the call in
`_inschrijf_velden.html` renamed → "no longer asks through the kit"; the kit's field
renamed to `pay` → "no longer names its field payment_method" (the pages follow a
change of that name for the words of their button).
"""

import re
from pathlib import Path

import pytest

from tests._bestanden import bestanden

pytestmark = pytest.mark.ui_agnostisch

APP = Path(__file__).resolve().parents[1] / "app"
KIT = "ui/templates/_macros.html"
COMMENT = re.compile(r"\{#.*?#\}", re.S)
BY_HAND = re.compile(r"""field\(\s*["']payment_method["']|_\(["']Online betalen["']\)""")
ASKERS = (
    "domains/activities/templates/_inschrijf_velden.html",
    "domains/membership/templates/lid_worden.html",
    "domains/membership/templates/lidmaatschap_vernieuwen.html",
    "ui/templates/design_system.html",
)


def _sources() -> dict[str, str]:
    files = bestanden(APP.rglob("*.html"), wat="app/**/*.html", minstens=100)
    return {
        p.relative_to(APP).as_posix(): COMMENT.sub("", p.read_text(encoding="utf-8")) for p in files
    }


def test_the_choice_is_written_in_the_kit_and_nowhere_else():
    sources = _sources()
    kit = sources[KIT]
    assert "{% macro payment_choice(" in kit and 'field("payment_method"' in kit, (
        "the kit no longer holds the choice, or no longer names its field payment_method"
    )
    by_hand = sorted(name for name, src in sources.items() if name != KIT and BY_HAND.search(src))
    assert not by_hand, f"a payment choice written by hand — use ui.payment_choice: {by_hand}"


@pytest.mark.parametrize("template", ASKERS)
def test_the_screens_that_ask_it_call_the_kit(template):
    assert "ui.payment_choice(" in _sources()[template], (
        f"{template} no longer asks through the kit"
    )
