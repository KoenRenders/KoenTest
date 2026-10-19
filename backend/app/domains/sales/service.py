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
from app.domains.sales.models import SalesError, ShopContact, ShopSettings
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
    submission_key: str | None = None,
    buyer_organization_id: int | None = None,
):
    """Place an order: every price recomputed, the lines and their reservations
    written (C4.1, C5, F1).

    `buyer_organization_id` (CR-26 F8): the order is for an organisation, bought
    *namens* by the person who placed it. Refused unless the invoices module is on
    for the tenant, in the back office too (R13: a rule of the service). The order
    copies the buyer — name, address, VAT number — as they stand now.

    Nothing the browser sent is an amount — each line's price comes from
    `price_for` here. The variants are reserved in a fixed order (by variant id),
    stock before payment, and the first refusal raises, so nothing is reserved
    half (the door rolls the whole order back). An article "Op bestelling" whose
    window is open reserves with `allow_short` (R39).

    Returns the `SalesOrder` (its lines carry the prices); the total is the sum of
    the line amounts, `total_of`.
    """
    import secrets

    from sqlalchemy.exc import IntegrityError

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
    # #1987: the unique submission key is the one thing that may clash when the
    # same form is posted twice at once. A savepoint takes the failed insert back,
    # so the caller (the door) can look the first order up and answer with it.
    savepoint = db.begin_nested()
    try:
        order = SalesOrder(
            person_id=person_id,
            guest_name=guest_name,
            guest_email=guest_email,
            guest_mobile=guest_mobile,
            payment_method=method,
            submission_key=submission_key,
            secret_key=secrets.token_urlsafe(32),
            **_buyer_columns(db, person_id, buyer_organization_id),
        )
        db.add(order)
        db.flush()
        for variant_id, quantity in items:
            if quantity < 1 or quantity > max_quantity:
                raise SalesError(
                    _("Ongeldig aantal: kies een waarde tussen 1 en %(max)s.")
                    % {"max": max_quantity}
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
    except IntegrityError:
        # #1987: a clash on the unique submission key — roll the failed insert
        # back and let the caller decide (form_guard.is_repeat).
        savepoint.rollback()
        raise
    except Exception:
        savepoint.rollback()
        raise
    savepoint.commit()
    return order


def _buyer_columns(db: Session, person_id: int | None, organization_id: int | None) -> dict:
    """`buyer_party_id` and the buyer copy of an order (CR-26 F8).

    *Namens*: the organisation's party and its data, only at a tenant with the
    invoices module on. *Voor mezelf*: the signed-in person's own party, name and
    address. A guest: nothing — the invoice of CR-34 will read the one copy that
    is there. The copy keeps what the invoice must show even when the party later
    changes or is deleted."""
    from app.domains.mdm.api import buyer_copy_of_organisation, module_enabled, person_buyer_copy
    from app.i18n import _
    from app.kernel.modules import ModuleCode

    if organization_id is not None:
        if not module_enabled(ModuleCode.INVOICES):
            raise SalesError(_("Bestellen namens een organisatie kan hier niet."))
        copy = buyer_copy_of_organisation(db, organization_id)
        if not copy:
            raise SalesError(_("Deze organisatie bestaat niet meer."))
    elif person_id is not None:
        copy = person_buyer_copy(db, person_id)
    else:
        return {}
    party_id = copy.pop("party_id", None)
    return {"buyer_party_id": party_id, **{f"buyer_{key}": value for key, value in copy.items()}}


def has_orders(db: Session, party_id: int, tenant_id: int | None = None) -> bool:
    """Is this party a customer here — did it buy, or did a person of that party
    place an order? The one place *klant* is read from (CR-26 F11: no role is
    stored). `tenant_id` names the tenant when the call is not inside one."""
    from sqlalchemy import or_

    from app.domains.mdm.api import Person
    from app.domains.sales.models import SalesOrder

    person_ids = db.query(Person.id).filter(Person.party_id == party_id).scalar_subquery()
    query = db.query(SalesOrder.id).filter(
        or_(SalesOrder.buyer_party_id == party_id, SalesOrder.person_id.in_(person_ids))
    )
    if tenant_id is not None:
        query = query.execution_options(include_all_tenants=True).filter(
            SalesOrder.tenant_id == tenant_id
        )
    return query.first() is not None


def total_of(order) -> Decimal:
    """The total of an order's lines (their fixed prices times their quantities)."""
    return sum((line.unit_price * line.quantity for line in order.lines), Decimal("0"))


def _stock_refusal(
    db: Session, product: Product, variant_id: int, quantity: int, today: date
) -> str | None:
    """None when a line of `quantity` can be reserved — enough stock, or the
    article's pre-order window is open (R39, `allow_short`) — else the sentence
    naming the shortfall: the stock and what can be ordered today (the stepper's
    bound), or "Uitverkocht." without stock (#2104). The one rule the basket and the
    order share (Q1): a line the basket marks must be a line the order refuses, and
    the reverse."""
    from app.domains.stock.api import available
    from app.i18n import _
    from app.kernel.tenant_config import tenant_max_item_quantity

    open_window, _until = pre_order_window(product, today)
    if open_window:
        return None
    in_stock = available(db, variant_id)
    if in_stock >= quantity:
        return None
    if in_stock <= 0:
        return _("Uitverkocht.")
    orderable = _orderable_max(db, product, variant_id, today, tenant_max_item_quantity(db))
    return _("Nog %(aantal)s op voorraad, maximaal %(max)s bestelbaar.") % {
        "aantal": in_stock,
        "max": orderable,
    }


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
    kept_price=None,
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
    price = kept_price if kept_price is not None else price_for(db, variant_id, today, member)
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
    db: Session, *, member: bool, items: list[tuple[int, int]], kept_prices=None
) -> list[dict[str, Any]]:
    """The basket's lines as the checkout shows them — article, size, the price
    recomputed here (never from the browser, C5), the quantity, and whether the
    line can still be ordered (Koen's "ja op beide"): a line no longer offered
    keeps only "Verwijderen"; a line that is only too many keeps its stepper,
    bounded by what can be ordered; the rest of the basket stays orderable. Only a
    quantity below 1 is a refusal. `kept_prices` is a list aligned with the sorted
    items — the price of each kept line, `None` for a new one (A6) — so the change
    form shows the price the save will write."""
    from app.i18n import _
    from app.kernel.tenant_config import tenant_max_item_quantity

    today = belgian_today()
    max_quantity = tenant_max_item_quantity(db)
    kept = kept_prices or []
    lines: list[dict[str, Any]] = []
    for index, (variant_id, quantity) in enumerate(sorted(items, key=lambda item: item[0])):
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
                kept_price=kept[index] if index < len(kept) else None,
            )
        )
    return lines


