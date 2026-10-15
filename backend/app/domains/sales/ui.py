"""The Webshop's public pages (CR-21, phase 2).

`/webshop` lists the tenant's articles on offer; `/webshop/{product_id}` is one
article with its sizes and prices. What is on offer — and at which price for
whom — lives in the service (`sales.service`), so the list, the article page, the
basket and the order all ask the same rule. `/webshop/bestellen` places the order;
`/mijn/aankopen` lists the buyer's orders and `/mijn/aankopen/{id}` is one order.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.sales.api import (
    article_offer,
    basket_lines,
    get_order,
    offered_products,
    orders_of_person,
    owned_order,
    submit_order,
)
from app.domains.sales.viewmodels import (
    BasketView,
    BedanktView,
    WebshopProductView,
    WebshopView,
)
from app.i18n import _
from app.limiter import order_limiter
from app.ui import site_context, templates

router = APIRouter()


def _buyer(request: Request, db: Session) -> tuple[int | None, bool]:
    """`(person_id, member)` of the signed-in person, or `(None, False)`."""
    from app.domains.membership.api import has_valid_membership
    from app.kernel.clock import belgian_today
    from app.ui.account_ui import signed_in_person

    signed_in, person = signed_in_person(request, db)
    if not signed_in or person is None:
        return None, False
    return person.id, has_valid_membership(person, belgian_today())


def _member(request: Request, db: Session) -> bool:
    """Is the signed-in person a member with a valid membership today? (F3, R11)."""
    return _buyer(request, db)[1]


def _parse_items(form) -> tuple[list[tuple[int, int]], str | None]:
    """The basket's `(variant_id, quantity)` pairs, the same variant summed to one
    line. Returns `(items, error)` — `error` a sentence when the two posted lists
    do not line up or a value is not a number (a doubled variant is not an error,
    it is one line)."""
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


@router.get("/webshop", response_class=HTMLResponse)
def webshop(request: Request, db: Session = Depends(get_db)):
    member = _member(request, db)
    vm = WebshopView(
        products=offered_products(db, member=member),
        site=site_context(db, request),
    )
    return templates.TemplateResponse(request, "webshop.html", vm.as_context())


@router.get("/webshop/bedankt", response_class=HTMLResponse)
def bedankt(request: Request, order: int | None = None, db: Session = Depends(get_db)):
    """The shop's thank-you page (Q60, Q78): after an online payment the provider
    returns here and the page reads the ledger; after a transfer the placing
    redirects here. Registered before `/webshop/{product_id}` so the fixed path
    wins over the parameter; without an `order` it sends the visitor to the shop
    instead of FastAPI's raw JSON 422."""
    if order is None:
        return RedirectResponse("/webshop", status_code=303)
    found = get_order(db, order)
    if found is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    vm = BedanktView(order=found, order_id=found.id, site=site_context(db, request))
    return templates.TemplateResponse(request, "webshop_bedankt.html", vm.as_context())


@router.get("/webshop/{product_id}", response_class=HTMLResponse)
def webshop_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    member = _member(request, db)
    offer = article_offer(db, product_id, member=member)
    if offer is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    prices = [size["price"] for size in offer["sizes"]]
    vm = WebshopProductView(
        name=offer["name"],
        description=offer["description"],
        price=min(prices),
        from_price=len(set(prices)) > 1,
        sizes=offer["sizes"],
        photos=offer["photos"],
        documents=offer["documents"],
        site=site_context(db, request),
    )
    return templates.TemplateResponse(request, "webshop_product.html", vm.as_context())


