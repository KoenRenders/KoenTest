"""The attributes of the `payment` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="payment.gateway_payment.provider",
        columns=("payment.gateway_payments.provider",),
        label=None,
        name_en="Provider",
        help="The provider of the gateway payment.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="payment.gateway_payment.provider_payment_id",
        columns=("payment.gateway_payments.provider_payment_id",),
        label=None,
        name_en="Provider payment id",
        help="The provider payment id of the gateway payment.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="payment.gateway_payment.amount",
        columns=("payment.gateway_payments.amount",),
        label=None,
        name_en="Amount",
        help="The amount of the gateway payment.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="payment.gateway_payment.currency",
        columns=("payment.gateway_payments.currency",),
        label=None,
        name_en="Currency",
        help="The currency of the gateway payment.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="payment.gateway_payment.status",
        columns=("payment.gateway_payments.status",),
        label=None,
        name_en="Status",
        help="The status of the gateway payment.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="payment.gateway_payment.checkout_url",
        columns=("payment.gateway_payments.checkout_url",),
        label=None,
        name_en="Checkout url",
        help="The checkout url of the gateway payment.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="payment.gateway_payment.description",
        columns=("payment.gateway_payments.description",),
        label=None,
        name_en="Description",
        help="The description of the gateway payment.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="payment.gateway_payment.payment_metadata",
        columns=("payment.gateway_payments.payment_metadata",),
        label=None,
        name_en="Payment metadata",
        help="The payment metadata of the gateway payment.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="payment.payment_record.payable_type",
        columns=("payment.payment_records.payable_type",),
        label="Soort",
        name_en="Payable type",
        help="Waarvoor betaald wordt: lidgeld of een activiteit.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="payment.payment_record.payable_id",
        columns=("payment.payment_records.payable_id",),
        label=None,
        name_en="Payable id",
        help="The payable id of the payment record.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="payment.payment_record.amount",
        columns=("payment.payment_records.amount",),
        label="Te betalen",
        name_en="Amount",
        help="Het bedrag van deze ene regel. Een terugbetaling is negatief.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="payment.payment_record.method",
        columns=("payment.payment_records.method",),
        label="Betaalwijze",
        name_en="Method",
        help="Hoe er betaald werd of moet worden: online, overschrijving of cash.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="payment.payment_record.status",
        columns=("payment.payment_records.status",),
        label="Status",
        name_en="Status",
        help="Waar deze betaling staat: in afwachting, betaald, mislukt of geannuleerd.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="payment.payment_record.type",
        columns=("payment.payment_records.type",),
        label="Type",
        name_en="Type",
        help="Of deze regel een vordering is of een terugbetaling.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="payment.payment_record.amount_paid",
        columns=("payment.payment_records.amount_paid",),
        label="Betaald",
        name_en="Amount paid",
        help="Wat er op deze regel ontvangen is.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="payment.payment_record.note",
        columns=("payment.payment_records.note",),
        label="Notitie",
        name_en="Note",
        help="Wat de penningmeester erbij schreef.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="payment.payment_record.structured_communication",
        columns=("payment.payment_records.structured_communication",),
        label="Mededeling (OGM)",
        name_en="Structured communication",
        help="De gestructureerde mededeling op een overschrijving.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="payment.payment_record.paid_at",
        columns=("payment.payment_records.paid_at",),
        label="Betaald op",
        name_en="Paid at",
        help="Wanneer er betaald is — iets anders dan wanneer de vordering gemaakt werd.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
)


# The data the reporting universe stands on that no single stored column is (CR-33 phase 1).
UNIVERSE_ENTRIES: tuple[Attribute, ...] = (
    Attribute(
        key="payment.payment_record.created_at",
        columns=("payment.payment_records.created_at",),
        label="Aanmaakdatum",
        name_en="Created at",
        help="Wanneer de vordering aangemaakt is — iets anders dan wanneer er betaald is.",
        ai_exposure=AiExposure.INTERNAL,
    ),
    Attribute(
        key="payment.payment_record.id",
        columns=("payment.payment_records.id",),
        label="Betaling",
        name_en="Id",
        help="Het betaalrecord zelf.",
        ai_exposure=AiExposure.INTERNAL,
    ),
)