class Honeypot(Exception):
    """A bot filled the honeypot: the order is dropped with no word (#1297)."""


def submit_order(
    db: Session,
    *,
    proof: Any,
    values: Any,
    person_id: int | None,
    member: bool,
    contact_name: str,
    contact_email: str,
    phone: str,
    method: Any,
    items: list[tuple[int, int]],
    buyer_organization_id: int | None = None,
) -> tuple[str | None, int, str | None]:
    """The whole placing flow (C4.1, C5, #1987): place, start the payment, publish,
    commit. A shown form is accepted once — a second post answers with the first
    order, never a second payment.

    Returns `(checkout_url, order_id, secret_key)` — `checkout_url` only for an
    online order, `secret_key` the thank-you page's key.
    Raises `SalesError` for a refusal (the door answers 422, the order rolled
    back); raises `HTTPException(502)` when an online payment cannot start (the
    order is rolled back, nothing reserved); raises `form_guard.NotSent` when the
    form is not ours; raises `Honeypot` for a bot.
    """
    import httpx
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError

    from app.domains.mdm.api import PaymentMethod
    from app.domains.payment.api import PayableType
    from app.domains.sales.models import SUBMISSION_KEY_CONSTRAINT
    from app.i18n import _
    from app.kernel import form_guard
    from app.kernel.contracts.payment import CreatePayment
    from app.kernel.contracts.sales import SalesOrderPlaced
    from app.kernel.events import publish
    from app.kernel.ports import call
    from app.kernel.tenant_config import tenant_base_url

    if form_guard.refused(proof, "order"):
        raise Honeypot()
    key = form_guard.submission_key(values)
    if key is None:
        raise form_guard.NotSent(form_guard.Refusal.BAD_TOKEN)

    # #1987: before every rule — the first post may have changed what a rule says.
    earlier = order_for_submission(db, key)
    if earlier is not None:
        return order_again(db, earlier)

    if method not in (PaymentMethod.ONLINE, PaymentMethod.TRANSFER):
        raise SalesError(_("Kies online betalen of overschrijving."))
    # #2121: the basket asks the buyer's mobile, so the buyer's own order carries
    # one — signed in or not (a guest's is also the aggregate's rule, `check()`).
    # The board's order has no phone field and promises none: it comes through
    # the trusted door and keeps the person's own details.
    if proof is not form_guard.TRUSTED and not phone.strip():
        raise SalesError(_("Vul je mobiele nummer in."), field="phone")

    if buyer_organization_id is not None:
        # *Namens* is a person's, for an organisation he acts for, at the shop and in
        # Verkoop alike (Q13: no confirmation step, but no order without the relation).
        from app.domains.mdm.api import acts_for

        if person_id is None or not acts_for(db, person_id, buyer_organization_id):
            raise SalesError(_("Je bestelt niet namens deze organisatie."))

    try:
        order = place_order(
            db,
            person_id=person_id,
            buyer_organization_id=buyer_organization_id,
            guest_name=contact_name,
            guest_email=contact_email,
            guest_mobile=phone,
            method=method,
            items=items,
            member=member,
            submission_key=key,
        )
    except SalesError:
        db.rollback()
        # The same form posted twice within milliseconds — the first committed
        # after this one looked its key up, so this one met a rule the first
        # changed. The order exists: answer with it, not with the refusal.
        earlier = order_for_submission(db, key)
        if earlier is not None:
            return order_again(db, earlier)
        raise
    except IntegrityError as clash:
        # #1987: the same form posted twice at the same moment. Both found no
        # order and both inserted; the unique key let one through. `place_order`
        # took its insert back to its savepoint, so the read sees the winner.
        if not form_guard.is_repeat(clash, SUBMISSION_KEY_CONSTRAINT):
            raise
        earlier = order_for_submission(db, key)
        if earlier is None:
            raise
        return order_again(db, earlier)

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
                    redirect_url=f"{tenant_base_url(db)}/webshop/bedankt?key={order.secret_key}",
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
    return checkout_url, order.id, order.secret_key


