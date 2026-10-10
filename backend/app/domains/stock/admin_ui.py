"""Voorraadbeheer (CR-21): the stock per size, the receipt and the correction.

A GET asks `stock.view`, a change asks `stock.manage` (CR-24 D1). On hand is the
sum of the movements, available is on hand minus the open reservations (D2);
"Beschikbaar" is shown never below zero. The field Locatie is hidden while the
tenant has one location (Q83) — the writers use the default location.

The path is Dutch because a board member reads it in the address bar; the
module, the routes and the parameters are English like all new code.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import SESSION_COOKIE, Right, csrf_token_for, require_csrf, require_right
from app.domains.product.api import list_products, size_of, variants_of
from app.domains.stock.api import (
    StockError,
    available,
    correct,
    on_hand,
    receive,
    reserved,
)
from app.domains.stock.viewmodels import StockCorrectionView, StockReceiptView, StockView
from app.i18n import _
from app.ui import admin_nav, templates

router = APIRouter()

NAV = "/admin/voorraad"

_DIRECTIONS = [("up", "Erbij"), ("down", "Eraf")]


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


def _redirect(request: Request, url: str) -> Response:
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


def _options(db: Session) -> list[tuple[str, str]]:
    """Every size of every article, as (variant id, "product · size") for the select."""
    result: list[tuple[str, str]] = []
    for product in list_products(db):
        for variant in variants_of(db, product.id):
            result.append((str(variant.id), f"{product.name} · {size_of(variant)}"))
    return result


def _rows(db: Session) -> list[dict]:
    rows = []
    for product in list_products(db):
        for variant in variants_of(db, product.id):
            rows.append(
                {
                    "product": product.name,
                    "size": size_of(variant),
                    "on_hand": on_hand(db, variant.id),
                    "reserved": reserved(db, variant.id),
                    "available": max(available(db, variant.id), 0),
                }
            )
    return rows


def _receipt_view(request: Request, db: Session, error: str | None = None) -> StockReceiptView:
    return StockReceiptView(
        options=_options(db),
        csrf_token=_csrf(request),
        error=error,
        nav_items=admin_nav(NAV, request),
    )


def _correction_view(
    request: Request, db: Session, error: str | None = None
) -> StockCorrectionView:
    return StockCorrectionView(
        options=_options(db),
        directions=[(value, _(label)) for value, label in _DIRECTIONS],
        csrf_token=_csrf(request),
        error=error,
        nav_items=admin_nav(NAV, request),
    )


@router.get("/admin/voorraad", response_class=HTMLResponse)
def stock_list(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.STOCK_VIEW)),
):
    view = StockView(rows=_rows(db), nav_items=admin_nav(NAV, request))
    return templates.TemplateResponse(request, "admin_voorraad.html", view.as_context())


@router.get("/admin/voorraad/ontvangst", response_class=HTMLResponse)
def receipt_form(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.STOCK_VIEW)),
):
    return templates.TemplateResponse(
        request, "admin_ontvangst.html", _receipt_view(request, db).as_context()
    )


@router.post("/admin/voorraad/ontvangst")
def receipt_create(
    request: Request,
    variant_id: str = Form(""),
    quantity: str = Form(""),
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.STOCK_MANAGE)),
    _csrf: None = Depends(require_csrf),
):
    try:
        receive(db, int(variant_id), int(quantity), actor=_email)
    except (StockError, ValueError) as refusal:
        return templates.TemplateResponse(
            request,
            "admin_ontvangst.html",
            _receipt_view(request, db, error=str(refusal)).as_context(),
            status_code=422,
        )
    return _redirect(request, "/admin/voorraad")


@router.get("/admin/voorraad/correctie", response_class=HTMLResponse)
def correction_form(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.STOCK_VIEW)),
):
    return templates.TemplateResponse(
        request, "admin_correctie.html", _correction_view(request, db).as_context()
    )


@router.post("/admin/voorraad/correctie")
def correction_create(
    request: Request,
    variant_id: str = Form(""),
    quantity: str = Form(""),
    direction: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.STOCK_MANAGE)),
    _csrf: None = Depends(require_csrf),
):
    try:
        amount = int(quantity)
        if direction == "down":
            amount = -amount
        correct(db, int(variant_id), amount, note=note, actor=_email)
    except (StockError, ValueError) as refusal:
        return templates.TemplateResponse(
            request,
            "admin_correctie.html",
            _correction_view(request, db, error=str(refusal)).as_context(),
            status_code=422,
        )
    return _redirect(request, "/admin/voorraad")
