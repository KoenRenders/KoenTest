"""E2E #2108 — the webshop's product page: one picture at a time beside the buy box.

Two articles are made here, on the shop's own tenant (`winkel`, see
`test_webshop.py`): one with four pictures and thirteen sizes — the approved
screen of CR-21 (Q68, Q69) — and one with one picture. Measured in the browser,
since only the rendered page knows where "In mandje" stands:

- at 1 280 x 800 the picture and the buy box stand side by side and the whole
  "In mandje" button lies inside the first screen;
- at 390 x 844 the button's place is reported (the issue asks for the number);
- the arrows step through the pictures and the counter follows, hidden at the
  first and the last; one picture shows neither;
- the quantity and the button share one row at both widths.
"""

from __future__ import annotations

import os
import secrets
import sys
from datetime import date
from decimal import Decimal

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import pagina_klaar  # noqa: E402

WEBSHOP_HOST = "http://webshop.localhost:8000"
SIZES = ["XS", "S", "M", "L", "XL", "XXL", "3XL", "98", "110", "122", "134", "146", "158"]


def _picture(n: int) -> bytes:
    """A drawn picture with its number on it — no photo of a person."""
    return (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 600'>"
        f"<rect width='600' height='600' fill='#254e73'/>"
        f"<text x='300' y='340' font-size='160' text-anchor='middle' fill='#eec15e'>{n}</text>"
        "</svg>"
    ).encode()


