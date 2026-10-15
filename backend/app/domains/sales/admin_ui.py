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
    cancel_order,
    deliver_line,
    get_order,
    list_orders,
    order_view,
)
from app.i18n import _
from app.kernel.refusals import FieldError
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
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SALES_VIEW)),
):
    """Verkoop's list of orders, one segment at a time (Q81)."""
    from app.domains.sales.viewmodels import VerkoopView

    segment = _segment(request)
    orders = list_orders(db)
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
    vm = VerkoopView(columns=columns, rows=rows, segment=segment, nav_items=admin_nav(NAV, request))
    return templates.TemplateResponse(request, "verkoop.html", vm.as_context())


@router.get("/admin/verkoop/{order_id}", response_class=HTMLResponse)
def verkoop_order(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SALES_VIEW)),
):
    """The order page in the admin shell (D6): the same view the buyer reads."""
    from app.domains.sales.viewmodels import OrderPageView

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
