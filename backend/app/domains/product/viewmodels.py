"""View-models of the product screens (CR-21)."""

from dataclasses import dataclass, field
from typing import Any, Optional

from app.domains.product.models import Product, ProductVariant
from app.ui.viewmodel import ViewModel


def size_of(variant: ProductVariant) -> str:
    """The size of a variant, from its one `Maat` property (B3a)."""
    for prop in variant.properties or []:
        if prop.get("name") == "Maat":
            return str(prop.get("value", ""))
    return ""


@dataclass(frozen=True, kw_only=True)
class ProductListView(ViewModel):
    """`admin_producten.html` and its fragment `_producten_lijst.html`."""

    products: list[Product]
    # How many sizes each product has, for the "n maten" line of a card.
    sizes: dict[int, int]
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ProductNewView(ViewModel):
    """`admin_product_nieuw.html`."""

    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ProductView(ViewModel):
    """`admin_product.html` — the article record, read and edit mode."""

    product: Product
    sizes: list[tuple[int, str]]  # (variant id, size) in their sort order
    editing: bool
    csrf_token: str
    #: Data for `ui.record_header` (CR-11 block 5): the head's actions are data,
    #: never a button the screen draws itself.
    primary: dict[str, Any] | None
    actions: list[dict[str, Any]]
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)
