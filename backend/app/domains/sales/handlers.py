"""What the sales component does when the catalogue says a product is gone (CR-21).

The gate of a delete lives here, in the component that knows the orders, and not
in the product: an article that stands in an order is decommissioned, never
deleted (T19, Q75). The handler runs inside the delete's transaction, so a
refusal here rolls the delete back.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.sales.models import ProductHasOrderLines, SalesOrderLine
from app.kernel.contracts.product import ProductDeleted, SizeDeleteRefused
from app.kernel.events import subscribe


def _has_order_lines(db: Session, variant_ids: tuple[int, ...]) -> bool:
    if not variant_ids:
        return False
    return (
        db.query(SalesOrderLine.id).filter(SalesOrderLine.variant_id.in_(variant_ids)).first()
        is not None
    )


@subscribe(ProductDeleted)
def refuse_delete_with_order_lines(event: ProductDeleted, db: Session) -> None:
    """Refuse a delete — of an article or of one size — that still stands in an
    order. A size's refusal carries the size's id and a bare fragment, so
    `product` names the size at its row; a whole article raises the full sentence.
    """
    if not _has_order_lines(db, event.variant_ids):
        return
    from app.i18n import _

    if event.product_gone:
        raise ProductHasOrderLines(
            _("Dit artikel staat in een bestelling en kan niet verwijderd worden.")
        )
    raise SizeDeleteRefused(
        event.variant_ids[0],
        _("staat in een bestelling en kan niet verwijderd worden."),
    )
