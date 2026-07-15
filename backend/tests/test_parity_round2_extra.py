"""Ronde 2 (#476), kleine wins: betaling-geannuleerd retry + geruststelling,
relatietype-label-filter."""
from app.ui import _relatielabel


def test_relatielabel_maps_codes():
    assert _relatielabel("HOOFDLID") == "Hoofdlid"
    assert _relatielabel("PARTNER") == "Partner"
    assert _relatielabel("KIND") == "(meerderjarig) kind"
    assert _relatielabel(None) == "—"
    assert _relatielabel("ONBEKEND") == "ONBEKEND"


def test_betaling_geannuleerd_has_retry_and_reassurance(client):
    html = client.get("/betaling/geannuleerd").text
    assert "Opnieuw proberen" in html
    assert "bewaard" in html


def test_betaling_succes_single_button(client):
    html = client.get("/betaling/succes").text
    assert "Betaling ontvangen" in html
    assert "Opnieuw proberen" not in html
