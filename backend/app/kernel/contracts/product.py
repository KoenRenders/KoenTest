"""Events the product component publishes (contract, CR-21 — the webshop).

`ProductDeleted` is published by the product's delete inside its transaction
(CR-21 phase 1), so `pricing` can drop the product's prices and `stock` can
refuse a delete that still has movements in that same transaction — a refusal in
either rolls the delete back (Q75). A subscriber that refuses raises
`SizeDeleteRefused` for the size it refuses; the publisher names that size at its
row and in the sentence. The handlers come with the deletion flow; the contract
stands here so all sides share one shape.
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


class SizeDeleteRefused(Exception):
    """A subscriber on `ProductDeleted` refused the delete of one size.

    The subscriber (today `stock`, later `sales`) raises it for the one variant it
    refuses, carrying that `variant_id` and its own `reason` — a bare sentence
    fragment, without the size's name. The publisher (`product`) catches it and
    names the size at its row and in the sentence, so the reason lives in one
    place and the publisher words no other domain's rule.
    """

    def __init__(self, variant_id: int, reason: str):
        super().__init__(reason)
        self.variant_id = variant_id
        self.reason = reason
