"""The attributes of the `pricing` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="pricing.price.product_id",
        columns=("pricing.prices.product_id",),
        label=None,
        name_en="Product id",
        help="Het artikel waar de prijs bij hoort.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="pricing.price.variant_id",
        columns=("pricing.prices.variant_id",),
        label=None,
        name_en="Variant id",
        help="De maat waar de prijs bij hoort, of geen voor de artikelprijs.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="pricing.price.price_type",
        columns=("pricing.prices.price_type",),
        label=None,
        name_en="Price type",
        help="De gewone prijs of de ledenprijs.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="pricing.price.amount",
        columns=("pricing.prices.amount",),
        label="Prijs",
        name_en="Amount",
        help="Het bedrag van de prijs.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="pricing.price.member_amount",
        columns=("pricing.prices.amount",),
        label="Ledenprijs",
        name_en="Member amount",
        help="Het bedrag dat leden betalen — dezelfde kolom, de ledenprijs-rij.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="pricing.price.currency",
        columns=("pricing.prices.currency",),
        label=None,
        name_en="Currency",
        help="De munteenheid van de prijs.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="pricing.price.valid_from",
        columns=("pricing.prices.valid_from",),
        label="Vanaf",
        name_en="Valid from",
        help="Vanaf welke datum de prijs geldt.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
)
