"""The codes the editor's insert menu offers (CR-17; Koen, 12 October 2026:
"a, stap 1 erbij in CR-17"; CR-32 R19).

One list: `insertable_codes` takes what `placeholders()` returns — the list
the Codes card shows — and keeps the values of the closed list, because the
menu inserts a value node. Nothing is added and nothing renamed, so the menu
cannot offer a code the renderer does not replace.

Broken on purpose (13 and 15 October 2026), put back by the reverse edit: the
filter turned off → the first test red: nothing is left out of the menu.
"""

from __future__ import annotations

from app.domains.cms.render import PLACEHOLDER_LABELS
from app.domains.cms.service import insertable_codes, placeholders


def test_the_menu_offers_the_values_of_the_closed_list_and_nothing_else(db_session):
    """CR-32 R19 rewrote this: the menu inserts a value node, which only the
    closed list can be; the form codes and the codes with a part of their own
    stay in the card and keep working as typed text."""
    from app.domains.cms.schema import VALUE_CODES

    card = placeholders(db_session)
    menu = insertable_codes(card)

    assert menu, "the menu offers nothing"
    assert all(entry in card for entry in menu), "the menu names a code the card does not"
    assert [entry["code"].strip("{}") for entry in menu] == list(VALUE_CODES)
    left_out = [entry["code"] for entry in card if entry not in menu]
    assert "{{tenants:raakmillegem}}" in left_out and "{{form:berichten}}" in left_out


def test_the_card_s_list_is_the_renderer_s(db_session):
    """The guard under both: the card's codes are the renderer's own names."""
    assert [entry["code"] for entry in placeholders(db_session)] == [
        f"{{{{{code}}}}}" for code in PLACEHOLDER_LABELS
    ]
