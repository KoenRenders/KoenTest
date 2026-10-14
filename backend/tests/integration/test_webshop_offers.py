"""The public Webshop (CR-21, phase 2): what it offers and what it does not.

One rule (H1, H2): an article is on offer when it is in sale and at least one of
its sizes has a price valid today; a member pays the size's member price, anyone
else its regular price (F3). The list and the article page ask the same service,
so each test here is red without the one condition it names.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.pricing.api import add_prices
from app.domains.product.api import (
    ProductStatus,
    add_variant,
    create_product,
    set_status,
)
from app.kernel.clock import belgian_today

pytestmark = pytest.mark.ui_agnostisch

MEMBER_EMAIL = "lid-webshop@example.com"


def _on_sale_with_price(db, name: str, *, amount: str, member_amount: str | None = None):
    """An article in sale, one size, with a price valid today (and, when given, a
    member price). Returns the product."""
    product = create_product(db, name)
    set_status(db, product.id, ProductStatus.ON_SALE)
    variant = add_variant(db, product.id, "M")
    add_prices(
        db,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal(amount),
        member_amount=Decimal(member_amount) if member_amount is not None else None,
    )
    return product


def _signed_in_member(db, email: str, *, valid_to: date):
    """A household with a confirmed e-mail and a membership valid to `valid_to`.
    The caller sets the session cookie to `email` afterwards."""
    from app.domains.auth.api import login_person_for_email
    from app.domains.membership.api import Membership
    from tests.conftest import create_test_family

    create_test_family(db, email=email)
    person = login_person_for_email(db, email)
    db.add(
        Membership(
            member_id=person.member_persons[0].member_id,
            year=valid_to.year,
            is_active=True,
            valid_from=date(valid_to.year, 1, 1),
            valid_to=valid_to,
        )
    )
    db.commit()


def test_the_webshop_offers_only_on_sale_articles_with_a_price(client, db_session, every_module_on):
    """T18: an article in sale with a price for a size shows; a Concept one and an
    in-sale one without a price do not."""
    _on_sale_with_price(db_session, "T-shirt Raak", amount="15.00")

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


def test_an_afgevoerd_article_leaves_the_webshop(client, db_session, every_module_on):
    """AC18: an article that is Afgevoerd leaves the Webshop, price or not."""
    product = _on_sale_with_price(db_session, "Afgevoerd artikel", amount="15.00")
    set_status(db_session, product.id, ProductStatus.DISCONTINUED)

    page = client.get("/webshop")
    assert "Afgevoerd artikel" not in page.text
    assert client.get(f"/webshop/{product.id}").status_code == 404


def test_an_article_whose_price_starts_tomorrow_is_not_offered(client, db_session, every_module_on):
    """ "A valid price today" is the rule's own word: a price that starts tomorrow
    leaves the article out of the offer. "Tomorrow" is the rule's own day (J1):
    on a process whose clock is UTC, `date.today()` is still today in Brussels."""
    product = create_product(db_session, "Morgen pas")
    set_status(db_session, product.id, ProductStatus.ON_SALE)
    variant = add_variant(db_session, product.id, "M")
    add_prices(
        db_session,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=belgian_today() + timedelta(days=1),
        amount=Decimal("15.00"),
        member_amount=None,
    )

    page = client.get("/webshop")
    assert "Morgen pas" not in page.text
    assert client.get(f"/webshop/{product.id}").status_code == 404


def test_the_article_page_shows_the_size_and_its_price(client, db_session, every_module_on):
    """The page of an article that is on offer is a 200 with its size as a tile
    and its price (the kit's tiles, #1967)."""
    product = _on_sale_with_price(db_session, "T-shirt Raak", amount="15.00")

    page = client.get(f"/webshop/{product.id}")
    assert page.status_code == 200
    assert "T-shirt Raak" in page.text
    assert "M" in page.text
    assert "15,00" in page.text


def test_a_visitor_pays_the_regular_price_and_a_member_the_member_price(
    client, db_session, every_module_on
):
    """F3: a visitor without a session reads the regular price; a signed-in member
    with a valid membership reads the member price."""
    _on_sale_with_price(db_session, "T-shirt Raak", amount="15.00", member_amount="12.00")

    page = client.get("/webshop")
    assert "15,00" in page.text
    assert "12,00" not in page.text

    _signed_in_member(db_session, MEMBER_EMAIL, valid_to=date(date.today().year, 12, 31))
    client.cookies.set(SESSION_COOKIE, make_session_value(MEMBER_EMAIL))

    page = client.get("/webshop")
    assert "12,00" in page.text
    assert "15,00" not in page.text


def test_a_member_whose_membership_lapsed_pays_the_regular_price(
    client, db_session, every_module_on
):
    """J3: a membership that ended yesterday is no membership — the regular price."""
    _on_sale_with_price(db_session, "T-shirt Raak", amount="15.00", member_amount="12.00")

    _signed_in_member(db_session, MEMBER_EMAIL, valid_to=belgian_today() - timedelta(days=1))
    client.cookies.set(SESSION_COOKIE, make_session_value(MEMBER_EMAIL))

    page = client.get("/webshop")
    assert "15,00" in page.text
    assert "12,00" not in page.text


def test_the_page_of_another_tenants_article_is_not_found(client, db_session, every_module_on):
    """A visitor types the id: an article of another tenant is not this tenant's
    offer, so its page is a 404."""
    from app.kernel.tenancy import TENANT_VOORBEELD_ID, current_tenant_id

    token = current_tenant_id.set(TENANT_VOORBEELD_ID)
    try:
        other = _on_sale_with_price(db_session, "Vreemd artikel", amount="15.00")
    finally:
        current_tenant_id.reset(token)

    assert client.get(f"/webshop/{other.id}").status_code == 404


def test_the_page_of_a_deleted_article_is_not_found(client, db_session, every_module_on):
    """A deleted article's id no longer answers — the page is a 404, not an error."""
    product = _on_sale_with_price(db_session, "Weg artikel", amount="15.00")
    db_session.delete(product)
    db_session.commit()

    assert client.get(f"/webshop/{product.id}").status_code == 404
