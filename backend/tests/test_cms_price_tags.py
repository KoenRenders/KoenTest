"""CMS-prijsplaceholders leveren een volledig bedrag, inclusief euroteken (#579).

Het symbool hoort in de placeholder en niet in de CMS-tekst: een redacteur die
zelf "€" moet typen, kan het vergeten — en dat gebeurde ook. Op HDEV las de
publieke lidmaatschapstekst "bedraagt 35,00 … 17,50" terwijl PROD "€35,00"
toonde. Deze test legt het formaat vast zodat de regressie niet terugkeert.
"""
import pytest

from app.domains.cms.render import _format_price, render_cms_content


def test_format_price_bevat_euroteken_en_kommadecimaal():
    assert _format_price(35.0) == "€35,00"
    assert _format_price(17.5) == "€17,50"


def test_format_price_gebruikt_geen_punt_als_decimaalteken():
    """Belgische notatie: de komma scheidt, nooit de punt."""
    assert "." not in _format_price(12.34)


@pytest.mark.parametrize("code", ["membership_price_full", "membership_price_half"])
def test_gerenderde_prijstag_bevat_euroteken(db_session, code):
    """Het volledige renderpad — placeholder in CMS-inhoud → publieke HTML."""
    gerenderd = render_cms_content(f"<p>Het lidgeld bedraagt {{{{{code}}}}}.</p>")

    assert "€" in gerenderd, f"{code} rendert zonder euroteken"
    assert f"{{{{{code}}}}}" not in gerenderd, "placeholder is niet vervangen"
