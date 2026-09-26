"""Publieke facade van het payment-component (fase 3, #401).

Gateway (Mollie) en status (PaymentRecord-grootboek incl. refunds) samen als
één component; andere componenten en de oude wereld gaan uitsluitend via deze
module. §19.3: `get_records_for` is dé PaymentRecord-lookup-helper — geen
losse queries op het model buiten het component.
"""
from app.domains.payment.gateway_service import (  # noqa: F401
    create_payment,
    refresh_payment_status,
)
from app.domains.payment.models import (  # noqa: F401
    GatewayPayment,
    PayableType,
    PaymentProvider,
    PaymentRecord,
    PaymentRecordHistory,
    PaymentStatus,
    PaymentType,
)
# CR-12: de codelijsten van dit domein horen bij de publieke schil, zodat een
# ander domein een FK-doel en een enum via één deur bereikt.
from app.domains.payment.codes import (  # noqa: F401
    PAYABLE_TYPE,
    PAYMENT_PROVIDER,
    PAYMENT_STATUS,
    PAYMENT_TYPE,
)
from app.domains.payment.service import (  # noqa: F401
    aggregate,
    checkout_url_for,
    confirm_manual_payment,
    create_payment_record,
    create_refund,
    current_membership_counts,
    derived_status,
    edit_payment_record,
    enriched_records,
    apply_zicht,
    count_zichten,
    filter_records,
    group_cards,
    matches_filter,
    may_delete,
    count_records_for_family,
    count_registration_records_by_activity,
    family_payables,
    get_records_for,
    handle_gateway_update,
    membership_price_for_date,
    membership_valid_period,
    net_paid,
    reconcile_charges,
    reconcile_registration_charges,
    refresh_record_status,
    registration_balance,
    set_payment_status,
    void_payment_record,
)

__all__ = [
    "PAYABLE_TYPE", "PAYMENT_PROVIDER", "PAYMENT_STATUS", "PAYMENT_TYPE",
    "PayableType", "PaymentProvider", "PaymentStatus", "PaymentType",
    "GatewayPayment", "PaymentRecord", "PaymentRecordHistory",
    "create_payment", "refresh_payment_status",
    "aggregate", "checkout_url_for", "confirm_manual_payment", "create_payment_record", "create_refund",
    "current_membership_counts", "derived_status", "edit_payment_record",
    "apply_zicht", "count_zichten",
    "enriched_records", "filter_records", "group_cards", "matches_filter",
    "may_delete",
    "count_records_for_family", "count_registration_records_by_activity",
    "family_payables",
    "get_records_for", "handle_gateway_update",
    "membership_price_for_date", "membership_valid_period", "net_paid",
    "reconcile_charges", "reconcile_registration_charges", "registration_balance",
    "refresh_record_status", "set_payment_status", "void_payment_record",
]
