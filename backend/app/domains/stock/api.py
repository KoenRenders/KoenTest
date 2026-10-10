"""Public facade of the stock domain (CR-21).

Everything another module may use lives here. The ORM classes are exported for
other domains' services, not for screens; the layer gate holds that line.
"""

from app.domains.stock.codes import MOVEMENT_REASON, RESERVATION_STATUS  # noqa: F401
from app.domains.stock.models import (  # noqa: F401
    MovementReason,
    NotEnoughStock,
    ReservationStatus,
    StockError,
    StockLocation,
    StockMovement,
    StockReservation,
)
from app.domains.stock.service import (  # noqa: F401
    available,
    correct,
    lock_key,
    on_hand,
    receive,
)

__all__ = [
    "MOVEMENT_REASON",
    "RESERVATION_STATUS",
    "MovementReason",
    "NotEnoughStock",
    "ReservationStatus",
    "StockError",
    "StockLocation",
    "StockMovement",
    "StockReservation",
    "available",
    "correct",
    "lock_key",
    "on_hand",
    "receive",
]
