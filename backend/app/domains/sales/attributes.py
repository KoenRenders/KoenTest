"""The attributes of the `sales` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="sales.sales_order.person_id",
        columns=("sales.sales_orders.person_id",),
        label=None,
        name_en="Person id",
        help="De koper — de persoon van het getypte adres, nooit de verkoper.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="sales.sales_order.guest_name",
        columns=("sales.sales_orders.guest_name",),
        label="Naam",
        name_en="Guest name",
        help="De naam van een gast die zonder account bestelt.",
        ai_exposure=AiExposure.TOKENISED,  # K2
    ),
    Attribute(
        key="sales.sales_order.guest_email",
        columns=("sales.sales_orders.guest_email",),
        label="E-mail",
        name_en="Guest email",
        help="Het e-mailadres van een gast die zonder account bestelt.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="sales.sales_order.guest_mobile",
        columns=("sales.sales_orders.guest_mobile",),
        label="Mobiel",
        name_en="Guest mobile",
        help="Het mobiel nummer van een gast die zonder account bestelt.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="sales.sales_order.payment_method",
        columns=("sales.sales_orders.payment_method",),
        label="Betaalwijze",
        name_en="Payment method",
        help="Online of per overschrijving.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="sales.sales_order.placed_at",
        columns=("sales.sales_orders.placed_at",),
        label=None,
        name_en="Placed at",
        help="Wanneer de bestelling geplaatst is.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="sales.sales_order_line.variant_id",
        columns=("sales.sales_order_lines.variant_id",),
        label=None,
        name_en="Variant id",
        help="De maat die besteld is.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="sales.sales_order_line.quantity",
        columns=("sales.sales_order_lines.quantity",),
        label="Aantal",
        name_en="Quantity",
        help="Hoeveel van de maat besteld is.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="sales.sales_order_line.unit_code",
        columns=("sales.sales_order_lines.unit_code",),
        label=None,
        name_en="Unit code",
        help="De UN/ECE-eenheid, C62 voor een stuk.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="sales.sales_order_line.unit_price",
        columns=("sales.sales_order_lines.unit_price",),
        label="Prijs",
        name_en="Unit price",
        help="De prijs per stuk, vastgelegd bij het bestellen.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="sales.sales_order_line.delivered_at",
        columns=("sales.sales_order_lines.delivered_at",),
        label=None,
        name_en="Delivered at",
        help="Wanneer de regel afgeleverd is.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="sales.shop_contact.person_id",
        columns=("sales.shop_contacts.person_id",),
        label=None,
        name_en="Person id",
        help="De contactpersoon van de webshop.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="sales.shop_contact.sort_order",
        columns=("sales.shop_contacts.sort_order",),
        label=None,
        name_en="Sort order",
        help="De volgorde van de contactpersoon.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="sales.shop_settings.intro",
        columns=("sales.shop_settings.intro",),
        label="Inleiding",
        name_en="Intro",
        help="De inleidende tekst van de webshop.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
)
