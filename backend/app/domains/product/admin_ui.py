"""Productbeheer (CR-21): the product list and the create form, behind the
product rights.

Master data, kept apart from any activity (R2). A GET asks `product.view`, a
change asks `product.masterdata` (CR-24 D1). The article record — the sizes, the
life cycle, the pictures and documents, the delete — comes with the next commit.

The path is Dutch because a board member reads it in the address bar; the
module, the routes and the parameters are English like all new code.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import SESSION_COOKIE, Right, csrf_token_for, require_csrf, require_right
from app.domains.product.api import ProductError, create_product, list_products, variants_of
from app.domains.product.viewmodels import ProductListView, ProductNewView
from app.ui import admin_nav, is_fragment_request, templates

router = APIRouter()

NAV = "/admin/producten"


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


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
        create_product(db, name)
    except ProductError as refusal:
        return templates.TemplateResponse(
            request,
            "admin_product_nieuw.html",
            _new_view(request, db, error=str(refusal)).as_context(),
            status_code=422,
        )
    return RedirectResponse("/admin/producten", status_code=303)
