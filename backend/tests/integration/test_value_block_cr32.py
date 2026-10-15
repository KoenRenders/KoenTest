"""CR-32 phase 4 (R19, F17): the value block.

A value node holds a code of the closed list; the page renders it from the
settings and the editor shows a chip with what it is now. Changing the setting
changes the page without an edit (AC4).

Broken on purpose (15 October 2026), each red for its own reason: the sixth code
left out of `VALUE_CODES` → the valid-until test fails by name; the renderer
reading the code from a copy made at save time → the setting test fails; the
`tenants` branch of the inline renderer taken out → the sites value renders
nothing; a code outside the list accepted by the schema → the refusal test fails.
"""

import pytest

from app.domains.cms.render import render_document
from app.domains.cms.schema import UnknownAttribute, validate_document

pytestmark = pytest.mark.ui_serverrendered


def _paragraph_with(*inline: dict) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": list(inline)}]}


def _value(code: str) -> dict:
    return {"type": "value", "attrs": {"code": code}}


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


def test_a_value_of_the_list_validates_and_an_unknown_code_is_refused_by_name():
    assert validate_document(_paragraph_with(_value("membership_price_full")))
    with pytest.raises(UnknownAttribute, match="value.code='gratis'"):
        validate_document(_paragraph_with(_value("gratis")))


def test_the_value_is_rendered_from_the_settings_and_follows_them(monkeypatch):
    """AC4: the document holds the code, not the amount — the setting changes,
    the page changes, no edit. The settings are read through the one door the
    renderer uses (`tenant_membership_config`), here a dict the test changes."""
    from decimal import Decimal

    from app.kernel import tenant_config

    config = dict(tenant_config.tenant_membership_config())
    monkeypatch.setattr(tenant_config, "tenant_membership_config", lambda *a, **k: config)
    document = _paragraph_with(_text("Lidgeld: "), _value("membership_price_full"))
    config["price_full"] = Decimal("35.00")
    assert render_document(document) == "<p>Lidgeld: €35,00</p>"
    config["price_full"] = Decimal("40.00")
    assert render_document(document) == "<p>Lidgeld: €40,00</p>"


def test_the_valid_until_year_is_the_end_of_a_new_memberships_period():
    from app.domains.payment.api import membership_valid_period

    year = str(membership_valid_period()[1].year)
    html = render_document(_paragraph_with(_value("membership_valid_until")))
    assert html == f"<p>{year}</p>"


def test_the_sites_value_renders_the_list_the_typed_code_rendered(db_session):
    typed = render_document(_paragraph_with(_text("{{tenants}}")), db_session)
    placed = render_document(_paragraph_with(_value("tenants")), db_session)
    assert placed == typed and "{{tenants}}" not in placed


def test_the_chatbot_reads_a_value_as_its_words(db_session):
    text = render_document(
        _paragraph_with(_text("Het lidgeld is "), _value("membership_price_full")),
        db_session,
        target="text",
    )
    assert text.startswith("Het lidgeld is €")


def test_the_editor_configuration_carries_every_value_with_its_current_words():
    from app.domains.cms import schema

    values = {v["code"]: v for v in schema.schema_for("page")["values"]}
    assert set(values) == set(schema.VALUE_CODES)
    assert values["membership_price_full"]["value"].startswith("€")
    assert values["membership_valid_until"]["value"].isdigit()
