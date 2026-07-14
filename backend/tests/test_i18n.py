"""Taalbeleid-fundament (#407-T): catalogus compileert en _() volgt de
actieve taal (passthrough voor onbekende msgids)."""
from pathlib import Path


def test_catalogus_compileert():
    """De lint-/CI-gate: elke .po in app/locales moet compileren."""
    from babel.messages.mofile import write_mo
    from babel.messages.pofile import read_po

    locales = Path(__file__).resolve().parents[1] / "app" / "locales"
    po_files = list(locales.glob("*/LC_MESSAGES/messages.po"))
    assert po_files, "geen catalogus gevonden (draai scripts/i18n.sh)"
    for po in po_files:
        with open(po, "rb") as fh:
            catalog = read_po(fh)
        import io
        write_mo(io.BytesIO(), catalog)  # faalt bij een kapotte catalogus


def test_gettext_passthrough_en_context():
    from app.i18n import _, current_locale

    assert _("Onbekende tekst blijft zichzelf") == "Onbekende tekst blijft zichzelf"
    token = current_locale.set("nl_BE")
    try:
        assert _("Nog steeds passthrough") == "Nog steeds passthrough"
    finally:
        current_locale.reset(token)


def test_templates_kennen_gettext(client):
    # de Jinja-omgeving heeft de i18n-extensie: {{ _("...") }} werkt
    from app.ui import templates

    tpl = templates.env.from_string('{{ _("Hallo") }}')
    assert tpl.render() == "Hallo"
