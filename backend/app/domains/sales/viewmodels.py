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
    sizes: list[dict[str, Any]]
    site: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        context = super().as_context()
        context.pop("site", None)
        context.update(self.site)
        return context
