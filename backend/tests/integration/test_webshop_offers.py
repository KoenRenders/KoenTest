"""The public Webshop (CR-21, phase 2): what it offers and what it does not."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domains.pricing.api import add_prices
from app.domains.product.api import ProductStatus, add_variant, create_product, set_status

pytestmark = pytest.mark.ui_agnostisch


def test_the_webshop_offers_only_on_sale_articles_with_a_price(client, db_session, every_module_on):
    """T18: an article in sale with a price for a size shows; a Concept one and an
    in-sale one without a price do not."""
    on_sale = create_product(db_session, "T-shirt Raak")
    set_status(db_session, on_sale.id, ProductStatus.ON_SALE)
    variant = add_variant(db_session, on_sale.id, "M")
    add_prices(
        db_session,
        product_id=on_sale.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal("15.00"),
        member_amount=None,
    )

    create_product(db_session, "Nog niet klaar")  # stays Concept
    without_price = create_product(db_session, "Zonder prijs")
    set_status(db_session, without_price.id, ProductStatus.ON_SALE)

    page = client.get("/webshop")
    assert page.status_code == 200
    assert "T-shirt Raak" in page.text
    assert "Nog niet klaar" not in page.text
    assert "Zonder prijs" not in page.text


def test_the_product_page_is_only_for_on_sale_articles(client, db_session, every_module_on):
    concept = create_product(db_session, "Concept artikel")

    page = client.get(f"/webshop/{concept.id}")
    assert page.status_code == 404
