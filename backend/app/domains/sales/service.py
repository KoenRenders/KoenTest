"""The shop's rules (CR-21): what it offers, at which price, and how an order is
placed.

One rule in one place (H1, H2 of the read): an article is on offer when it is in
sale and at least one of its sizes has a price valid today. A member pays the
size's member price, anyone else its regular price — `price_for` decides that
(F3). Placing (C4.1, C5) recomputes every price, writes the lines and reserves
them, so the list, the article page and the order all ask the same rule.
"""

from __future__ import annotations

from datetime import date
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
    """The sizes of `product` that carry a price valid today, each with its id,
    name, the price the viewer pays (F16) and whether it can be chosen. A size is
    orderable when there is stock, or when the article's pre-order window is open
    (`_stock_refusal` for a quantity of 1 — the one rule, R1); a size in pre-order
    with no stock carries `pre_order`, which the tile reads to say "op bestelling"
    instead of "uitverkocht"."""
    from app.domains.stock.api import available

    today = belgian_today()
    open_window, _until = pre_order_window(product, today)
    sizes: list[dict[str, Any]] = []
    for variant in variants_of(db, product.id):
        price = price_for(db, variant.id, today, member)
        if price is not None:
            in_stock = available(db, variant.id)
            sizes.append(
                {
                    "id": variant.id,
                    "name": size_of(variant),
                    "price": price,
                    "available": _stock_refusal(db, product, variant.id, 1, today) is None,
                    "pre_order": open_window and in_stock <= 0,
                }
            )
    return sizes


