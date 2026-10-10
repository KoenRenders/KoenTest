"""Events the product component publishes (contract, CR-21 — the webshop).

`ProductDeleted` is published by the product's delete inside its transaction
(CR-21 phase 1), so `pricing` can drop the product's prices in that same
transaction — a refusal there rolls the delete back (Q75). The handler comes
with the deletion flow; the contract stands here so both sides share one shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.kernel.events import KernelEvent


@dataclass(frozen=True)
class ProductDeleted(KernelEvent):
    """A product — or one of its sizes — is deleted, and its prices with it.

    `variant_ids` are the variants that go with the product; deleting one size
    carries just that one id. Events are plain data.
    """

    product_id: int
    variant_ids: tuple[int, ...]