@router.post("/webshop/mandje", response_class=HTMLResponse)
async def mandje(request: Request, db: Session = Depends(get_db)) -> Response:
    """The basket, which IS the order page (CR-14 B4.1): the browser posts its
    basket (variant ids and quantities), the server recomputes every price (C5).
    A refusal is a whole page in the shell, never an htmx fragment."""
    from decimal import Decimal

    from app.domains.sales.api import SalesError

    def _vm(*, lines, total, error="") -> BasketView:
        return BasketView(
            lines=lines,
            total=total,
            member_applied=member,
            error=error,
            site=site_context(db, request),
        )

    form = await request.form()
    items, parse_error = _parse_items(form)
    person_id, member = _buyer(request, db)
    if parse_error is not None:
        return templates.TemplateResponse(
            request,
            "webshop_mandje.html",
            _vm(lines=[], total=Decimal("0"), error=parse_error).as_context(),
        )

    try:
        lines = basket_lines(db, member=member, items=items)
    except SalesError as exc:
        return templates.TemplateResponse(
            request,
            "webshop_mandje.html",
            _vm(lines=[], total=Decimal("0"), error=str(exc)).as_context(),
        )

    total = sum(
        (line["price"] * line["quantity"] for line in lines if line["available"]),
        Decimal("0"),
    )
    return templates.TemplateResponse(
        request, "webshop_mandje.html", _vm(lines=lines, total=total).as_context()
    )


@router.post(
    "/webshop/bestellen",
    response_class=HTMLResponse,
    dependencies=[Depends(order_limiter)],
)
async def order_submit(request: Request, db: Session = Depends(get_db)) -> Response:
    """Place the order (C4.1, C5): every price recomputed, the lines reserved, the
    payment started, all in one transaction."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import SalesError
    from app.kernel.refusals import FieldError
    from app.ui import refusal_response

    form = await request.form()
    try:
        method = PaymentMethod(str(form.get("payment_method") or "online"))
    except ValueError:
        return refusal_response(
            request,
            [FieldError("", _("Ongeldig aantal of betaalwijze."))],
            "#bestel-melding",
            send=True,
        )
    items, parse_error = _parse_items(form)
    if parse_error is not None:
        return refusal_response(
            request, [FieldError("", parse_error)], "#bestel-melding", send=True
        )
    contact_name = str(form.get("contact_name") or "").strip()
    contact_email = str(form.get("contact_email") or "").strip()
    phone = str(form.get("phone") or "").strip()
    person_id, member = _buyer(request, db)

    try:
        checkout_url, order_id = submit_order(
            db,
            person_id=person_id,
            member=member,
            contact_name=contact_name,
            contact_email=contact_email,
            phone=phone,
            method=method,
            items=items,
        )
    except SalesError as exc:
        return refusal_response(request, [FieldError("", str(exc))], "#bestel-melding", send=True)

    response = HTMLResponse("")
    if method == PaymentMethod.ONLINE:
        response.headers["HX-Redirect"] = checkout_url or ""
    else:
        response.headers["HX-Redirect"] = f"/webshop/bedankt?order={order_id}"
    return response


@router.get("/mijn/aankopen", response_class=HTMLResponse)
def my_orders(request: Request, db: Session = Depends(get_db)):
    """The buyer's orders (AC13, W26): one card per order, newest first."""
    from app.domains.sales.viewmodels import MyOrdersView

    person_id, _is_member = _buyer(request, db)
    if person_id is None:
        from app.ui.account_ui import to_sign_in

        return to_sign_in(request)
    vm = MyOrdersView(
        orders=orders_of_person(db, person_id),
        site=site_context(db, request),
    )
    return templates.TemplateResponse(request, "mijn_aankopen.html", vm.as_context())


@router.get("/mijn/aankopen/{order_id}", response_class=HTMLResponse)
def my_order(request: Request, order_id: int, db: Session = Depends(get_db)):
    """One order of the buyer or of his household (C5: any other id is a 404)."""
    from app.domains.sales.api import order_view
    from app.domains.sales.viewmodels import OrderPageView

    person_id, _is_member = _buyer(request, db)
    order = owned_order(db, order_id, person_id)
    if order is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    vm = OrderPageView(order=order_view(db, order), is_admin=False, site=site_context(db, request))
    return templates.TemplateResponse(request, "webshop_order.html", vm.as_context())
