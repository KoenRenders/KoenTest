"""Events the product component publishes (contract, CR-21 — the webshop).

`ProductDeleted` is published by the product's delete inside its transaction
(CR-21 phase 1), so `pricing` can drop the product's prices and `stock` can
refuse a delete that still has movements in that same transaction — a refusal in
either rolls the delete back (Q75). The handlers come with the deletion flow;
the contract stands here so all sides share one shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.kernel.events import KernelEvent


@dataclass(frozen=True)
class ProductDeleted(KernelEvent):
    """A product — or one of its sizes — is deleted, and its prices with it.

    `variant_ids` are the variants whose prices go. `product_gone` says the whole
    product is deleted, so its own price (`variant_id` NULL) goes too; deleting
    one size leaves the product and its own price in place. Events are plain
    data.
    """

    product_id: int
    variant_ids: tuple[int, ...]
    product_gone: bool
