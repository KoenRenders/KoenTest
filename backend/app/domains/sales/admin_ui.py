"""Verkoop (CR-21): the list of orders, the order page and the actions — deliver
a line and cancel — behind the sales rights (CR-24 D1).

A GET asks `sales.view`, a change asks `sales.manage`. The path is Dutch because a
board member reads it in the address bar; the module, the routes and the
parameters are English like all new code.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import SESSION_COOKIE, Right, csrf_token_for, require_csrf, require_right
from app.domains.sales.api import (
    SalesError,
    article_offer,
    basket_lines,
    board_order_person,
    cancel_order,
    deliver_line,
    get_order,
    list_orders,
    offered_products,
    order_view,
    parse_items,
)
from app.domains.sales.viewmodels import (
    BoardOrderView,
    OrderPageView,
    ShopSettingsView,
    VerkoopView,
)
from app.i18n import _
from app.kernel.refusals import FieldError
from app.limiter import board_order_limiter
from app.ui import admin_nav, refusal_response, templates

router = APIRouter()

NAV = "/admin/verkoop"

#: The three segments (Q81), one state the board acts on: unpaid, to deliver
#: (nothing or part delivered), and everything.
SEGMENTS = [
    {"value": "te-betalen", "label": _("Te betalen")},
    {"value": "te-leveren", "label": _("Te leveren")},
    {"value": "alles", "label": _("Alles")},
]


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


def _redirect(request: Request, url: str) -> Response:
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


def _segment(request: Request) -> str:
    chosen = request.query_params.get("segment", "alles")
    return chosen if chosen in {s["value"] for s in SEGMENTS} else "alles"


@router.get("/admin/verkoop", response_class=HTMLResponse)
def verkoop(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SALES_VIEW)),
):
    """Verkoop's list of orders, one segment at a time (Q81)."""
    return templates.TemplateResponse(
        request,
        "verkoop.html",
        _verkoop_view(db, _segment(request), q, nav_items=admin_nav(NAV, request)).as_context(),
    )


@router.get("/admin/verkoop/lijst", response_class=HTMLResponse)
def verkoop_fragment(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SALES_VIEW)),
):
    """The list alone: the segment filter swaps this fragment, so the segment
    control is not replaced under the fingers."""
    return templates.TemplateResponse(
        request,
        "_verkoop_lijst.html",
        _verkoop_view(db, _segment(request), q, oob=True).as_context(),
    )


def _verkoop_view(
    db: Session, segment: str, q: str = "", *, oob: bool = False, nav_items=None
) -> VerkoopView:
    """The list's view-model, shared by the page and the fragment (Q81)."""
    orders = list_orders(db)
    if q.strip():
        needle = q.strip().casefold()
        orders = [
            o
            for o in orders
            if needle in str(o["id"]) or needle in (o["contact_name"] or "").casefold()
        ]
    if segment == "te-betalen":
        orders = [o for o in orders if o["payment"] == "open"]
    elif segment == "te-leveren":
        orders = [o for o in orders if o["payment"] != "open" and o["delivery"] != _("Afgeleverd")]

    def _payment_badge(state: str) -> tuple[str, str]:
        if state == "open":
            return (_("Te betalen"), "orange")
        if state == "settled":
            return (_("Betaald"), "green")
        return (_("Geen betaling"), "gray")

    columns = [
        {"key": "bestelling", "label": _("Bestelling"), "cell": "name"},
        {"key": "status", "label": _("Status"), "cell": "status"},
    ]
    rows = [
        {
            "id": o["id"],
            "name": _("Bestelling") + " " + str(o["id"]),
            "contact": o["contact_name"],
            "badge": _payment_badge(o["payment"]),
            "delivery": o["delivery"],
        }
        for o in orders
    ]
    return VerkoopView(
        columns=columns,
        rows=rows,
        segment=segment,
        q=q,
        total=len(rows),
        oob=oob,
        segments=SEGMENTS,
        nav_items=nav_items or [],
    )


@router.get("/admin/verkoop/nieuw", response_class=HTMLResponse)
def add_order(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SALES_VIEW)),
):
    """Verkoop's "Bestelling toevoegen" (R43, F18): the order page in the admin
    shell, the person of the typed address."""
    return templates.TemplateResponse(
        request,
        "admin_verkoop_nieuw.html",
        _board_order_view(db, request, email="", items=[]).as_context(),
    )


@router.post(
    "/admin/verkoop/nieuw/koppeling",
    response_class=HTMLResponse,
    dependencies=[Depends(board_order_limiter)],
)
async def add_order_link(
    request: Request,
    db: Session = Depends(get_db),
    _u: str = Depends(require_right(Right.SALES_MANAGE)),
    _csrf: None = Depends(require_csrf),
):
    """Re-render the form as the e-mail changes (R43): the line list re-prices at
    the member price of the typed person, and the link line says whether the
    address is known — never a name (CR-24 AC6)."""
    form = await request.form()
    email = str(form.get("email") or "").strip()
    items, _parse_error = parse_items(form)
    vm = _board_order_view(db, request, email=email, items=items)
    return templates.TemplateResponse(request, "_verkoop_nieuw_form.html", vm.as_context())