def _article(name: str, pictures: int, sizes: list[str]) -> int:
    """An article on sale on the shop's tenant, with `pictures` pictures and one
    size per name, each in stock, at a product price."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import tenant_codes
    from app.domains.media.api import MediaAsset, MediaKind
    from app.domains.pricing.api import add_prices
    from app.domains.product.api import ProductAttachment
    from app.domains.product.models import Product, ProductStatus, ProductVariant
    from app.domains.stock.api import receive
    from app.kernel.tenancy import current_tenant_id

    db = SessionLocal()
    token = current_tenant_id.set(tenant_codes(db)["winkel"])
    try:
        product = Product(name=name, status=ProductStatus.ON_SALE)
        db.add(product)
        db.flush()
        for order, size in enumerate(sizes):
            variant = ProductVariant(
                product_id=product.id,
                properties=[{"name": "Maat", "value": size}],
                sort_order=order,
            )
            db.add(variant)
            db.flush()
            receive(db, variant.id, quantity=5)
        add_prices(
            db,
            product_id=product.id,
            variant_id=None,
            valid_from=date(2026, 1, 1),
            amount=Decimal("20.00"),
            member_amount=None,
        )
        for n in range(1, pictures + 1):
            asset = MediaAsset(
                kind=MediaKind.PRODUCT_PHOTO,
                title=f"foto-{n}.svg",
                data=_picture(n),
                content_type="image/svg+xml",
            )
            db.add(asset)
            db.flush()
            db.add(
                ProductAttachment(
                    product_id=product.id,
                    media_asset_id=asset.id,
                    description=f"Foto {n} van {name}",
                    sort_order=n,
                )
            )
        db.commit()
        return product.id
    finally:
        current_tenant_id.reset(token)
        db.close()


def _remove(product_ids: list[int]) -> None:
    """Take the articles away again, with everything made for them, so the shop's
    tenant is as the seed left it: `test_webshop.py` walks the seeded articles and
    reads the first of a list, whichever file runs first (master CLI, 18 October
    2026: the order of the files may not decide)."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import tenant_codes
    from app.domains.media.api import MediaAsset
    from app.domains.pricing.models import Price
    from app.domains.product.api import ProductAttachment
    from app.domains.product.models import Product, ProductVariant
    from app.domains.stock.models import StockMovement
    from app.kernel.tenancy import current_tenant_id

    db = SessionLocal()
    token = current_tenant_id.set(tenant_codes(db)["winkel"])
    try:
        attachments = db.query(ProductAttachment).filter(
            ProductAttachment.product_id.in_(product_ids)
        )
        asset_ids = [a.media_asset_id for a in attachments]
        attachments.delete(synchronize_session=False)
        db.query(MediaAsset).filter(MediaAsset.id.in_(asset_ids)).delete(synchronize_session=False)
        variants = db.query(ProductVariant).filter(ProductVariant.product_id.in_(product_ids))
        variant_ids = [v.id for v in variants]
        db.query(StockMovement).filter(StockMovement.variant_id.in_(variant_ids)).delete(
            synchronize_session=False
        )
        db.query(Price).filter(Price.product_id.in_(product_ids)).delete(synchronize_session=False)
        variants.delete(synchronize_session=False)
        db.query(Product).filter(Product.id.in_(product_ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        current_tenant_id.reset(token)
        db.close()


@pytest.fixture(scope="module")
def articles():
    tag = secrets.token_hex(3)
    made = {
        "four": _article(f"Webshop Trui {tag}", 4, SIZES),
        "one": _article(f"Webshop Pet {tag}", 1, ["M", "L", "XL"]),
    }
    yield made
    _remove(list(made.values()))


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    page = browser.new_page(base_url=WEBSHOP_HOST)
    yield page
    page.close()


def _open(page, product_id: int, width: int, height: int):
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"/webshop/{product_id}")
    pagina_klaar(page)


def _box(page, selector: str) -> dict:
    box = page.locator(selector).first.bounding_box()
    assert box is not None, f"{selector} is rendered"
    return box


def _counter(page) -> str:
    return page.locator("[data-carousel-counter]").inner_text().strip()


def _shown(page, selector: str) -> bool:
    return page.locator(selector).first.evaluate("el => el.checkVisibility()")


def test_on_a_laptop_the_buy_box_stands_beside_the_picture_in_the_first_screen(page, articles):
    """1 280 x 800: the picture left, the buy box right, "In mandje" whole inside the
    viewport on load — with four pictures and thirteen sizes."""
    _open(page, articles["four"], 1280, 800)
    picture = _box(page, "[data-product-photos]")
    buy = _box(page, "[data-shop-buy]")
    button = _box(page, "[data-add-to-basket]")

    assert picture["x"] + picture["width"] <= buy["x"], (picture, buy)
    assert abs(picture["y"] - buy["y"]) < 4, "side by side, tops aligned"
    assert button["y"] >= 0 and button["y"] + button["height"] <= 800, (
        f"'In mandje' in the first screen: {button}"
    )


@pytest.mark.parametrize("width,height", [(1280, 800), (390, 844)])
def test_the_quantity_and_the_button_share_one_row(page, articles, width, height):
    """The counter left, "In mandje" right, on one row."""
    _open(page, articles["four"], width, height)
    stepper = _box(page, "[data-buy-row] input[name=quantity]")
    button = _box(page, "[data-add-to-basket]")
    assert stepper["x"] + stepper["width"] <= button["x"], (stepper, button)
    centre = lambda b: b["y"] + b["height"] / 2  # noqa: E731
    assert abs(centre(stepper) - centre(button)) <= 4, (stepper, button)


def test_on_a_phone_the_button_is_reported(page, articles):
    """390 x 844 with four pictures and thirteen sizes: the issue asks where the
    button stands, to put to Koen if it falls below the first screen. The picture
    stands above the buy box."""
    _open(page, articles["four"], 390, 844)
    picture = _box(page, "[data-product-photos]")
    buy = _box(page, "[data-shop-buy]")
    button = _box(page, "[data-add-to-basket]")
    assert picture["y"] + picture["height"] <= buy["y"], "stacked, the picture first"
    print(
        f"\n#2108 at 390 x 844: 'In mandje' top {button['y']:.0f}, "
        f"bottom {button['y'] + button['height']:.0f}; picture {picture['height']:.0f} px high"
    )


def test_the_arrows_step_and_the_counter_follows(page, articles):
    """Next and previous move one picture; the counter follows; previous is hidden
    at the first, next at the last; one picture is shown at a time."""
    _open(page, articles["four"], 390, 844)
    photos = page.locator("[data-carousel-photo]")
    assert photos.count() == 4

    def visible() -> list[int]:
        return [i for i in range(4) if photos.nth(i).evaluate("el => el.checkVisibility()")]

    assert _counter(page) == "1 / 4"
    assert visible() == [0]
    assert not _shown(page, "[data-carousel-previous]")
    assert _shown(page, "[data-carousel-next]")

    page.get_by_role("button", name="Volgende foto").click()
    assert _counter(page) == "2 / 4"
    assert visible() == [1]
    assert _shown(page, "[data-carousel-previous]")

    page.get_by_role("button", name="Volgende foto").click()
    page.get_by_role("button", name="Volgende foto").click()
    assert _counter(page) == "4 / 4"
    assert visible() == [3]
    assert not _shown(page, "[data-carousel-next]")
    assert page.evaluate("document.activeElement.matches('[data-carousel-previous]')"), (
        "the focus moved to the other arrow when next hid under it"
    )

    page.get_by_role("button", name="Vorige foto").click()
    assert _counter(page) == "3 / 4"
    assert visible() == [2]
    assert photos.nth(2).locator("img").get_attribute("alt").startswith("Foto 3 van")


def test_a_tap_on_the_picture_opens_the_lightbox_on_it(page, articles):
    """Q68: a tap on the picture opens the lightbox, on that picture."""
    _open(page, articles["four"], 390, 844)
    page.get_by_role("button", name="Volgende foto").click()
    page.locator("[data-carousel-photo]").nth(1).click()
    assert _shown(page, "[data-lightbox]")
    src = page.locator("[data-lightbox-photo]").get_attribute("src")
    assert src == page.locator("[data-carousel-photo] img").nth(1).get_attribute("src")


def test_one_picture_shows_no_arrows_and_no_counter(page, articles):
    _open(page, articles["one"], 390, 844)
    assert page.locator("[data-carousel-photo]").count() == 1
    assert _shown(page, "[data-carousel-photo]")
    assert page.locator("[data-carousel-previous], [data-carousel-next]").count() == 0
    assert page.locator("[data-carousel-counter]").count() == 0
