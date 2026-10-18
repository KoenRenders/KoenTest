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
    from app.domains.product.api import variants_of

    product = _on_sale_with_price(db_session, "T-shirt Raak", amount="15.00")
    variant = variants_of(db_session, product.id)[0]

    page = client.get(f"/webshop/{product.id}")
    assert page.status_code == 200
    assert "T-shirt Raak" in page.text
    assert f'value="{variant.id}"' in page.text  # the size's tile
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

    _signed_in_member(db_session, MEMBER_EMAIL, valid_to=date(belgian_today().year, 12, 31))
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


def test_vanaf_precedes_the_lowest_price_when_sizes_differ_in_price(
    client, db_session, every_module_on
):
    """N5: with sizes at two prices the page says "vanaf" before the lowest price."""
    product = _on_sale_with_price(db_session, "T-shirt Raak", amount="15.00")
    variant_l = add_variant(db_session, product.id, "L")
    add_prices(
        db_session,
        product_id=product.id,
        variant_id=variant_l.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal("17.50"),
        member_amount=None,
    )
    db_session.commit()

    page = client.get(f"/webshop/{product.id}")
    assert page.status_code == 200
    assert "vanaf € 15,00" in page.text


def test_no_vanaf_when_the_sizes_cost_the_same(client, db_session, every_module_on):
    """N5: two sizes at one price show the price alone, no "vanaf"."""
    product = _on_sale_with_price(db_session, "T-shirt Raak", amount="15.00")
    variant_l = add_variant(db_session, product.id, "L")
    add_prices(
        db_session,
        product_id=product.id,
        variant_id=variant_l.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal("15.00"),
        member_amount=None,
    )
    db_session.commit()

    page = client.get(f"/webshop/{product.id}")
    assert page.status_code == 200
    assert "vanaf €" not in page.text
    assert "15,00" in page.text


def test_the_article_page_shows_its_pictures_and_documents(client, db_session, every_module_on):
    """R1/R3: the article page shows its pictures (alt from the description) and its
    documents as links that open; the list shows the first picture's thumbnail."""
    from app.domains.media.api import MediaAsset, MediaKind
    from app.domains.product.api import ProductAttachment

    product = _on_sale_with_price(db_session, "T-shirt Raak", amount="15.00")

    photo = MediaAsset(
        kind=MediaKind.PRODUCT_PHOTO, title="foto.png", data=b"x", content_type="image/png"
    )
    db_session.add(photo)
    db_session.flush()
    db_session.add(
        ProductAttachment(product_id=product.id, media_asset_id=photo.id, description="De voorkant")
    )
    document = MediaAsset(
        kind=MediaKind.PRODUCT_DOCUMENT,
        title="maattabel.pdf",
        data=b"%PDF-1.4",
        content_type="application/pdf",
    )
    db_session.add(document)
    db_session.flush()
    db_session.add(
        ProductAttachment(product_id=product.id, media_asset_id=document.id, title="Maattabel")
    )
    db_session.commit()

    page = client.get(f"/webshop/{product.id}")
    assert page.status_code == 200
    assert f"/api/v1/media/{photo.id}" in page.text
    assert 'alt="De voorkant"' in page.text
    assert f'href="/api/v1/media/{document.id}"' in page.text
    assert "Maattabel" in page.text

    listing = client.get("/webshop")
    assert f"/api/v1/media/{photo.id}/thumb" in listing.text


def test_a_picture_without_a_description_has_an_empty_alt(client, db_session, every_module_on):
    """S1: a picture without a description renders `alt=""`, never the file name."""
    from app.domains.media.api import MediaAsset, MediaKind
    from app.domains.product.api import ProductAttachment

    product = _on_sale_with_price(db_session, "T-shirt Raak", amount="15.00")
    photo = MediaAsset(
        kind=MediaKind.PRODUCT_PHOTO,
        title="foto-voorkant.png",
        data=b"x",
        content_type="image/png",
    )
    db_session.add(photo)
    db_session.flush()
    db_session.add(ProductAttachment(product_id=product.id, media_asset_id=photo.id))
    db_session.commit()

    page = client.get(f"/webshop/{product.id}")
    assert 'alt=""' in page.text
    assert "foto-voorkant.png" not in page.text


def test_a_document_without_a_title_shows_the_file_name(client, db_session, every_module_on):
    """S1: a document without a title shows its file name as the link text."""
    from app.domains.media.api import MediaAsset, MediaKind
    from app.domains.product.api import ProductAttachment

    product = _on_sale_with_price(db_session, "T-shirt Raak", amount="15.00")
    document = MediaAsset(
        kind=MediaKind.PRODUCT_DOCUMENT,
        title="maattabel.pdf",
        data=b"%PDF-1.4",
        content_type="application/pdf",
    )
    db_session.add(document)
    db_session.flush()
    db_session.add(ProductAttachment(product_id=product.id, media_asset_id=document.id))
    db_session.commit()

    page = client.get(f"/webshop/{product.id}")
    assert "maattabel.pdf" in page.text


def test_a_pre_order_size_without_stock_says_op_bestelling(client, db_session, every_module_on):
    """R1: a size of an "Op bestelling" article with no stock is orderable and its
    tile says "op bestelling", not "uitverkocht" — the tile asks the shared stock
    rule, so it fails if the tile says "uitverkocht" or nothing."""
    from app.domains.product.api import add_variant, create_product, set_status

    product = create_product(db_session, "T-shirt")
    set_status(db_session, product.id, ProductStatus.ON_SALE)
    product.pre_order = True
    variant = add_variant(db_session, product.id, "M")
    add_prices(
        db_session,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal("15.00"),
        member_amount=None,
    )
    db_session.commit()

    page = client.get(f"/webshop/{product.id}")
    assert page.status_code == 200
    assert "op bestelling" in page.text
    assert "uitverkocht" not in page.text


def test_op_bestelling_stays_after_the_first_pre_order(client, db_session, every_module_on):
    """T1: one pre-order reserves below zero (`available` −1), and the tile still
    says "op bestelling" — the size reads `in_stock <= 0`, not `== 0`."""
    from app.domains.product.api import add_variant, create_product, set_status
    from tests.conftest import form_guard_fields

    product = create_product(db_session, "T-shirt")
    set_status(db_session, product.id, ProductStatus.ON_SALE)
    product.pre_order = True
    variant = add_variant(db_session, product.id, "M")
    add_prices(
        db_session,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal("15.00"),
        member_amount=None,
    )
    db_session.commit()

    placed = client.post(
        "/webshop/bestellen",
        data={
            "variant_id": str(variant.id),
            "quantity": "1",
            "contact_name": "An",
            "contact_email": "an@example.com",
            "phone": "0470000000",
            "payment_method": "transfer",
            **form_guard_fields(),
        },
        follow_redirects=False,
    )
    assert placed.status_code == 200

    page = client.get(f"/webshop/{product.id}")
    assert page.status_code == 200
    assert "op bestelling" in page.text


def test_a_sold_out_size_without_pre_order_stays_uitverkocht(client, db_session, every_module_on):
    """R1's counter-case: a size with no stock and no pre-order says "uitverkocht",
    not "op bestelling"."""
    product = _on_sale_with_price(db_session, "T-shirt Raak", amount="15.00")

    page = client.get(f"/webshop/{product.id}")
    assert page.status_code == 200
    assert "uitverkocht" in page.text
    assert "op bestelling" not in page.text


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
