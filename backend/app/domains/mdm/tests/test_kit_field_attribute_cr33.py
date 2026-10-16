"""The kit field reads its label from the register, and the other readers follow it (CR-33 T2, T3).

Each test can go red for its own reason: `attribute=` rendering the key instead of the label,
both `label=` and `attribute=` accepted, an entry without a label accepted, and a reader that
types its own word and so ignores a renamed entry.
"""

import dataclasses

import pytest

from app.kernel import attributes as reg
from app.ui import templates

FIELD = '{% import "_macros.html" as ui %}{{ ui.field("x", __ARGS__) }}'


def _render(arguments: str) -> str:
    return templates.env.from_string(FIELD.replace("__ARGS__", arguments)).render()


def test_a_field_with_an_attribute_shows_the_registers_label():
    html = _render('attribute="mdm.person.first_name", edit=True')
    assert "Voornaam" in html
    assert "mdm.person.first_name" not in html, "the key is no text a person reads"


def test_a_field_with_a_typed_label_is_unchanged():
    assert "Zoek" in _render('_("Zoek"), edit=True')


def test_a_label_and_an_attribute_together_are_refused():
    with pytest.raises(ValueError, match="not both"):
        _render('_("Voornaam"), attribute="mdm.person.first_name"')


def test_an_attribute_without_a_label_or_without_an_entry_is_refused():
    with pytest.raises(ValueError, match="no label"):
        _render('attribute="activities.activity_organiser.email_override"')  # no label yet
    with pytest.raises(LookupError, match="known keys"):
        _render('attribute="mdm.person.nothing"')


def test_a_renamed_entry_moves_every_reader(monkeypatch):
    """One source: rename two entries and the kit field and the changes list follow; nothing
    keeps a word of its own. (The export header and the mails call `attribute(key).text`, the
    call this test makes.)"""
    from app.domains.mdm.change_lines import person_field_label

    registry = dict(reg._REGISTRY)
    old = {
        key: registry.pop(key) for key in ("mdm.person.first_name", "payment.payment_record.method")
    }
    monkeypatch.setattr(reg, "_REGISTRY", registry)
    for key, label in (
        ("mdm.person.first_name", "Roepnaam"),
        ("payment.payment_record.method", "Betaalwijze X"),
    ):
        # built through the constructor: it registers itself, here in the isolated registry
        dataclasses.replace(old[key], label=label)

    assert person_field_label("first_name") == "Roepnaam"
    assert "Roepnaam" in _render('attribute="mdm.person.first_name"')
    assert reg.attribute("payment.payment_record.method").text == "Betaalwijze X"