@router.post(
    "/admin/verkoop/nieuw/maten",
    response_class=HTMLResponse,
    dependencies=[Depends(board_order_limiter)],
)
async def add_order_sizes(
    request: Request,
    db: Session = Depends(get_db),
    _u: str = Depends(require_right(Right.SALES_MANAGE)),
    _csrf: None = Depends(require_csrf),
):
    """The size tiles and the "Artikel toevoegen" row for one article (Q90)."""
    form = await request.form()
    product_id = str(form.get("product_id") or "")
    email = str(form.get("email") or "").strip()
    _status, _person, member = board_order_person(db, email)
    sizes: list[dict] = []
    if product_id:
        try:
            offer = article_offer(db, int(product_id), member=member)
        except (TypeError, ValueError):
            offer = None
        sizes = offer["sizes"] if offer else []
    return templates.TemplateResponse(
        request,
        "_verkoop_maten.html",
        BoardOrderView(product_id=product_id, sizes=sizes).as_context(),
    )


@router.post("/admin/verkoop/nieuw", response_class=HTMLResponse)
async def add_order_submit(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SALES_MANAGE)),
    _csrf: None = Depends(require_csrf),
):
    """Add a line, remove one, or save the order (R43, F18)."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import submit_order
    from app.kernel import form_guard
    from app.kernel.refusals import FieldError

    form = await request.form()
    action = str(form.get("action") or "save")
    email = str(form.get("email") or "").strip()
    items, parse_error = parse_items(form)

    if form.get("remove_variant_id"):
        action = "remove"

    if action == "add":
        new_variant = str(form.get("new_variant_id") or "").strip()
        new_quantity = str(form.get("new_quantity") or "").strip()
        if parse_error is None and new_variant:
            try:
                variant_id, quantity = int(new_variant), int(new_quantity)
            except ValueError:
                variant_id, quantity = 0, 0
            if variant_id > 0 and quantity > 0:
                merged = dict(items)
                merged[variant_id] = merged.get(variant_id, 0) + quantity
                items = sorted(merged.items())
        vm = _board_order_view(db, request, email=email, items=items, product_id="")
        return templates.TemplateResponse(request, "_verkoop_nieuw_form.html", vm.as_context())

    if action == "remove":
        remove_variant = str(form.get("remove_variant_id") or "").strip()
        if parse_error is None and remove_variant:
            try:
                remove_id = int(remove_variant)
            except ValueError:
                remove_id = 0
            items = [(v, q) for v, q in items if v != remove_id]
        vm = _board_order_view(db, request, email=email, items=items, product_id="")
        return templates.TemplateResponse(request, "_verkoop_nieuw_form.html", vm.as_context())

    if parse_error is not None:
        return refusal_response(
            request, [FieldError("", parse_error)], "#bestel-melding", send=True
        )
    status, person, member = board_order_person(db, email)
    if status == "multiple":
        return refusal_response(
            request,
            [
                FieldError(
                    "email", _("Dit adres hoort bij meerdere personen; vraag een ander adres.")
                )
            ],
            "#bestel-melding",
            send=True,
        )
    if person is None:
        return refusal_response(
            request,
            [FieldError("email", _("Dit e-mailadres is bij niemand gekend."))],
            "#bestel-melding",
            send=True,
        )
    if not items:
        return refusal_response(
            request,
            [FieldError("", _("Voeg minstens één artikel toe."))],
            "#bestel-melding",
            send=True,
        )
    try:
        method = PaymentMethod(str(form.get("payment_method") or "transfer"))
    except ValueError:
        method = PaymentMethod.ONLINE
    if method is PaymentMethod.ONLINE:
        return refusal_response(
            request,
            [
                FieldError(
                    "", _("Een bestelling die het bestuur invoert, betaalt per overschrijving.")
                )
            ],
            "#bestel-melding",
            send=True,
        )
    try:
        _checkout, order_id = submit_order(
            db,
            proof=form_guard.TRUSTED,
            values=form,
            person_id=person.id,
            member=member,
            contact_name="",
            contact_email="",
            phone="",
            method=method,
            items=items,
        )
    except SalesError as refusal:
        return refusal_response(
            request, [FieldError("", str(refusal))], "#bestel-melding", send=True
        )
    except form_guard.NotSent as hurry:
        return refusal_response(request, [FieldError("", str(hurry))], "#bestel-melding", send=True)
    return _redirect(request, f"/admin/verkoop/{order_id}")


def _board_order_view(
    db: Session,
    request: Request,
    *,
    email: str,
    items: list[tuple[int, int]],
    product_id: str = "",
) -> BoardOrderView:
    """The "Bestelling toevoegen" view-model (R43): the lines at the member price
    of the typed person, the articles for the picker, and the chosen article's
    sizes."""
    from decimal import Decimal

    status, _person, member = board_order_person(db, email)
    lines = basket_lines(db, member=member, items=items)
    total = sum(
        (line["price"] * line["quantity"] for line in lines if line["available"]),
        Decimal("0"),
    )
    articles = [(str(p["id"]), p["name"]) for p in offered_products(db, member=member)]
    return BoardOrderView(
        email=email,
        status=status,
        lines=lines,
        total=total,
        member_applied=member and any(line["available"] for line in lines),
        articles=articles,
        product_id=product_id,
        site={"nav_items": admin_nav(NAV, request), "csrf_token": _csrf(request)},
    )


@router.get("/admin/verkoop/instellingen", response_class=HTMLResponse)
def shop_settings_page(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SALES_MANAGE)),
):
    """The shop's own settings (R41, R42): the intro text above the Webshop and
    the contact persons, under Verkoop."""
    from app.domains.sales.api import shop_contact_cards, shop_settings

    vm = ShopSettingsView(
        intro=shop_settings(db).intro or "",
        contacts=shop_contact_cards(db),
        nav_items=admin_nav(NAV, request),
        csrf_token=_csrf(request),
    )
    return templates.TemplateResponse(request, "admin_shop_settings.html", vm.as_context())


@router.get("/admin/verkoop/instellingen/personen", response_class=HTMLResponse)
def shop_contact_candidates(
    request: Request,
    contact_q: str = "",
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SALES_MANAGE)),
):
    """The candidates of the contact search — every person, not only members (R41,
    Q71); whoever is already a contact is left out."""
    from app.domains.mdm.api import search_persons
    from app.domains.sales.api import shop_contacts

    taken = {c.person_id for c in shop_contacts(db)}
    candidates = [
        {
            "id": match.person.id,
            "name": f"{match.first_name} {match.last_name}".strip(),
            "email": match.email or "",
        }
        for match in search_persons(db, contact_q, exclude_ids=taken)
    ]
    vm = ShopSettingsView(contact_q=contact_q, candidates=candidates)
    return templates.TemplateResponse(request, "_shop_settings_candidates.html", vm.as_context())


@router.post("/admin/verkoop/instellingen", response_class=HTMLResponse)
async def shop_settings_save(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SALES_MANAGE)),
    _csrf: None = Depends(require_csrf),
):
    """Save the intro, or add or remove a contact person (R41, R42)."""
    from app.domains.sales.api import add_shop_contact, remove_shop_contact, save_shop_intro

    form = await request.form()
    action = str(form.get("action") or "save")
    try:
        if action == "remove_contact":
            contact_id = int(str(form.get("contact_id") or 0))
            remove_shop_contact(db, contact_id)
        elif action == "add_contact":
            person_id = int(str(form.get("person_id") or 0))
            if person_id:
                add_shop_contact(db, person_id)
        else:
            save_shop_intro(db, str(form.get("intro") or ""))
    except ValueError:
        return refusal_response(
            request, [FieldError("", _("Ongeldige keuze."))], "#instellingen-melding", send=True
        )
    except SalesError as refusal:
        return refusal_response(
            request, [FieldError("", str(refusal))], "#instellingen-melding", send=True
        )
    return _redirect(request, "/admin/verkoop/instellingen")


@router.get("/admin/verkoop/{order_id}", response_class=HTMLResponse)
def verkoop_order(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SALES_VIEW)),
):
    """The order page in the admin shell (D6): the same view the buyer reads."""
    order = get_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    vm = OrderPageView(
        order=order_view(db, order),
        is_admin=True,
        site={"nav_items": admin_nav(NAV, request), "csrf_token": _csrf(request)},
    )
    return templates.TemplateResponse(request, "admin_verkoop_order.html", vm.as_context())


@router.post("/admin/verkoop/{order_id}/lijn/{line_id}/leveren")
def lever_lijn(
    request: Request,
    order_id: int,
    line_id: int,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SALES_MANAGE)),
    _csrf: None = Depends(require_csrf),
):
    """Deliver one line (F6, R21)."""
    try:
        deliver_line(db, order_id, line_id, actor=_email)
    except SalesError as refusal:
        return refusal_response(request, [FieldError("", str(refusal))], "#order-melding")
    return _redirect(request, f"/admin/verkoop/{order_id}")


@router.post("/admin/verkoop/{order_id}/annuleren")
def annuleer(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SALES_MANAGE)),
    _csrf: None = Depends(require_csrf),
):
    """Cancel the whole order (F8)."""
    try:
        cancel_order(db, order_id, actor=_email)
    except SalesError as refusal:
        return refusal_response(request, [FieldError("", str(refusal))], "#order-melding")
    return _redirect(request, "/admin/verkoop")
