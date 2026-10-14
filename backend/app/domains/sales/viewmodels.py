"""View-models of the public Webshop (CR-21): what each page gets from its route."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class WebshopView(ViewModel):
    """`webshop.html` — the list of articles on offer."""

    products: list[dict[str, Any]]
    site: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        context = super().as_context()
        context.pop("site", None)
        context.update(self.site)
        return context


@dataclass(frozen=True, kw_only=True)
class WebshopProductView(ViewModel):
    """`webshop_product.html` — one article on offer, with its sizes and prices."""

    name: str
    description: str
    price: Any
    from_price: bool
    sizes: list[dict[str, Any]]
    site: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        context = super().as_context()
        context.pop("site", None)
        context.update(self.site)
        return context


@dataclass(frozen=True, kw_only=True)
class BasketView(ViewModel):
    """`webshop_mandje.html` — the basket, which IS the order page (as a
    registration is one page)."""

    lines: list[dict[str, Any]]
    total: Any
    member_applied: bool
    error: str = ""
    site: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        context = super().as_context()
        context.pop("site", None)
        context.update(self.site)
        return context


@dataclass(frozen=True, kw_only=True)
class MyOrdersView(ViewModel):
    """`mijn_aankopen.html` — the buyer's orders, newest first."""

    orders: list[Any]
    site: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        context = super().as_context()
        context.pop("site", None)
        context.update(self.site)
        return context


@dataclass(frozen=True, kw_only=True)
class WebshopOrderView(ViewModel):
    """`webshop_order.html` — one order, in the site shell."""

    order: Any
    order_id: int
    site: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        context = super().as_context()
        context.pop("site", None)
        context.update(self.site)
        return context


@dataclass(frozen=True, kw_only=True)
class BedanktView(ViewModel):
    """`webshop_bedankt.html` — the thank-you page."""

    order: Any
    order_id: int
    site: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        context = super().as_context()
        context.pop("site", None)
        context.update(self.site)
        return context