def get_order(db: Session, order_id: int):
    """The order, or None — for the thank-you page, which shows no ownership."""
    from app.domains.sales.models import SalesOrder

    return db.query(SalesOrder).filter(SalesOrder.id == order_id).one_or_none()


def order_for_submission(db: Session, key: str):
    """The order a shown form already made, or None (#1987): the form is accepted
    once, and a second post of it answers with this one."""
    from app.domains.sales.models import SalesOrder

    return db.query(SalesOrder).filter(SalesOrder.submission_key == key).first()


def order_again(db: Session, order) -> tuple[str | None, int, str | None]:
    """What a second post of a form answers: the first order (D4, #1987). The same
    provider checkout while that payment is still pending — never a second payment —
    else the thank-you page's order."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.payment.api import (
        PayableType,
        PaymentStatus,
        checkout_url_for,
        get_records_for,
    )

    if order.payment_method == PaymentMethod.ONLINE:
        for record in get_records_for(db, PayableType.ORDER, order.id):
            url = checkout_url_for(db, record) if record.status == PaymentStatus.PENDING else None
            if url:
                return url, order.id, order.secret_key
    return None, order.id, order.secret_key


def order_by_secret_key(db: Session, secret_key: str):
    """The order whose thank-you link carries this key, or None (Koen, 16 October
    2026): the page opens only for the order whose key it is."""
    from app.domains.sales.models import SalesOrder

    return db.query(SalesOrder).filter(SalesOrder.secret_key == secret_key).first()


def order_person_email(db: Session, order) -> str:
    """The e-mail the order's person signs in with, or "" — for the board's change
    form, which prices the lines as that person."""
    from app.domains.mdm.api import CONTACT, Person

    if order.person_id is None:
        return ""
    person = db.get(Person, order.person_id)
    if person is None:
        return ""
    email = person.primary_contact(CONTACT.EMAIL)
    return email.value if email else ""


def order_person_member(db: Session, order) -> bool:
    """Whether the order's person is a member today — the one price source for a
    changed order (the form and the service both ask it)."""
    from app.domains.mdm.api import Person
    from app.domains.membership.api import has_valid_membership

    if order.person_id is None:
        return False
    person = db.get(Person, order.person_id)
    return has_valid_membership(person, belgian_today()) if person is not None else False


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


def parse_lines(form) -> tuple[list[tuple[int, int]], str | None]:
    """The `(variant_id, quantity)` pairs the change form posts, kept apart — two
    lines of one variant stay two lines, so a line can be split (F7, Q30). The
    posted order is kept, never sorted: the form's × posts a line's position, so
    the order here must be the order the form renders (B5); the service sorts its
    own target."""
    from app.i18n import _

    try:
        variant_ids = [int(str(v)) for v in form.getlist("variant_id")]
        quantities = [int(str(q)) for q in form.getlist("quantity")]
    except ValueError:
        return [], _("Ongeldig aantal.")
    if len(variant_ids) != len(quantities):
        return [], _("Ongeldig aantal.")
    return list(zip(variant_ids, quantities)), None


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


def change_plan(
    db: Session, order, target: list[tuple[int, int]]
) -> tuple[list[Decimal | None], list[bool], list]:
    """Split a change's target against the order's lines.

    - `prices` is a list aligned with the sorted target: the price each line will
      get. A variant that already stands in the order keeps its price — a changed
      quantity and a split keep it too (Koen's "b") — and a new variant is `None`,
      to be priced today.
    - `kept` is True where the target is the same line (same variant and quantity),
      so its line object and its reservation stay.
    - `to_remove` is the undelivered lines the target drops.

    Delivered lines are matched first (B3), so a delivered line keeps its slot and
    an identical undelivered line is the one removed."""
    target = sorted(target, key=lambda item: item[0])
    ordered = sorted(order.lines, key=lambda line: line.delivered_at is None)

    prices: list[Decimal | None] = [None] * len(target)
    kept = [False] * len(target)
    matched = [False] * len(target)
    to_remove: list = []
    for line in ordered:
        key = (line.variant_id, line.quantity)
        for index, item in enumerate(target):
            if item == key and not matched[index]:
                matched[index] = True
                kept[index] = True
                prices[index] = line.unit_price  # its own price, a twin included
                break
        else:
            if line.delivered_at is None:
                to_remove.append(line)

    # A line that is not the same line but whose variant stays — a changed quantity
    # or a split — keeps the variant's old price (Koen's "b").
    variant_prices: dict[int, Decimal] = {}
    for line in ordered:
        variant_prices.setdefault(line.variant_id, line.unit_price)
    for index, (variant_id, _quantity) in enumerate(target):
        if not kept[index]:
            prices[index] = variant_prices.get(variant_id)

    return prices, kept, to_remove


def change_order_lines(
    db: Session, order_id: int, items: list[tuple[int, int]], *, actor: str | None
) -> None:
    """Replace the order's lines (R15, R16, F7): a line whose variant stays — the
    same line, a changed quantity, or a split — keeps its price (Koen, "b"); only a
    new variant takes today's price. The old reservations release first, then the new
    lines reserve, in one savepoint, so a change that keeps the order's own last unit
    is not refused for it and a refusal leaves the old lines as they were. A delivered
    line cannot be changed (a return is by hand, R25): a change that touches one is
    refused, naming it; the other lines of that order can still change.
    `SalesOrderChanged` lets payment recalculate."""
    from app.domains.sales.models import SalesOrder, SalesOrderLine
    from app.domains.stock.api import NotEnoughStock
    from app.i18n import _
    from app.kernel.contracts.sales import SalesOrderChanged
    from app.kernel.contracts.stock import ReleaseStock, ReserveStock
    from app.kernel.events import publish
    from app.kernel.ports import call
    from app.kernel.tenant_config import tenant_max_item_quantity
    from app.soft_delete import soft_delete

    order = db.query(SalesOrder).filter(SalesOrder.id == order_id).one_or_none()
    if order is None:
        raise SalesError(_("Deze bestelling bestaat niet."))

    target = sorted(items, key=lambda item: item[0])
    if not target:
        raise SalesError(_("Je mandje is leeg."))
    max_quantity = tenant_max_item_quantity(db)
    today = belgian_today()
    member = order_person_member(db, order)

    for variant_id, quantity in target:
        if quantity < 1 or quantity > max_quantity:
            raise SalesError(
                _("Ongeldig aantal: kies een waarde tussen 1 en %(max)s.") % {"max": max_quantity}
            )

    # A delivered line the target no longer keeps is refused, naming the size: the
    # target must keep at least as many of each delivered line as the order holds
    # (two delivered twins count as two).
    from collections import Counter

    delivered_counts = Counter(
        (line.variant_id, line.quantity) for line in order.lines if line.delivered_at is not None
    )
    target_counts = Counter(target)
    for key, count in delivered_counts.items():
        if target_counts.get(key, 0) < count:
            variant = get_variant(db, key[0])
            size = size_of(variant) if variant is not None else ""
            raise SalesError(
                _("Maat %(size)s is al geleverd en kan niet gewijzigd worden.")
                % {"size": size or str(key[0])}
            )

    # The lines the target keeps — delivered or not — stay; the undelivered ones it
    # does not keep are released and soft-deleted. `kept` marks which target positions
    # are the same line (their price and reservation stay); a line that only changes
    # quantity or is split keeps its variant's price (`prices`).
    prices, kept, to_remove = change_plan(db, order, target)

    savepoint = db.begin_nested()
    try:
        for line in to_remove:
            call(ReleaseStock(order_line_id=line.id), db)
            soft_delete(line)
        for index, (variant_id, quantity) in enumerate(target):
            if kept[index]:
                continue  # the same line: its price and its reservation stay
            variant = get_variant(db, variant_id)
            if variant is None:
                raise SalesError(_("Dit artikel wordt niet meer aangeboden."))
            product = get_product_in_tenant(db, variant.product_id)
            if product is None or product.status is not ProductStatus.ON_SALE:
                raise SalesError(_("Dit artikel wordt niet meer aangeboden."))
            price = prices[index]
            if price is None:
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
    except Exception:
        savepoint.rollback()
        raise
    savepoint.commit()

    db.expire(order, ["lines"])
    publish(
        SalesOrderChanged(order_id=order.id, total_due=str(total_of(order)), actor=actor),
        db,
    )
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
        # A1: an online order whose open booking became a transfer (a change
        # dropped the online checkout) pays by transfer now.
        "online_checkout_stale": _online_checkout_stale(db, order),
    }


def _online_checkout_stale(db: Session, order) -> bool:
    from app.domains.mdm.api import PaymentMethod
    from app.domains.payment.api import PaymentRecord

    if order.payment_method is not PaymentMethod.ONLINE:
        return False
    booking_id = order_payment_state(db, order.id).get("booking_id")
    if not booking_id:
        return False
    record = db.get(PaymentRecord, booking_id)
    return record is not None and record.method is not PaymentMethod.ONLINE


def shop_settings(db: Session) -> ShopSettings:
    """The tenant's shop settings, made on first ask (F17, R42)."""
    settings = db.query(ShopSettings).first()
    if settings is None:
        settings = ShopSettings()
        db.add(settings)
        db.flush()
    return settings


def save_shop_intro(db: Session, intro: str) -> ShopSettings:
    """Save the intro text above the Webshop (R42); an empty text clears it."""
    settings = shop_settings(db)
    settings.intro = intro.strip() or None
    db.commit()
    return settings


def shop_contacts(db: Session) -> list[ShopContact]:
    """The shop's contact persons, in their chosen order (R41)."""
    return db.query(ShopContact).order_by(ShopContact.sort_order, ShopContact.id).all()


def add_shop_contact(db: Session, person_id: int) -> None:
    """Add a person as a contact, once (R41): the same person twice is one row. A
    person who does not exist is refused — the row would be skipped on the pages
    but still stand."""
    from app.domains.mdm.api import Person
    from app.i18n import _

    if db.get(Person, person_id) is None:
        raise SalesError(_("Deze persoon is niet gekend."))
    existing = db.query(ShopContact).filter(ShopContact.person_id == person_id).first()
    if existing is None:
        db.add(ShopContact(person_id=person_id, sort_order=db.query(ShopContact).count()))
        db.commit()


def remove_shop_contact(db: Session, contact_id: int) -> None:
    """Remove a contact person (R41): soft-deleted, as everything in this domain
    that a later row may have pointed at."""
    from app.soft_delete import soft_delete

    contact = db.get(ShopContact, contact_id)
    if contact is not None:
        soft_delete(contact)
        db.commit()


def shop_contact_cards(db: Session) -> list[dict[str, Any]]:
    """The contact persons for the buyer (R41, Q71): name, e-mail and mobile, as
    the person holds them — no other address or number. The `id` and `person_id`
    ride along for the settings screen; the pages read the three shown fields."""
    from app.domains.mdm.api import CONTACT, Person

    cards: list[dict[str, Any]] = []
    for contact in shop_contacts(db):
        person = db.get(Person, contact.person_id)
        if person is None:
            continue
        email = person.primary_contact(CONTACT.EMAIL)
        mobile = person.primary_contact(CONTACT.MOBILE)
        cards.append(
            {
                "id": contact.id,
                "person_id": contact.person_id,
                "name": f"{person.first_name} {person.last_name}".strip(),
                "email": email.value if email else "",
                "mobile": mobile.value if mobile else "",
            }
        )
    return cards