def article_media(
    db: Session, product_id: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The article's pictures and documents for the public pages (R1, R3): each
    picture carries its full URL, its thumbnail and its alt from the asset; each
    document carries its URL and title. Pictures first, in the article's order."""
    from app.domains.media.api import media_url
    from app.domains.product.api import attachment_cards
    from app.i18n import _

    photos: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    for card in attachment_cards(db, product_id):
        if card["is_photo"]:
            photos.append(
                {
                    "url": card["url"],
                    "thumb": media_url(card["media_asset_id"], thumb=True),
                    "alt": card["description"],
                }
            )
        else:
            documents.append(
                {
                    "url": card["url"],
                    "title": card["title"] or card["filename"] or _("Document"),
                }
            )
    return photos, documents


def offered_products(db: Session, *, member: bool = False) -> list[dict[str, Any]]:
    """The articles the shop offers today (F16, R40): in sale, with at least one
    size whose price is valid today. Each carries its offered sizes, the lowest of
    their prices and the first picture's thumbnail (R1)."""
    offered: list[dict[str, Any]] = []
    for product in list_products(db, active_only=True):
        sizes = _offered_sizes(db, product, member=member)
        if not sizes:
            continue
        photos, _documents = article_media(db, product.id)
        offered.append(
            {
                "id": product.id,
                "name": product.name,
                "sizes": [size["name"] for size in sizes],
                "price": min(size["price"] for size in sizes),
                "thumb": photos[0]["thumb"] if photos else None,
            }
        )
    return offered


def article_offer(db: Session, product_id: int, *, member: bool = False) -> dict[str, Any] | None:
    """One article's offer today — its name, description, the sizes with their
    prices, and its pictures and documents (R1, R3) — or None when it is not
    offered: not in sale, no size with a price valid today, of another tenant, or
    deleted.

    The product is read through the tenant-filtered read of `product`
    (`get_product_in_tenant`), not a load by key: a visitor types the id, and a
    primary-key load must not skip the tenant filter (H4, J4)."""
    product = get_product_in_tenant(db, product_id)
    if product is None or product.status is not ProductStatus.ON_SALE:
        return None
    sizes = _offered_sizes(db, product, member=member)
    if not sizes:
        return None
    photos, documents = article_media(db, product_id)
    return {
        "name": product.name,
        "description": product.description or "",
        "sizes": sizes,
        "photos": photos,
        "documents": documents,
    }


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
        refusal = _stock_refusal(db, product, variant_id, quantity, today)
        if refusal is not None:
            raise SalesError(refusal)
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


def _stock_refusal(
    db: Session, product: Product, variant_id: int, quantity: int, today: date
) -> str | None:
    """None when a line of `quantity` can be reserved — enough stock, or the
    article's pre-order window is open (R39, `allow_short`) — else the sentence
    naming the shortfall. The one rule the basket and the order share (Q1): a line
    the basket marks must be a line the order refuses, and the reverse."""
    from app.domains.stock.api import available
    from app.i18n import _

    open_window, _until = pre_order_window(product, today)
    if open_window:
        return None
    in_stock = available(db, variant_id)
    if in_stock < quantity:
        return _("Nog %(aantal)s op voorraad.") % {"aantal": in_stock}
    return None


def _orderable_max(
    db: Session, product: Product, variant_id: int, today: date, max_quantity: int
) -> int:
    """The most of a variant that can be ordered today: the tenant's maximum for a
    pre-order article (R39), else the stock capped at that maximum — the stepper's
    bound (Q2)."""
    from app.domains.stock.api import available

    open_window, _until = pre_order_window(product, today)
    if open_window:
        return max_quantity
    return min(available(db, variant_id), max_quantity)


def _basket_line(
    db: Session,
    *,
    variant_id: int,
    quantity: int,
    member: bool,
    today: date,
    max_quantity: int,
) -> dict[str, Any]:
    """One basket line in the one shape every caller reads: name, size, price,
    quantity, whether it is orderable (`available`), whether it keeps a stepper
    (`editable` — an orderable line, or one that is only too many), the stepper's
    `max`, and the sentence when it is not orderable. Built once, not per case."""
    from app.i18n import _

    def _make(
        *,
        available: bool,
        editable: bool,
        name: str | None,
        size: str,
        price,
        note: str,
        stepper_max: int,
    ) -> dict[str, Any]:
        return {
            "variant_id": variant_id,
            "name": name,
            "size": size,
            "price": price,
            "quantity": quantity,
            "available": available,
            "editable": editable,
            "note": note,
            "max": stepper_max,
        }

    variant = get_variant(db, variant_id)
    if variant is None:
        return _make(
            available=False,
            editable=False,
            name=None,
            size="",
            price=None,
            note=_("Dit artikel wordt niet meer aangeboden."),
            stepper_max=max_quantity,
        )
    product = get_product_in_tenant(db, variant.product_id)
    name = product.name if product else _("Het artikel")
    size = size_of(variant)
    if product is None or product.status is not ProductStatus.ON_SALE:
        return _make(
            available=False,
            editable=False,
            name=name,
            size=size,
            price=None,
            note=_("Dit artikel wordt niet meer aangeboden."),
            stepper_max=max_quantity,
        )
    price = price_for(db, variant_id, today, member)
    if price is None:
        return _make(
            available=False,
            editable=False,
            name=name,
            size=size,
            price=None,
            note=_("Dit artikel wordt niet meer aangeboden."),
            stepper_max=max_quantity,
        )
    if quantity > max_quantity:
        return _make(
            available=False,
            editable=True,
            name=name,
            size=size,
            price=price,
            note=_("Maximaal %(max)s per artikel.") % {"max": max_quantity},
            stepper_max=max_quantity,
        )
    refusal = _stock_refusal(db, product, variant_id, quantity, today)
    if refusal is not None:
        return _make(
            available=False,
            editable=True,
            name=name,
            size=size,
            price=price,
            note=refusal,
            stepper_max=_orderable_max(db, product, variant_id, today, max_quantity),
        )
    return _make(
        available=True,
        editable=True,
        name=name,
        size=size,
        price=price,
        note="",
        stepper_max=_orderable_max(db, product, variant_id, today, max_quantity),
    )


def basket_lines(
    db: Session, *, member: bool, items: list[tuple[int, int]]
) -> list[dict[str, Any]]:
    """The basket's lines as the checkout shows them — article, size, the price
    recomputed here (never from the browser, C5), the quantity, and whether the
    line can still be ordered (Koen's "ja op beide"): a line no longer offered
    keeps only "Verwijderen"; a line that is only too many keeps its stepper,
    bounded by what can be ordered; the rest of the basket stays orderable. Only a
    quantity below 1 is a refusal."""
    from app.i18n import _
    from app.kernel.tenant_config import tenant_max_item_quantity

    today = belgian_today()
    max_quantity = tenant_max_item_quantity(db)
    lines: list[dict[str, Any]] = []
    for variant_id, quantity in sorted(items, key=lambda item: item[0]):
        if quantity < 1:
            raise SalesError(_("Ongeldig aantal."))
        lines.append(
            _basket_line(
                db,
                variant_id=variant_id,
                quantity=quantity,
                member=member,
                today=today,
                max_quantity=max_quantity,
            )
        )
    return lines


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
    import httpx
    from fastapi import HTTPException

    from app.domains.mdm.api import PaymentMethod
    from app.domains.payment.api import PayableType
    from app.i18n import _
    from app.kernel.contracts.payment import CreatePayment
    from app.kernel.contracts.sales import SalesOrderPlaced
    from app.kernel.events import publish
    from app.kernel.ports import call
    from app.kernel.tenant_config import tenant_base_url

    if method not in (PaymentMethod.ONLINE, PaymentMethod.TRANSFER):
        raise SalesError(_("Kies online betalen of overschrijving."))

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
        except (ValueError, httpx.HTTPError) as exc:
            # The payment seam's own refusal (the provider refused, a missing key,
            # or it could not be reached) and an online payment without a checkout
            # url. A programming fault raises on, and is a 500 — never "the payment
            # could not start". Both branches end the same way: nothing placed,
            # nothing published (K1, L1).
            db.rollback()
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


def order_payment_state(db: Session, order_id: int) -> dict:
    """The order's payment state from `payment` — "open" or "settled" — with the
    amounts (R34). An order without a live booking has no state."""
    from app.domains.payment.api import order_payment_states

    return order_payment_states(db, [order_id]).get(order_id, {})


def board_order_person(db: Session, email: str) -> tuple[str, Any | None, bool]:
    """Who the board's typed address names (R43, F18, T22): `(status, person,
    member)` with `status` "linked" (a household's member), "account" (a person
    without a household, so never a member), "unknown" (no one signs in with it)
    or "multiple" (the address does not say who). The order hangs on the person,
    never on the seller."""
    from app.domains.auth.api import sign_in_identity
    from app.domains.membership.api import has_valid_membership
    from app.kernel.clock import belgian_today

    typed = (email or "").strip()
    if "@" not in typed:
        return "unknown", None, False
    status, person = sign_in_identity(db, typed)
    if status == "multiple":
        return "multiple", None, False
    if status == "none":
        return "unknown", None, False
    linked = "linked" if status == "ok" else "account"
    return linked, person, has_valid_membership(person, belgian_today())


def parse_items(form) -> tuple[list[tuple[int, int]], str | None]:
    """The `(variant_id, quantity)` pairs the basket or the board's order form
    posts, the same variant summed to one line. Returns `(items, error)` — `error`
    a sentence when the two posted lists do not line up or a value is not a
    number (a doubled variant is not an error, it is one line)."""
    from app.i18n import _

    try:
        variant_ids = [int(str(v)) for v in form.getlist("variant_id")]
        quantities = [int(str(q)) for q in form.getlist("quantity")]
    except ValueError:
        return [], _("Ongeldig aantal.")
    if len(variant_ids) != len(quantities):
        return [], _("Ongeldig aantal.")
    merged: dict[int, int] = {}
    for variant_id, quantity in zip(variant_ids, quantities):
        merged[variant_id] = merged.get(variant_id, 0) + quantity
    return sorted(merged.items()), None


def order_delivery_state(db: Session, order) -> str:
    """The order's delivery status from its lines (F5): "Wordt besteld" while
    nothing is delivered and a line still waits for the supplier, else "Klaar om
    af te halen", "Deels afgeleverd" or "Afgeleverd"."""
    from app.domains.stock.api import waiting
    from app.i18n import _

    lines = order.lines
    if not lines:
        return _("Klaar om af te halen")
    delivered = sum(1 for line in lines if line.delivered_at is not None)
    if delivered == 0:
        if waiting(db, [line.id for line in lines]):
            return _("Wordt besteld")
        return _("Klaar om af te halen")
    if delivered == len(lines):
        return _("Afgeleverd")
    return _("Deels afgeleverd")


def list_orders(db: Session) -> list[dict[str, Any]]:
    """Verkoop's list: every order, newest first, with its payment and delivery
    state and the buyer's name (F5, R34)."""
    from app.domains.mdm.api import Person
    from app.domains.payment.api import order_payment_states
    from app.domains.sales.models import SalesOrder

    orders = db.query(SalesOrder).order_by(SalesOrder.id.desc()).all()
    person_ids = {o.person_id for o in orders if o.person_id is not None}
    persons = (
        {p.id: p for p in db.query(Person).filter(Person.id.in_(person_ids))} if person_ids else {}
    )
    states = order_payment_states(db, [o.id for o in orders]) if orders else {}
    return [
        {
            "id": order.id,
            "placed_at": order.placed_at,
            "contact_name": (
                f"{persons[order.person_id].first_name} {persons[order.person_id].last_name}".strip()
                if order.person_id in persons
                else order.guest_name or ""
            ),
            "payment": states.get(order.id, {}).get("state", ""),
            "delivery": order_delivery_state(db, order),
        }
        for order in orders
    ]


def deliver_line(db: Session, order_id: int, line_id: int, *, actor: str | None) -> None:
    """Deliver one line (F6, R21): `stock.api.issue` writes the GOODS_ISSUE and
    closes the reservation, and the line's `delivered_at` is set — one transaction.

    The line is read under a row lock, so two deliveries of one line cannot both
    pass the `delivered_at` check. A line can be delivered only while it holds an
    open reservation the stock covers; otherwise the service refuses in words: a
    delivered line again, a line that waits for the supplier, or a line whose
    reservation is gone — the stock and the state never disagree.
    """
    from datetime import datetime, timezone

    from app.domains.sales.models import SalesOrder, SalesOrderLine
    from app.domains.stock.api import NotEnoughStock, open_reservation_lines, waiting
    from app.i18n import _
    from app.kernel.contracts.stock import IssueStock
    from app.kernel.ports import call

    order = db.query(SalesOrder).filter(SalesOrder.id == order_id).one_or_none()
    if order is None:
        raise SalesError(_("Deze bestelling bestaat niet."))
    line = (
        db.query(SalesOrderLine)
        .filter(SalesOrderLine.id == line_id, SalesOrderLine.order_id == order_id)
        .with_for_update()
        .one_or_none()
    )
    if line is None:
        raise SalesError(_("Deze regel hoort niet bij deze bestelling."))
    if line.delivered_at is not None:
        raise SalesError(_("Deze regel is al geleverd."))
    if line.id not in open_reservation_lines(db, [line.id]):
        raise SalesError(_("Deze regel is al geleverd."))
    if waiting(db, [line.id]):
        raise SalesError(_("Deze regel wacht nog op de leverancier."))
    try:
        call(IssueStock(order_line_id=line.id, actor=actor), db)
    except NotEnoughStock as exc:
        raise SalesError(_("Deze regel wacht nog op de leverancier.")) from exc
    line.delivered_at = datetime.now(timezone.utc)
    db.commit()


def cancel_order(db: Session, order_id: int, *, actor: str | None) -> None:
    """Cancel the whole order (F8): the reservations free the stock, the order is
    soft-deleted and leaves the lists, and `SalesOrderChanged(order_id, 0, actor)`
    brings a paid order's refund. Refused once a line is delivered."""
    from app.domains.sales.models import SalesOrder
    from app.i18n import _
    from app.kernel.contracts.sales import SalesOrderChanged
    from app.kernel.contracts.stock import ReleaseStock
    from app.kernel.events import publish
    from app.kernel.ports import call
    from app.soft_delete import soft_delete

    order = db.query(SalesOrder).filter(SalesOrder.id == order_id).one_or_none()
    if order is None:
        raise SalesError(_("Deze bestelling bestaat niet."))
    if any(line.delivered_at is not None for line in order.lines):
        raise SalesError(_("Een geleverde bestelling kan niet geannuleerd worden."))
    for line in order.lines:
        call(ReleaseStock(order_line_id=line.id), db)
    soft_delete(order)
    publish(SalesOrderChanged(order_id=order.id, total_due="0", actor=actor), db)
    db.commit()


def order_view(db: Session, order) -> dict[str, Any]:
    """The order page's data (D6): the lines with their article and size, the
    contact, the payment and delivery states, and the total. The same view-model
    the site shell and the admin shell both render."""
    from app.domains.mdm.api import Person
    from app.domains.product.api import get_variant, size_of
    from app.i18n import _

    contact_name = order.guest_name or ""
    if order.person_id is not None:
        person = db.get(Person, order.person_id)
        if person is not None:
            contact_name = f"{person.first_name} {person.last_name}".strip()

    from app.domains.stock.api import open_reservation_lines, waiting

    line_ids = [line.id for line in order.lines]
    open_lines = open_reservation_lines(db, line_ids)
    waiting_lines = set(waiting(db, line_ids))

    lines = []
    for line in order.lines:
        variant = get_variant(db, line.variant_id)
        lines.append(
            {
                "id": line.id,
                "name": variant.product.name if variant is not None else _("Artikel"),
                "size": size_of(variant) if variant is not None else "",
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "delivered": line.delivered_at is not None,
                "deliverable": line.id in open_lines and line.id not in waiting_lines,
            }
        )

    return {
        "id": order.id,
        "placed_at": order.placed_at,
        "contact_name": contact_name,
        "lines": lines,
        "payment": order_payment_state(db, order.id).get("state", ""),
        "delivery": order_delivery_state(db, order),
        "total": total_of(order),
        "cancellable": all(line.delivered_at is None for line in order.lines),
    }
