"""The attributes of the `stock` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="stock.stock_location.name",
        columns=("stock.stock_locations.name",),
        label="Locatie",
        name_en="Name",
        help="De naam van de voorraadlocatie.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="stock.stock_location.is_default",
        columns=("stock.stock_locations.is_default",),
        label=None,
        name_en="Is default",
        help="Of dit de standaardlocatie van de tenant is.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="stock.stock_movement.variant_id",
        columns=("stock.stock_movements.variant_id",),
        label=None,
        name_en="Variant id",
        help="De maat waarvan de voorraad veranderde.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="stock.stock_movement.quantity",
        columns=("stock.stock_movements.quantity",),
        label="Aantal",
        name_en="Quantity",
        help="Hoeveel erbij of eraf ging, getekend.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="stock.stock_movement.reason",
        columns=("stock.stock_movements.reason",),
        label=None,
        name_en="Reason",
        help="Ontvangst, uitgifte of correctie.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="stock.stock_movement.note",
        columns=("stock.stock_movements.note",),
        label="Reden",
        name_en="Note",
        help="De reden van een correctie.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="stock.stock_movement.occurred_at",
        columns=("stock.stock_movements.occurred_at",),
        label=None,
        name_en="Occurred at",
        help="Wanneer de beweging gebeurde.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="stock.stock_movement.actor",
        columns=("stock.stock_movements.actor",),
        label=None,
        name_en="Actor",
        help="Wie de beweging boekte, als e-mailadres.",
        ai_exposure=AiExposure.INTERNAL,  # K2
    ),
    Attribute(
        key="stock.stock_movement.order_line_id",
        columns=("stock.stock_movements.order_line_id",),
        label=None,
        name_en="Order line id",
        help="De bestelregel die de beweging schreef.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="stock.stock_reservation.order_line_id",
        columns=("stock.stock_reservations.order_line_id",),
        label=None,
        name_en="Order line id",
        help="De bestelregel waarvoor gereserveerd is.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="stock.stock_reservation.variant_id",
        columns=("stock.stock_reservations.variant_id",),
        label=None,
        name_en="Variant id",
        help="De maat die gereserveerd is.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="stock.stock_reservation.quantity",
        columns=("stock.stock_reservations.quantity",),
        label=None,
        name_en="Quantity",
        help="Hoeveel er gereserveerd is.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="stock.stock_reservation.status",
        columns=("stock.stock_reservations.status",),
        label=None,
        name_en="Status",
        help="Open, geleverd of geannuleerd.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
)
