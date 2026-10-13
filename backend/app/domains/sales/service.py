"""The shop's rules (CR-21): what it offers, at which price, and how an order is
placed.

One rule in one place (H1, H2 of the read): an article is on offer when it is in
sale and at least one of its sizes has a price valid today. A member pays the
size's member price, anyone else its regular price — `price_for` decides that
(F3). Placing (C4.1, C5) recomputes every price, writes the lines and reserves
them, so the list, the article page and the order all ask the same rule.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.domains.pricing.api import price_for
from app.domains.product.api import (
    Product,
    ProductStatus,
    get_product_in_tenant,
    get_variant,
    list_products,
    pre_order_window,
    size_of,
    variants_of,
)
from app.domains.sales.models import SalesError
from app.kernel.clock import belgian_today


def _offered_sizes(db: Session, product: Product, *, member: bool) -> list[dict[str, Any]]:
    """The sizes of `product` that carry a price valid today, each with its name
    and the price the viewer pays (F16: "a valid price today")."""
    today = belgian_today()
    sizes: list[dict[str, Any]] = []
    for variant in variants_of(db, product.id):
        price = price_for(db, variant.id, today, member)
        if price is not None:
            sizes.append({"name": size_of(variant), "price": price})
    return sizes


def offered_products(db: Session, *, member: bool = False) -> list[dict[str, Any]]:
    """The articles the shop offers today (F16, R40): in sale, with at least one
    size whose price is valid today. Each carries its offered sizes and the lowest
    of their prices."""
    offered: list[dict[str, Any]] = []
    for product in list_products(db, active_only=True):
        sizes = _offered_sizes(db, product, member=member)
        if not sizes:
            continue
        offered.append(
            {
                "id": product.id,
                "name": product.name,
                "sizes": [size["name"] for size in sizes],
                "price": min(size["price"] for size in sizes),
            }
        )
    return offered


def article_offer(db: Session, product_id: int, *, member: bool = False) -> dict[str, Any] | None:
    """One article's offer today — its name, description and the sizes with their
    prices — or None when it is not offered: not in sale, no size with a price
    valid today, of another tenant, or deleted.

    The product is read through the tenant-filtered read of `product`
    (`get_product_in_tenant`), not a load by key: a visitor types the id, and a
    primary-key load must not skip the tenant filter (H4, J4)."""
    product = get_product_in_tenant(db, product_id)
    if product is None or product.status is not ProductStatus.ON_SALE:
        return None
    sizes = _offered_sizes(db, product, member=member)
    if not sizes:
        return None
    return {"name": product.name, "description": product.description or "", "sizes": sizes}


def place_order(
    db: Session,
    *,
    person_id: int | None,
    guest_name: str,
    guest_email: str,
    guest_mobile: str,
    method: Any,
    items: list[tuple[int, int]],
    member: bool,
):
    """Place an order: every price recomputed, the lines and their reservations
    written (C4.1, C5, F1).

    Nothing the browser sent is an amount — each line's price comes from
    `price_for` here. The variants are reserved in a fixed order (by variant id),
    stock before payment, and the first refusal raises, so nothing is reserved
    half (the door rolls the whole order back). An article "Op bestelling" whose
    window is open reserves with `allow_short` (R39).

    Returns the `SalesOrder` (its lines carry the prices); the total is the sum of
    the line amounts, `total_of`.
    """
    from app.domains.sales.models import SalesOrder, SalesOrderLine
    from app.domains.stock.api import NotEnoughStock
    from app.i18n import _
    from app.kernel.contracts.stock import ReserveStock
    from app.kernel.ports import call
    from app.kernel.tenant_config import tenant_max_item_quantity

    items = sorted(items, key=lambda item: item[0])
    if not items:
        raise SalesError(_("Je mandje is leeg."))
    max_quantity = tenant_max_item_quantity(db)
    today = belgian_today()
    order = SalesOrder(
        person_id=person_id,
        guest_name=guest_name,
        guest_email=guest_email,
        guest_mobile=guest_mobile,
        payment_method=method,
    )
    db.add(order)
    db.flush()
    for variant_id, quantity in items:
        if quantity < 1 or quantity > max_quantity:
            raise SalesError(
                _("Ongeldig aantal: kies een waarde tussen 1 en %(max)s.") % {"max": max_quantity}
            )
        variant = get_variant(db, variant_id)
        if variant is None:
            raise SalesError(_("Dit artikel wordt niet meer aangeboden."))
        product = get_product_in_tenant(db, variant.product_id)
        if product is None or product.status is not ProductStatus.ON_SALE:
            raise SalesError(_("Dit artikel wordt niet meer aangeboden."))
        price = price_for(db, variant_id, today, member)
        if price is None:
            raise SalesError(_("Dit artikel wordt niet meer aangeboden."))
        open_window, _until = pre_order_window(product, today)
        line = SalesOrderLine(
            order_id=order.id,
            variant_id=variant_id,
            quantity=quantity,
            unit_price=price,
        )
        db.add(line)
        db.flush()
        try:
            call(
                ReserveStock(
                    order_line_id=line.id,
                    variant_id=variant_id,
                    quantity=quantity,
                    allow_short=open_window,
                ),
                db,
            )
        except NotEnoughStock as exc:
            raise SalesError(_("Niet genoeg voorraad.")) from exc
    return order


def total_of(order) -> Decimal:
    """The total of an order's lines (their fixed prices times their quantities)."""
    return sum((line.unit_price * line.quantity for line in order.lines), Decimal("0"))


