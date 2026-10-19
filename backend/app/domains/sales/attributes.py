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
        key="sales.sales_order.buyer_party_id",
        columns=("sales.sales_orders.buyer_party_id",),
        label=None,
        name_en="Buyer party id",
        help="Voor wie de bestelling is: de eigen partij van de persoon (voor mezelf), een organisatie (namens), leeg voor een gast.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="sales.sales_order.buyer_name",
        columns=("sales.sales_orders.buyer_name",),
        label=None,
        name_en="Buyer name",
        help="De naam van de koper zoals hij bij het plaatsen was: de organisatie of de persoon.",
        ai_exposure=AiExposure.TOKENISED,  # K2
    ),
    Attribute(
        key="sales.sales_order.buyer_street",
        columns=("sales.sales_orders.buyer_street",),
        label=None,
        name_en="Buyer street",
        help="De straat van de koper bij het plaatsen; leeg als de partij geen adres heeft.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="sales.sales_order.buyer_house_number",
        columns=("sales.sales_orders.buyer_house_number",),
        label=None,
        name_en="Buyer house number",
        help="Het huisnummer van de koper bij het plaatsen.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="sales.sales_order.buyer_bus_number",
        columns=("sales.sales_orders.buyer_bus_number",),
        label=None,
        name_en="Buyer box number",
        help="Het busnummer van de koper bij het plaatsen.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="sales.sales_order.buyer_postal_code",
        columns=("sales.sales_orders.buyer_postal_code",),
        label=None,
        name_en="Buyer postal code",
        help="De postcode van de koper bij het plaatsen, als tekst.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="sales.sales_order.buyer_municipality",
        columns=("sales.sales_orders.buyer_municipality",),
        label=None,
        name_en="Buyer municipality",
        help="De gemeente van de koper bij het plaatsen.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="sales.sales_order.buyer_country",
        columns=("sales.sales_orders.buyer_country",),
        label=None,
        name_en="Buyer country",
        help="Het land van de koper bij het plaatsen (ISO 3166-1 alpha-2).",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="sales.sales_order.buyer_vat_number",
        columns=("sales.sales_orders.buyer_vat_number",),
        label=None,
        name_en="Buyer VAT number",
        help="Het btw-nummer van de koper bij het plaatsen; een particulier heeft er geen.",
        ai_exposure=AiExposure.INTERNAL,  # K9
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
        key="sales.sales_order.submission_key",
        columns=("sales.sales_orders.submission_key",),
        label=None,
        name_en="Submission key",
        help="The key of the shown form the order came from (#1987): a form is accepted once.",
        ai_exposure=AiExposure.NONE,  # K1, as the answer token: a technical key
    ),
    Attribute(
        key="sales.sales_order.secret_key",
        columns=("sales.sales_orders.secret_key",),
        label=None,
        name_en="Secret key",
        help="The secret of the thank-you page's link: random and unique, never shown in the back office.",
        ai_exposure=AiExposure.NONE,  # K1: a technical key, never logged
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
