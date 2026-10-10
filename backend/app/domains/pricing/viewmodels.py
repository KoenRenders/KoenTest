"""View-models of the pricing screens (CR-21)."""

from dataclasses import dataclass, field
from typing import Any, Optional

from app.domains.product.api import Product
from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class PriceListView(ViewModel):
    """`admin_prijzen.html` — the articles, to pick one to set its prices."""

    products: list[Product]
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class PriceView(ViewModel):
    """`admin_prijs.html` — one article's prices and the new-price form."""

    product: Product
    #: One row per (start date, size): the regular and member amount side by side
    #: and the state ("Vandaag", "Vanaf …", "Voorbij").
    rows: list[dict[str, Any]]
    #: The "Maten" select of the new-price form, as (value, label) pairs.
    options: list[tuple[str, str]]
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)
