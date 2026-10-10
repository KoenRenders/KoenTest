"""Prijsbeheer (CR-21): the prices of an article, behind the pricing rights.

A GET asks `price.view`, a change asks `price.manage` (CR-24 D1). The list
`/admin/prijzen` is the articles; `/admin/prijzen/{product_id}` is one article's
prices by start date, with the new-price form.

The path is Dutch because a board member reads it in the address bar; the
module, the routes and the parameters are English like all new code.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import SESSION_COOKIE, Right, csrf_token_for, require_csrf, require_right
from app.domains.pricing.api import PriceError, PriceType, add_prices, prices_of
from app.domains.pricing.viewmodels import PriceListView, PriceView
from app.domains.product.api import get_product, get_variant, list_products, size_of, variants_of
from app.i18n import _
from app.kernel.clock import belgian_today
from app.ui import admin_nav, templates

router = APIRouter()

NAV = "/admin/prijzen"


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


def _redirect(request: Request, url: str) -> Response:
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


def _variant_size(db: Session, variant_id: int | None) -> str:
    if variant_id is None:
        return _("alle maten")
    variant = get_variant(db, variant_id)
    return size_of(variant) if variant else ""


def _price_state(valid_from: date, today: date, current: date | None) -> str:
    from app.i18n import long_date

    if valid_from > today:
        return _("Vanaf %(date)s") % {"date": long_date(valid_from)}
    if valid_from == current:
        return _("Vandaag")
    return _("Voorbij")


def _price_view(request: Request, db: Session, product, error: Optional[str] = None) -> PriceView:
    today = belgian_today()
    prices = prices_of(db, product.id)
    current = max((p.valid_from for p in prices if p.valid_from <= today), default=None)
    grouped: dict[tuple[date, int | None], dict] = {}
    for price in prices:
        key = (price.valid_from, price.variant_id)
        row = grouped.setdefault(
            key, {"valid_from": price.valid_from, "regular": None, "member": None}
        )
        if price.price_type is PriceType.REGULAR:
            row["regular"] = price.amount
        else:
            row["member"] = price.amount
    rows = []
    for (valid_from, variant_id), amounts in grouped.items():
        rows.append(
            {
                "valid_from": valid_from,
                "size": _variant_size(db, variant_id),
                "regular": amounts["regular"],
                "member": amounts["member"],
                "state": _price_state(valid_from, today, current),
            }
        )
    return PriceView(
        product=product,
        rows=rows,
        options=[("", _("Alle maten"))]
        + [(str(variant.id), size_of(variant)) for variant in variants_of(db, product.id)],
        csrf_token=_csrf(request),
        error=error,
        nav_items=admin_nav(NAV, request),
    )


@router.get("/admin/prijzen", response_class=HTMLResponse)
def price_list(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.PRICE_VIEW)),
):
    view = PriceListView(products=list_products(db), nav_items=admin_nav(NAV, request))
    return templates.TemplateResponse(request, "admin_prijzen.html", view.as_context())


@router.get("/admin/prijzen/{product_id}", response_class=HTMLResponse)
def price_record(
    request: Request,
    product_id: int,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.PRICE_VIEW)),
):
    product = get_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    return templates.TemplateResponse(
        request, "admin_prijs.html", _price_view(request, db, product).as_context()
    )


@router.post("/admin/prijzen/{product_id}")
def price_create(
    request: Request,
    product_id: int,
    valid_from: str = Form(""),
    variant_id: str = Form(""),
    amount: str = Form(""),
    member_amount: str = Form(""),
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.PRICE_MANAGE)),
    _csrf: None = Depends(require_csrf),
):
    product = get_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    try:
        day = date.fromisoformat(valid_from) if valid_from else None
        variant = int(variant_id) if variant_id else None
        regular = _decimal(amount)
        member = _decimal(member_amount) if member_amount else None
        add_prices(
            db,
            product_id=product_id,
            variant_id=variant,
            valid_from=day,
            amount=regular,
            member_amount=member,
        )
    except (PriceError, ValueError, InvalidOperation) as refusal:
        return templates.TemplateResponse(
            request,
            "admin_prijs.html",
            _price_view(request, db, product, error=str(refusal)).as_context(),
            status_code=422,
        )
    return _redirect(request, f"/admin/prijzen/{product_id}")


def _decimal(value: str) -> Optional[Decimal]:
    value = (value or "").strip().replace(",", ".")
    if not value:
        return None
    return Decimal(value)
