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

from app.domains.stock.models import StockError
from app.domains.stock.service import has_movements
from app.kernel.contracts.product import ProductDeleted
from app.kernel.events import subscribe


@subscribe(ProductDeleted)
def refuse_delete_with_movements(event: ProductDeleted, db: Session) -> None:
    """Refuse a delete — of an article or of one size — that still has movements.

    The sentence names the alternative (AC19, W23): set the article to Afgevoerd
    instead of deleting it. For a size the article stays; only the size is named.
    """
    if not has_movements(db, event.variant_ids):
        return
    from app.i18n import _

    message = (
        _("Dit artikel heeft voorraadbewegingen en kan niet verwijderd worden — zet het afgevoerd.")
        if event.product_gone
        else _("Deze maat heeft voorraadbewegingen en kan niet verwijderd worden.")
    )
    raise StockError(message)