def submit_order(
    db: Session,
    *,
    person_id: int | None,
    member: bool,
    contact_name: str,
    contact_email: str,
    phone: str,
    method: Any,
    items: list[tuple[int, int]],
) -> tuple[str | None, int]:
    """The whole placing flow (C4.1, C5): place, start the payment, publish, commit.

    Returns `(checkout_url, order_id)` — `checkout_url` only for an online order.
    Raises `SalesError` for a refusal (the door answers 422, the order rolled
    back); raises `HTTPException(502)` when an online payment cannot start (the
    order is rolled back, nothing reserved).
    """
    from fastapi import HTTPException

    from app.domains.mdm.api import PaymentMethod
    from app.domains.payment.api import PayableType
    from app.i18n import _
    from app.kernel.contracts.payment import CreatePayment
    from app.kernel.contracts.sales import SalesOrderPlaced
    from app.kernel.events import publish
    from app.kernel.ports import call
    from app.kernel.tenant_config import tenant_base_url

    try:
        order = place_order(
            db,
            person_id=person_id,
            guest_name=contact_name,
            guest_email=contact_email,
            guest_mobile=phone,
            method=method,
            items=items,
            member=member,
        )
    except SalesError:
        db.rollback()
        raise

    total = total_of(order)
    checkout_url: str | None = None
    payment_record_id = ""
    if total > 0:
        try:
            started = call(
                CreatePayment(
                    payable_type=PayableType.ORDER.value,
                    payable_id=order.id,
                    amount=str(total),
                    method=method.value,
                    redirect_url=f"{tenant_base_url(db)}/webshop/bedankt?order={order.id}",
                    description=f"Bestelling {order.id}",
                    audit_source="webshop-order",
                ),
                db,
            )
            payment_record_id = started.payment_record_id
            checkout_url = started.checkout_url
            if method == PaymentMethod.ONLINE and not checkout_url:
                raise ValueError("geen checkout_url")
        except Exception as exc:  # noqa: BLE001 - the provider refused or timed out
            db.rollback()
            if method == PaymentMethod.ONLINE:
                raise HTTPException(
                    status_code=502,
                    detail=_(
                        "De online betaling kon niet gestart worden. Je bestelling is niet bewaard — probeer het later opnieuw."
                    ),
                ) from exc

    publish(
        SalesOrderPlaced(order_id=order.id, payment_record_id=payment_record_id),
        db,
    )
    db.commit()
    return checkout_url, order.id


def get_order(db: Session, order_id: int):
    """The order, or None — for the thank-you page, which shows no ownership."""
    from app.domains.sales.models import SalesOrder

    return db.query(SalesOrder).filter(SalesOrder.id == order_id).one_or_none()


def orders_of_person(db: Session, person_id: int):
    """The orders of a person, newest first (AC13, W26)."""
    from app.domains.sales.models import SalesOrder

    return (
        db.query(SalesOrder)
        .filter(SalesOrder.person_id == person_id)
        .order_by(SalesOrder.id.desc())
        .all()
    )


def owned_order(db: Session, order_id: int, person_id: int | None):
    """The order, when the person owns it — himself or through his household
    (C5, CR-22 R8, Q62). None otherwise: another id answers 404, not 403."""
    from app.domains.mdm.api import MemberPerson
    from app.domains.sales.models import SalesOrder

    if person_id is None:
        return None
    order = db.query(SalesOrder).filter(SalesOrder.id == order_id).one_or_none()
    if order is None or order.person_id is None:
        return None
    if order.person_id == person_id:
        return order
    owner_households = {
        row[0]
        for row in db.query(MemberPerson.member_id)
        .filter(MemberPerson.person_id == order.person_id)
        .all()
    }
    mine = {
        row[0]
        for row in db.query(MemberPerson.member_id)
        .filter(MemberPerson.person_id == person_id)
        .all()
    }
    return order if owner_households & mine else None
