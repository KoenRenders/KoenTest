"""Productbeheer (CR-21): the product list, the create form and the article
record, behind the product rights.

Master data, kept apart from any activity (R2). A GET asks `product.view`, a
change asks `product.masterdata` (CR-24 D1). The life cycle walks through the
record's head; adding and removing a size on the screen, and the pictures and
documents, follow in their own commit.

The path is Dutch because a board member reads it in the address bar; the
module, the routes and the parameters are English like all new code.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import SESSION_COOKIE, Right, csrf_token_for, require_csrf, require_right
from app.domains.product.api import (
    ProductError,
    ProductStatus,
    create_product,
    delete_product,
    get_product,
    list_products,
    set_pre_order,
    set_status,
    size_of,
    update_product,
    variants_of,
)
from app.domains.product.viewmodels import ProductListView, ProductNewView, ProductView
from app.i18n import _
from app.ui import admin_nav, is_fragment_request, templates

router = APIRouter()

NAV = "/admin/producten"


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


def _redirect(request: Request, url: str) -> Response:
    """The shell carries hx-boost: a 303 lets htmx swap the answer, `HX-Redirect`
    lets the browser really navigate so a refresh stays on the right page."""
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


def _list_view(request: Request, db: Session, error: Optional[str] = None) -> ProductListView:
    products = list_products(db)
    return ProductListView(
        products=products,
        sizes={product.id: len(variants_of(db, product.id)) for product in products},
        error=error,
        nav_items=admin_nav(NAV, request),
    )


def _new_view(request: Request, db: Session, error: Optional[str] = None) -> ProductNewView:
    return ProductNewView(
        csrf_token=_csrf(request),
        error=error,
        nav_items=admin_nav(NAV, request),
    )


@router.get("/admin/producten", response_class=HTMLResponse)
def product_list(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.PRODUCT_VIEW)),
):
    view = _list_view(request, db)
    template = "_producten_lijst.html" if is_fragment_request(request) else "admin_producten.html"
    return templates.TemplateResponse(request, template, view.as_context())


@router.get("/admin/producten/nieuw", response_class=HTMLResponse)
def product_new(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.PRODUCT_VIEW)),
):
    return templates.TemplateResponse(
        request, "admin_product_nieuw.html", _new_view(request, db).as_context()
    )


@router.post("/admin/producten")
def product_create(
    request: Request,
    name: str = Form(""),
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.PRODUCT_MASTERDATA)),
    _csrf: None = Depends(require_csrf),
):
    try:
        product = create_product(db, name)
    except ProductError as refusal:
        return templates.TemplateResponse(
            request,
            "admin_product_nieuw.html",
            _new_view(request, db, error=str(refusal)).as_context(),
            status_code=422,
        )
    return RedirectResponse(f"/admin/producten/{product.id}", status_code=303)


def _record_view(
    request: Request, db: Session, product, editing: bool, error: Optional[str] = None
) -> ProductView:
    base = f"/admin/producten/{product.id}"
    actions: list[dict] = []
    if product.status is not ProductStatus.ON_SALE:
        actions.append(
            {
                "kind": "record",
                "verb": "state",
                "label": _("In verkoop zetten"),
                "attrs": f'hx-post="{base}/status" hx-vals=\'{{"status": "ON_SALE"}}\'',
            }
        )
    if product.status is not ProductStatus.DISCONTINUED:
        actions.append(
            {
                "kind": "record",
                "verb": "state",
                "label": _("Afvoeren"),
                "attrs": f'hx-post="{base}/status" hx-vals=\'{{"status": "DISCONTINUED"}}\'',
                "confirm": _("Het artikel verdwijnt dan uit de webshop."),
                "confirm_ok": _("Afvoeren"),
            }
        )
    actions.append(
        {
            "kind": "delete",
            "label": _("Verwijderen"),
            "attrs": f'hx-post="{base}/verwijderen"',
            "confirm": _("Het artikel en zijn prijzen worden verwijderd."),
            "confirm_ok": _("Definitief verwijderen"),
        }
    )
    return ProductView(
        product=product,
        sizes=[(variant.id, size_of(variant)) for variant in variants_of(db, product.id)],
        editing=editing,
        csrf_token=_csrf(request),
        primary={"label": _("Bewerken"), "href": f"{base}?bewerken=1"} if not editing else None,
        actions=actions if not editing else [],
        error=error,
        nav_items=admin_nav(NAV, request),
    )


@router.get("/admin/producten/{product_id}", response_class=HTMLResponse)
def product_record(
    request: Request,
    product_id: int,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.PRODUCT_VIEW)),
    bewerken: str = "",
):
    product = get_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    view = _record_view(request, db, product, editing=bool(bewerken))
    return templates.TemplateResponse(request, "admin_product.html", view.as_context())


@router.post("/admin/producten/{product_id}")
def product_update(
    request: Request,
    product_id: int,
    name: str = Form(""),
    description: str = Form(""),
    pre_order: str = Form(""),
    pre_order_until: str = Form(""),
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.PRODUCT_MASTERDATA)),
    _csrf: None = Depends(require_csrf),
):
    product = get_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    try:
        update_product(db, product_id, name=name, description=description)
        set_pre_order(
            db,
            product_id,
            pre_order=pre_order in ("on", "true", "1"),
            pre_order_until=_parse_date(pre_order_until),
        )
    except ProductError as refusal:
        return templates.TemplateResponse(
            request,
            "admin_product.html",
            _record_view(request, db, product, editing=True, error=str(refusal)).as_context(),
            status_code=422,
        )
    return _redirect(request, f"/admin/producten/{product_id}")


@router.post("/admin/producten/{product_id}/status")
def product_status(
    request: Request,
    product_id: int,
    status: str = Form(""),
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.PRODUCT_MASTERDATA)),
    _csrf: None = Depends(require_csrf),
):
    product = get_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    try:
        set_status(db, product_id, ProductStatus(status))
    except (ProductError, ValueError) as refusal:
        return templates.TemplateResponse(
            request,
            "admin_product.html",
            _record_view(request, db, product, editing=False, error=str(refusal)).as_context(),
            status_code=422,
        )
    return _redirect(request, f"/admin/producten/{product_id}")


@router.post("/admin/producten/{product_id}/verwijderen")
def product_delete(
    request: Request,
    product_id: int,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.PRODUCT_MASTERDATA)),
    _csrf: None = Depends(require_csrf),
):
    product = get_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    try:
        delete_product(db, product_id)
    except ProductError as refusal:
        return templates.TemplateResponse(
            request,
            "admin_product.html",
            _record_view(request, db, product, editing=False, error=str(refusal)).as_context(),
            status_code=422,
        )
    return _redirect(request, "/admin/producten")


def _parse_date(value: str) -> Optional[date]:
    from datetime import date as Date

    value = (value or "").strip()
    if not value:
        return None
    try:
        return Date.fromisoformat(value)
    except ValueError:
        return None
