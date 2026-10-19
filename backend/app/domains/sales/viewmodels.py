"""View-models of the public Webshop (CR-21): what each page gets from its route."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class WebshopView(ViewModel):
    """`webshop.html` — the list of articles on offer."""

    products: list[dict[str, Any]]
    intro: str = ""
    site: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        context = super().as_context()
        context.pop("site", None)
        context.update(self.site)
        return context


@dataclass(frozen=True, kw_only=True)
class WebshopProductView(ViewModel):
    """`webshop_product.html` — one article on offer, with its sizes, prices,
    pictures and documents (R1, R3)."""

    name: str
    description: str
    price: Any
    from_price: bool
    sizes: list[dict[str, Any]]
    photos: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
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
    contact_name: str = ""
    contact_email: str = ""
    phone: str = ""
    error: str = ""
    #: "Wie bestelt" (CR-26 F8): `(value, label)` options — *voor mezelf* and one *namens* per organisation the
    #: signed-in person acts for; empty means no choice is shown. `buyer` is the chosen id.
    organisations: list[tuple[str, str]] = field(default_factory=list)
    buyer: str = ""
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
    contacts: list[dict[str, Any]] = field(default_factory=list)
    site: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        context = super().as_context()
        context.pop("site", None)
        context.update(self.site)
        return context


@dataclass(frozen=True, kw_only=True)
class ShopSettingsView(ViewModel):
    """`admin_shop_settings.html` — the shop's intro text and contact
    persons (R41, R42), under Verkoop."""

    intro: str = ""
    contacts: list[dict[str, Any]] = field(default_factory=list)
    contact_q: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    nav_items: list[Any] = field(default_factory=list)
    csrf_token: str = ""

    def as_context(self) -> dict[str, Any]:
        return super().as_context()


@dataclass(frozen=True, kw_only=True)
class VerkoopView(ViewModel):
    """`verkoop.html` — Verkoop's list of orders, one segment at a time (Q81)."""

    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    segment: str
    q: str = ""
    total: int = 0
    oob: bool = False
    segments: list[dict[str, Any]] = field(default_factory=list)
    nav_items: list[Any] = field(default_factory=list)

    def as_context(self) -> dict[str, Any]:
        return super().as_context()


@dataclass(frozen=True, kw_only=True)
class OrderPageView(ViewModel):
    """The order page, in the site shell and the admin shell (D6) — one view-model,
    the actions decided by `is_admin`."""

    order: dict[str, Any]
    is_admin: bool
    contacts: list[dict[str, Any]] = field(default_factory=list)
    site: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        context = super().as_context()
        context.pop("site", None)
        context.update(self.site)
        return context


@dataclass(frozen=True, kw_only=True)
class BoardOrderView(ViewModel):
    """`admin_verkoop_nieuw.html` — Verkoop's "Bestelling toevoegen" (R43, F18):
    the typed address, whether it links to a person (named since Koen's word of
    16 October 2026 — Verkoop reads a person, changes nothing), and the order's
    lines at the member price of that person, never the seller's."""

    email: str = ""
    status: str = ""
    person_name: str = ""
    #: "Voor wie" (CR-26 F8): `(value, label)` options, empty when there is no choice.
    organisations: list[tuple[str, str]] = field(default_factory=list)
    buyer: str = ""
    form_url: str = "/admin/verkoop/nieuw"
    order_id: int = 0
    lines: list[dict[str, Any]] = field(default_factory=list)
    total: Any = None
    member_applied: bool = False
    articles: list[tuple[str, str]] = field(default_factory=list)
    product_id: str = ""
    sizes: list[dict[str, Any]] = field(default_factory=list)
    site: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        context = super().as_context()
        context.pop("site", None)
        context.update(self.site)
        return context
