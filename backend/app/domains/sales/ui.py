"""The Webshop's public pages (CR-21, phase 2).

`/webshop` lists the tenant's articles on offer; `/webshop/{product_id}` is one
article with its sizes and prices. What is on offer — and at which price for
whom — lives in the service (`sales.service`), so the list and the article page
ask the same rule, and the basket and the order of the commits that follow will
too.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.sales.api import article_offer, offered_products
from app.domains.sales.viewmodels import WebshopProductView, WebshopView
from app.i18n import _
from app.ui import site_context, templates

router = APIRouter()


def _member(request: Request, db: Session) -> bool:
    """Is the signed-in person a member with a valid membership today? (F3, R11)."""
    from app.domains.membership.api import has_valid_membership
    from app.ui.account_ui import signed_in_person

    signed_in, person = signed_in_person(request, db)
    return signed_in and has_valid_membership(person)


@router.get("/webshop", response_class=HTMLResponse)
def webshop(request: Request, db: Session = Depends(get_db)):
    member = _member(request, db)
    vm = WebshopView(
        products=offered_products(db, member=member),
        site=site_context(db, request),
    )
    return templates.TemplateResponse(request, "webshop.html", vm.as_context())


@router.get("/webshop/{product_id}", response_class=HTMLResponse)
def webshop_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    member = _member(request, db)
    offer = article_offer(db, product_id, member=member)
    if offer is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    vm = WebshopProductView(
        name=offer["name"],
        description=offer["description"],
        sizes=offer["sizes"],
        site=site_context(db, request),
    )
    return templates.TemplateResponse(request, "webshop_product.html", vm.as_context())
