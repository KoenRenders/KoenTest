"""The codes the editor's insert menu offers (CR-17; Koen, 12 October 2026:
"a, stap 1 erbij in CR-17").

One list: `insertable_codes` takes what `placeholders()` returns — the list
the Codes card shows — and leaves the form codes out, because the button
block is the way to a form now. Nothing is added and nothing renamed, so the
menu cannot offer a code the renderer does not replace.

Broken on purpose (13 October 2026), put back by the reverse edit: the filter
turned off → the first test red: nothing is left out of the menu.
"""

from __future__ import annotations

from app.domains.cms.render import PLACEHOLDER_LABELS
from app.domains.cms.service import insertable_codes, placeholders


def test_the_menu_offers_the_card_s_codes_without_the_form_codes(db_session):
    card = placeholders(db_session)
    menu = insertable_codes(card)

    assert menu, "the menu offers nothing"
    assert all(entry in card for entry in menu), "the menu names a code the card does not"
    left_out = [entry["code"] for entry in card if entry not in menu]
    assert left_out and all(code.startswith("{{form:") for code in left_out), left_out
    assert not [entry["code"] for entry in menu if "form:" in entry["code"]]


def test_a_code_with_a_part_of_its_own_goes_in_with_its_example(db_session):
    codes = [entry["code"] for entry in insertable_codes(placeholders(db_session))]
    assert "{{tenants:raak}}" in codes
    assert "{{membership_price_full}}" in codes


def test_the_card_s_list_is_the_renderer_s(db_session):
    """The guard under both: the card's codes are the renderer's own names."""
    assert [entry["code"] for entry in placeholders(db_session)] == [
        f"{{{{{code}}}}}" for code in PLACEHOLDER_LABELS
    ]
