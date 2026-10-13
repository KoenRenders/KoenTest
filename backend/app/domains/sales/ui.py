"""The Webshop's public pages (CR-21, phase 2).

`/webshop` lists the tenant's articles in sale with a price for at least one size;
`/webshop/{product}` is one article with its sizes, price and documents. The basket
and the order come with the commits that follow.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.pricing.api import price_for
from app.domains.product.api import (
    ProductStatus,
    get_product,
    list_products,
    size_of,
    variants_of,
)
from app.i18n import _
from app.kernel.clock import belgian_today
from app.ui import site_context, templates

router = APIRouter()


def _member(request: Request, db: Session) -> bool:
    """Is the signed-in person a member with a valid membership today? (F3, R11)."""
    from app.domains.membership.api import has_valid_membership
    from app.ui.account_ui import signed_in_person

    signed_in, person = signed_in_person(request, db)
    return signed_in and has_valid_membership(person)


def _shop_products(db: Session, member: bool) -> list[dict[str, Any]]:
    """The articles in sale with a price today for at least one size (R40)."""
    today = belgian_today()
    products: list[dict[str, Any]] = []
    for product in list_products(db, active_only=True):
        variants = variants_of(db, product.id)
        priced = [(size_of(v), price_for(db, v.id, today, member)) for v in variants]
        valid = [(name, price) for name, price in priced if price is not None]
        if not valid:
            continue
        products.append(
            {
                "id": product.id,
                "name": product.name,
                "description": product.description or "",
                "sizes": [name for name, _ in valid],
                "price": min(price for _, price in valid),
            }
        )
    return products


@router.get("/webshop", response_class=HTMLResponse)
def webshop(request: Request, db: Session = Depends(get_db)):
    member = _member(request, db)
    ctx = {
        **site_context(db, request),
        "products": _shop_products(db, member),
        "member": member,
    }
    return templates.TemplateResponse(request, "webshop.html", ctx)


@router.get("/webshop/{product_id}", response_class=HTMLResponse)
def webshop_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    product = get_product(db, product_id)
    if product is None or product.status is not ProductStatus.ON_SALE:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    member = _member(request, db)
    today = belgian_today()
    sizes = [
        {
            "id": variant.id,
            "name": size_of(variant),
            "price": price_for(db, variant.id, today, member),
        }
        for variant in variants_of(db, product.id)
        if price_for(db, variant.id, today, member) is not None
    ]
    ctx = {
        **site_context(db, request),
        "product": product,
        "sizes": sizes,
        "member": member,
    }
    return templates.TemplateResponse(request, "webshop_product.html", ctx)
