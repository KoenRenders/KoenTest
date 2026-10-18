"""The payment's two descriptions name the order too (#1921).

Since CR-21's webshop, `f_payments` reads an order (migration 307): its kind is
"Bestelling" and its label the buyer with the order number. "Soort" and
"Waarvoor" named two kinds; read here from the reports panel, where the text is
the tooltip of the object — not from the source.

"Soort" no longer counts the streams ("hun twee stromen"), so a fourth kind does
not make it untrue again.
"""

from __future__ import annotations

import html

from app.domains.reporting.tests.test_reporting_panel_ui import login
from app.domains.reporting.universe import BY_KEY


def _tooltip(page: str, key: str) -> str:
    text = BY_KEY[key].description
    assert f'title="{html.escape(text)}"' in page, f"{key}'s description is on the panel"
    return text


def test_the_payment_kind_names_the_order_and_counts_no_streams(client, db_session):
    login(client, db_session)
    page = client.get("/admin/rapporten/paneel").text
    text = _tooltip(page, "payment_payable_type")
    for kind in ("lidgeld", "een activiteit", "een bestelling"):
        assert kind in text, (kind, text)
    assert "twee" not in text and "drie" not in text, text


def test_what_is_paid_for_names_the_buyer_and_the_order_number(client, db_session):
    login(client, db_session)
    # A detail shows its description in the list form; elsewhere it says to pick it.
    page = client.get("/admin/rapporten/paneel?layout=detail").text
    text = _tooltip(page, "payment_payable_label")
    assert "de koper en het bestelnummer" in text, text
    assert "de inschrijver en de activiteit" in text, text
    assert "het hoofdlid en het lidmaatschapsjaar" in text, text
