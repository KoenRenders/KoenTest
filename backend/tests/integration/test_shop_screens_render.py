"""The shop's screens render with data (CR-21, the B1–B7 repairs).

Each test renders the screen through the client and reads the HTML — the way the
browser does — so a bug that only shows once an article exists is caught here and
not in production.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.pricing.api import Price, PriceType, prices_of
from app.domains.product.api import ProductStatus, add_variant, create_product, set_status
from app.kernel.clock import belgian_today
from tests.conftest import SEEDED_ADMIN_EMAIL


def _operator(client, db_session, every_module_on) -> dict[str, str]:
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not any(role.role_code.value == "OPERATOR" for role in user.roles):
        db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db_session.flush()
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return {"X-CSRF-Token": csrf_token_for(session)}


def test_the_product_list_renders_an_article_and_links_to_it(client, db_session, every_module_on):
    _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    add_variant(db_session, product.id, "M")

    page = client.get("/admin/producten")
    assert page.status_code == 200
    assert "T-shirt Raak" in page.text
    assert f'href="/admin/producten/{product.id}"' in page.text
    assert re.search(r'data-cell="extra"[^>]*>\s*1\s*</td>', page.text), (
        "the sizes count is not in its cell"
    )


def test_the_price_form_accepts_cents(client, db_session, every_module_on):
    _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")

    page = client.get(f"/admin/prijzen/{product.id}")
    assert page.status_code == 200
    assert 'step="0.01"' in page.text


def test_a_second_price_on_the_same_day_is_refused_in_words(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    first = client.post(
        f"/admin/prijzen/{product.id}",
        data={"valid_from": "2026-11-01", "variant_id": "", "amount": "17", "member_amount": "14"},
        headers=headers,
        follow_redirects=False,
    )
    assert first.status_code == 303

    second = client.post(
        f"/admin/prijzen/{product.id}",
        data={"valid_from": "2026-11-01", "variant_id": "", "amount": "18"},
        headers=headers,
        follow_redirects=False,
    )
    assert second.status_code == 422
    assert "staat al een prijs" in second.text


def test_annuleren_leads_back_to_the_record(client, db_session, every_module_on):
    _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")

    record = client.get(f"/admin/producten/{product.id}?bewerken=1")
    assert record.status_code == 200
    assert f'href="/admin/producten/{product.id}"' in record.text

    price = client.get(f"/admin/prijzen/{product.id}")
    assert price.status_code == 200
    assert f'href="/admin/prijzen/{product.id}"' in price.text


def test_geldt_is_per_size_and_type(client, db_session, every_module_on):
    _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    medium = add_variant(db_session, product.id, "M")
    today = belgian_today()
    db_session.add_all(
        [
            Price(
                product_id=product.id,
                variant_id=None,
                price_type=PriceType.REGULAR,
                amount=Decimal("15.00"),
                valid_from=today - timedelta(days=39),
            ),
            Price(
                product_id=product.id,
                variant_id=medium.id,
                price_type=PriceType.REGULAR,
                amount=Decimal("17.00"),
                valid_from=today - timedelta(days=70),
            ),
        ]
    )
    db_session.flush()

    page = client.get(f"/admin/prijzen/{product.id}")
    assert page.status_code == 200
    assert "Voorbij" not in page.text, "the size's own older price is in force, not superseded"
    assert page.text.count("Vandaag") == 2


def test_a_missing_article_is_404_not_500(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    answer = client.post(
        "/admin/producten/999999/status", data={"status": "ON_SALE"}, headers=headers
    )
    assert answer.status_code == 404


def test_a_size_of_another_article_is_refused(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    shirt = create_product(db_session, "T-shirt Raak")
    sweater = create_product(db_session, "Sweater Raak")
    sweater_size = add_variant(db_session, sweater.id, "M")

    answer = client.post(
        f"/admin/prijzen/{shirt.id}",
        data={
            "valid_from": "2026-11-01",
            "variant_id": str(sweater_size.id),
            "amount": "17",
        },
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422
    assert "hoort niet bij dit artikel" in answer.text
    assert prices_of(db_session, shirt.id) == []


def test_a_missing_article_on_update_is_404_not_500(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    answer = client.post(
        "/admin/producten/999999", data={"name": "x"}, headers=headers, follow_redirects=False
    )
    assert answer.status_code == 404


def test_a_delete_with_movements_is_refused_visibly(client, db_session, every_module_on):
    """The delete gate lives in `stock`'s handler (Q75, AC19): an article with a
    movement is refused, and the sentence reaches the record's message line — the
    visible box — not the closed menu that was clicked."""
    from app.domains.stock.api import receive

    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    variant = add_variant(db_session, product.id, "M")
    db_session.add(
        Price(
            product_id=product.id,
            variant_id=None,
            price_type=PriceType.REGULAR,
            amount=Decimal("15.00"),
            valid_from=date(2026, 1, 1),
        )
    )
    db_session.flush()
    receive(db_session, variant.id, quantity=5)

    record = client.get(f"/admin/producten/{product.id}")
    assert 'id="product-melding"' in record.text, "the header names a line the page lacks"

    answer = client.post(
        f"/admin/producten/{product.id}/verwijderen",
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422
    assert "voorraadbewegingen" in answer.text
    assert answer.headers.get("HX-Retarget") == "#product-melding"


def _article_with_a_movement(client, db_session, every_module_on):
    """An article with one size and a movement, signed in as the operator."""
    from app.domains.stock.api import receive

    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    variant = add_variant(db_session, product.id, "M")
    receive(db_session, variant.id, quantity=5)
    return headers, product


def test_a_refused_delete_offers_afvoeren_while_the_article_is_not_yet_afgevoerd(
    client, db_session, every_module_on
):
    """An article with a movement that is not Afgevoerd is offered the alternative
    (AC19, W23): the sentence carries "— zet het afgevoerd."."""
    headers, product = _article_with_a_movement(client, db_session, every_module_on)
    set_status(db_session, product.id, ProductStatus.ON_SALE)

    answer = client.post(
        f"/admin/producten/{product.id}/verwijderen",
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422
    assert "zet het afgevoerd" in answer.text


def test_a_refused_delete_does_not_offer_afvoeren_when_the_article_is_already_afgevoerd(
    client, db_session, every_module_on
):
    """An article already Afgevoerd is told the bare fact, without the offer
    (Koen, 10 October 2026): the sentence ends after "kan niet verwijderd worden."."""
    headers, product = _article_with_a_movement(client, db_session, every_module_on)
    set_status(db_session, product.id, ProductStatus.DISCONTINUED)

    answer = client.post(
        f"/admin/producten/{product.id}/verwijderen",
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422
    assert "voorraadbewegingen" in answer.text
    assert "zet het afgevoerd" not in answer.text


def test_removing_a_size_with_movements_is_refused(client, db_session, every_module_on):
    """The delete gate holds for one size too: removing a size with a movement is
    refused, and the size stays (the review of Voorraadbeheer)."""
    from app.domains.product.api import variants_of
    from app.domains.stock.api import receive

    headers, product = _article_with_a_movement(client, db_session, every_module_on)
    variant = variants_of(db_session, product.id)[0]
    receive(db_session, variant.id, quantity=5)

    answer = client.post(
        f"/admin/producten/{product.id}",
        data={"name": "T-shirt Raak"},
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422
    assert "voorraadbewegingen" in answer.text
    assert [v.id for v in variants_of(db_session, product.id)] == [variant.id]


def _article_with_a_photo(client, db_session, every_module_on):
    """An on-sale article with one size and one picture, the client signed in as
    the operator — what the S1 save tests post through."""
    from app.domains.media.api import MediaAsset, MediaKind
    from app.domains.pricing.api import add_prices
    from app.domains.product.api import ProductAttachment

    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    set_status(db_session, product.id, ProductStatus.ON_SALE)
    variant = add_variant(db_session, product.id, "M")
    add_prices(
        db_session,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal("15.00"),
        member_amount=None,
    )
    photo = MediaAsset(
        kind=MediaKind.PRODUCT_PHOTO, title="foto.png", data=b"x", content_type="image/png"
    )
    db_session.add(photo)
    db_session.flush()
    attachment = ProductAttachment(product_id=product.id, media_asset_id=photo.id)
    db_session.add(attachment)
    db_session.commit()
    return headers, product, variant, attachment


def _save_fields(product, variant, *, name="T-shirt Raak", **extra) -> dict:
    fields = {
        "name": name,
        "v_order": str(variant.id),
        f"v.{variant.id}.name": "M",
    }
    fields.update(extra)
    return fields


def test_a_posted_description_reaches_the_public_alt(client, db_session, every_module_on):
    """S1: a description posted through the article's own save reaches the public
    page's `alt`."""
    headers, product, variant, attachment = _article_with_a_photo(
        client, db_session, every_module_on
    )
    answer = client.post(
        f"/admin/producten/{product.id}",
        data=_save_fields(
            product, variant, **{f"bijlage.{attachment.id}.description": "De voorkant"}
        ),
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 303

    page = client.get(f"/webshop/{product.id}")
    assert 'alt="De voorkant"' in page.text


def test_a_description_over_255_characters_is_refused(client, db_session, every_module_on):
    """V1: a description over 255 characters is a refusal, not a 500."""
    headers, product, variant, attachment = _article_with_a_photo(
        client, db_session, every_module_on
    )
    answer = client.post(
        f"/admin/producten/{product.id}",
        data=_save_fields(product, variant, **{f"bijlage.{attachment.id}.description": "x" * 256}),
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422
    assert "te lang" in answer.text


def test_the_service_refuses_a_word_over_255_characters(client, db_session, every_module_on):
    """V1, at the service: `set_attachment_text` refuses a word over 255 characters."""
    import pytest

    from app.domains.product.api import ProductError, set_attachment_text

    _headers, product, _variant, attachment = _article_with_a_photo(
        client, db_session, every_module_on
    )
    with pytest.raises(ProductError):
        set_attachment_text(db_session, product.id, attachment.id, description="x" * 256)


def test_another_articles_attachment_key_changes_nothing(client, db_session, every_module_on):
    """S1: the article's save reads only its own attachments, so a posted key of
    another article's attachment leaves that article unchanged."""
    from app.domains.media.api import MediaAsset, MediaKind
    from app.domains.product.api import ProductAttachment

    headers, product, variant, _attachment = _article_with_a_photo(
        client, db_session, every_module_on
    )
    other = create_product(db_session, "Ander artikel")
    other_photo = MediaAsset(
        kind=MediaKind.PRODUCT_PHOTO, title="x.png", data=b"x", content_type="image/png"
    )
    db_session.add(other_photo)
    db_session.flush()
    other_attachment = ProductAttachment(
        product_id=other.id, media_asset_id=other_photo.id, description="Van het andere"
    )
    db_session.add(other_attachment)
    db_session.commit()

    answer = client.post(
        f"/admin/producten/{product.id}",
        data=_save_fields(
            product, variant, **{f"bijlage.{other_attachment.id}.description": "Gekaapt"}
        ),
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 303
    assert db_session.get(ProductAttachment, other_attachment.id).description == "Van het andere"


def _article_with_two_photos(client, db_session, every_module_on):
    from app.domains.media.api import MediaAsset, MediaKind
    from app.domains.pricing.api import add_prices
    from app.domains.product.api import ProductAttachment

    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    set_status(db_session, product.id, ProductStatus.ON_SALE)
    variant = add_variant(db_session, product.id, "M")
    add_prices(
        db_session,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal("15.00"),
        member_amount=None,
    )
    photos = []
    for i in range(2):
        photo = MediaAsset(
            kind=MediaKind.PRODUCT_PHOTO,
            title=f"foto{i}.png",
            data=b"x",
            content_type="image/png",
        )
        db_session.add(photo)
        db_session.flush()
        attachment = ProductAttachment(product_id=product.id, media_asset_id=photo.id)
        db_session.add(attachment)
        photos.append(attachment)
    db_session.commit()
    return headers, product, variant, photos


def test_a_refused_attachment_writes_nothing(client, db_session, every_module_on):
    """W1: a save with one valid and one too-long description is refused and writes
    nothing — not the name, not the first description."""
    from app.domains.product.api import ProductAttachment, get_product

    headers, product, variant, photos = _article_with_two_photos(
        client, db_session, every_module_on
    )
    answer = client.post(
        f"/admin/producten/{product.id}",
        data=_save_fields(
            product,
            variant,
            name="Nieuwe naam",
            **{
                f"bijlage.{photos[0].id}.description": "Eerste ok",
                f"bijlage.{photos[1].id}.description": "x" * 256,
            },
        ),
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422
    assert get_product(db_session, product.id).name == "T-shirt Raak"
    assert db_session.get(ProductAttachment, photos[0].id).description is None


def test_a_missing_field_changes_nothing(client, db_session, every_module_on):
    """A save that does not send an attachment's field keeps its word."""
    from app.domains.product.api import ProductAttachment

    headers, product, variant, attachment = _article_with_a_photo(
        client, db_session, every_module_on
    )
    attachment.description = "Blijf"
    db_session.commit()

    answer = client.post(
        f"/admin/producten/{product.id}",
        data=_save_fields(product, variant),
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 303
    assert db_session.get(ProductAttachment, attachment.id).description == "Blijf"
