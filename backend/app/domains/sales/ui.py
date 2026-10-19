"""The Webshop's public pages (CR-21, phase 2).

`/webshop` lists the tenant's articles on offer; `/webshop/{product_id}` is one
article with its sizes and prices. What is on offer — and at which price for
whom — lives in the service (`sales.service`), so the list, the article page, the
basket and the order all ask the same rule. `/webshop/bestellen` places the order;
`/mijn/aankopen` lists the buyer's orders and `/mijn/aankopen/{id}` is one order.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.sales.api import (
    article_offer,
    basket_lines,
    offered_products,
    orders_of_person,
    owned_order,
    parse_items,
    shop_contact_cards,
    shop_settings,
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


def _acting_organisations(request: Request, db: Session) -> list[tuple[str, str]]:
    """The choice "Wie bestelt" of the basket (CR-26 F8): *voor mezelf* and one
    *namens …* per organisation the signed-in person acts for, as `(value, label)`. Empty — and so no choice on the
    page — without the invoices module, signed out, or with no relation."""
    from app.domains.mdm.api import module_enabled, organisations_acting_for
    from app.kernel.modules import ModuleCode

    person_id, _is_member = _buyer(request, db)
    if person_id is None or not module_enabled(ModuleCode.INVOICES):
        return []
    acting = organisations_acting_for(db, person_id)
    if not acting:
        return []
    return [("", _("voor mezelf"))] + [
        (str(o["id"]), _("namens %(name)s") % {"name": o["name"]}) for o in acting
    ]


def _member(request: Request, db: Session) -> bool:
    """Is the signed-in person a member with a valid membership today? (F3, R11)."""
    return _buyer(request, db)[1]


def _contact_prefill(request: Request, db: Session) -> tuple[str, str, str]:
    """The contact of the signed-in person, to fill the basket's contact block as
    the registration for an activity does (Koen, 15 October 2026): name, the
    primary e-mail and the primary mobile. `("", "", "")` when nobody is signed in."""
    from app.domains.mdm.api import CONTACT
    from app.ui.account_ui import signed_in_person

    _signed_in, person = signed_in_person(request, db)
    if person is None:
        return "", "", ""
    name = f"{person.first_name} {person.last_name}".strip()
    email = person.primary_contact(CONTACT.EMAIL)
    mobile = person.primary_contact(CONTACT.MOBILE)
    return name, email.value if email else "", mobile.value if mobile else ""


@router.get("/webshop", response_class=HTMLResponse)
def webshop(request: Request, db: Session = Depends(get_db)):
    member = _member(request, db)
    vm = WebshopView(
        products=offered_products(db, member=member),
        intro=shop_settings(db).intro or "",
        site=site_context(db, request),
    )
    return templates.TemplateResponse(request, "webshop.html", vm.as_context())


@router.get("/webshop/bedankt", response_class=HTMLResponse)
def bedankt(request: Request, key: str | None = None, db: Session = Depends(get_db)):
    """The shop's thank-you page (Q60, Q78): after an online payment the provider
    returns here and the page reads the ledger; after a transfer the placing
    redirects here. The link carries the order's secret key (Koen, 16 October
    2026) — the page opens only for the order whose key it is, so an id reveals
    nothing. Registered before `/webshop/{product_id}` so the fixed path wins."""
    from app.domains.sales.api import order_by_secret_key

    if not key:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    found = order_by_secret_key(db, key)
    if found is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    vm = BedanktView(
        order=found,
        order_id=found.id,
        contacts=shop_contact_cards(db),
        site=site_context(db, request),
    )
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

    def _vm(
        *, lines, total, contact_name="", contact_email="", phone="", error="", buyer=""
    ) -> BasketView:
        return BasketView(
            organisations=_acting_organisations(request, db),
            buyer=buyer,
            lines=lines,
            total=total,
            member_applied=member,
            contact_name=contact_name,
            contact_email=contact_email,
            phone=phone,
            error=error,
            site=site_context(db, request),
        )

    form = await request.form()
    items, parse_error = parse_items(form)
    person_id, member = _buyer(request, db)
    contact_name, contact_email, phone = _contact_prefill(request, db)
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
        request,
        "webshop_mandje.html",
        _vm(
            lines=lines,
            total=total,
            contact_name=str(form.get("contact_name") or contact_name),
            contact_email=str(form.get("contact_email") or contact_email),
            phone=str(form.get("phone") or phone),
            buyer=str(form.get("buyer_organization_id") or ""),
        ).as_context(),
    )


@router.post(
    "/webshop/bestellen",
    response_class=HTMLResponse,
    dependencies=[Depends(order_limiter)],
)
async def order_submit(request: Request, db: Session = Depends(get_db)) -> Response:
    """Place the order (C4.1, C5, #1987): every price recomputed, the lines reserved,
    the payment started, all in one transaction. A shown form is accepted once —
    a second post answers with the first order, never a second payment."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import Honeypot, SalesError
    from app.kernel import form_guard
    from app.kernel.refusals import FieldError
    from app.ui import refusal_response

    form = await request.form()
    proof = form_guard.Proof.from_request(request, form)

    try:
        method = PaymentMethod(str(form.get("payment_method") or "online"))
    except ValueError:
        return refusal_response(
            request,
            [FieldError("", _("Ongeldig aantal of betaalwijze."))],
            "#bestel-melding",
            send=True,
        )
    items, parse_error = parse_items(form)
    if parse_error is not None:
        return refusal_response(
            request, [FieldError("", parse_error)], "#bestel-melding", send=True
        )
    contact_name = str(form.get("contact_name") or "").strip()
    contact_email = str(form.get("contact_email") or "").strip()
    phone = str(form.get("phone") or "").strip()
    person_id, member = _buyer(request, db)
    # "Wie bestelt": empty is *voor mezelf*, a number is *namens* that organisation
    # (the service checks the relation and the module).
    buyer_text = str(form.get("buyer_organization_id") or "").strip()
    if buyer_text and not buyer_text.isdigit():
        return refusal_response(
            request,
            [FieldError("buyer_organization_id", _("Kies wie er bestelt."))],
            "#bestel-melding",
            send=True,
        )
    buyer_organization_id = int(buyer_text) if buyer_text else None

    try:
        checkout_url, order_id, secret_key = submit_order(
            db,
            proof=proof,
            values=form,
            person_id=person_id,
            member=member,
            contact_name=contact_name,
            contact_email=contact_email,
            phone=phone,
            method=method,
            items=items,
            buyer_organization_id=buyer_organization_id,
        )
    except Honeypot:
        return HTMLResponse("")
    except form_guard.NotSent as hurry:
        return refusal_response(request, [FieldError("", str(hurry))], "#bestel-melding", send=True)
    except SalesError as exc:
        return refusal_response(
            request, [FieldError(exc.field, str(exc))], "#bestel-melding", send=True
        )

    response = HTMLResponse("")
    response.headers["HX-Redirect"] = checkout_url or f"/webshop/bedankt?key={secret_key}"
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
    vm = OrderPageView(
        order=order_view(db, order),
        is_admin=False,
        contacts=shop_contact_cards(db),
        site=site_context(db, request),
    )
    return templates.TemplateResponse(request, "webshop_order.html", vm.as_context())


@router.post("/mijn/aankopen/{order_id}/annuleren")
def cancel_my_order(request: Request, order_id: int, db: Session = Depends(get_db)):
    """The buyer cancels his own order (R23, R25, F8): whoever may see the order may
    cancel it — the person and his household (Koen's "1a"). Another person's order is
    a 404, a signed-out visitor is sent to sign in and back to the order page, and a
    delivered order is refused."""
    from fastapi.responses import RedirectResponse

    from app.domains.auth.api import SESSION_COOKIE, read_session_value, require_csrf
    from app.domains.sales.api import SalesError, cancel_order
    from app.kernel.refusals import FieldError
    from app.ui import refusal_response
    from app.ui.account_ui import to_sign_in

    person_id, _is_member = _buyer(request, db)
    if person_id is None:
        return to_sign_in(request, path=f"/mijn/aankopen/{order_id}")
    if owned_order(db, order_id, person_id) is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    require_csrf(request)
    actor = read_session_value(request.cookies.get(SESSION_COOKIE)) or f"person-{person_id}"
    try:
        cancel_order(db, order_id, actor=actor)
    except SalesError as refusal:
        return refusal_response(request, [FieldError("", str(refusal))], "#order-melding")
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": "/mijn/aankopen"})
    return RedirectResponse("/mijn/aankopen", status_code=303)
