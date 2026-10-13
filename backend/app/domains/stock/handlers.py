"""What the stock component does when the catalogue says a product is gone (CR-21).

The gate of a delete lives here, in the component that knows the movements, and
not in the product: an article with a movement is decommissioned, never deleted
(Q75, AC19). The handler runs inside the delete's transaction, so a refusal here
rolls the delete back — the prices `pricing` already dropped in that same
transaction come back. `pricing`'s handler is imported before this one in
`app/main.py`, so it drops the prices first and this refusal exercises the
rollback (A3).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.stock.models import ProductHasMovements
from app.domains.stock.service import has_movements, reserve
from app.kernel.contracts.product import ProductDeleted, SizeDeleteRefused
from app.kernel.contracts.stock import ReservationMade, ReserveStock
from app.kernel.events import subscribe
from app.kernel.ports import handles


@handles(ReserveStock)
def reserve_stock(port: ReserveStock, db: Session) -> ReservationMade:
    """Reserve one order line (the port's handler, CR-21 Q64). The refusal —
    `NotEnoughStock` — passes through untouched and rolls the caller's order back."""
    reserve(
        db,
        port.order_line_id,
        port.variant_id,
        port.quantity,
        allow_short=port.allow_short,
    )
    return ReservationMade(order_line_id=port.order_line_id)


@subscribe(ProductDeleted)
def refuse_delete_with_movements(event: ProductDeleted, db: Session) -> None:
    """Refuse a delete — of an article or of one size — that still has movements.

    An article with a movement is decommissioned, never deleted (Q75, AC19). The
    sentence raised here is the bare fact; the screen that catches it decides the
    offer — an article already Afgevoerd is not offered the alternative again.
    For a size the article stays; the refusal carries the size's id and the reason
    as a bare fragment, so `product` names the size at its row and words nothing
    of movements itself.
    """
    if not has_movements(db, event.variant_ids):
        return
    from app.i18n import _

    if event.product_gone:
        raise ProductHasMovements(
            _("Dit artikel heeft voorraadbewegingen en kan niet verwijderd worden.")
        )
    raise SizeDeleteRefused(
        event.variant_ids[0],
        _("heeft voorraadbewegingen en kan niet verwijderd worden."),
    )
