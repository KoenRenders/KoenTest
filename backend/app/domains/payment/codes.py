"""The code lists the payment domain owns (CR-12 phase 1).

Four lists live here; the fifth, `payment_method`, lives in `mdm` because two
domains store it (§B4.1). Money went first of the business domains on purpose:
it held the most loose string comparisons, and AC1, AC2, AC3 and AC6 are
measured on these screens.

One list that is deliberately absent: the status of a gateway payment. That is
Mollie's vocabulary, not ours — see `providers/mollie.py` and §B4.10. The
distinction is worth stating because the two sit in the same table: *which*
providers we support is our list and gets a code table; *what those providers
report back* is theirs and gets an adapter enum plus a mapping.
"""
from app.domains.payment.models import (
    PayableType,
    PayableTypeCode,
    PayableTypeLabel,
    PaymentProvider,
    PaymentProviderCode,
    PaymentProviderLabel,
    PaymentStatus,
    PaymentStatusCode,
    PaymentStatusLabel,
    PaymentType,
    PaymentTypeCode,
    PaymentTypeLabel,
)
from app.kernel.codes import CodeList, CodeSeed

PAYMENT_STATUS_CODES = (
    CodeSeed(code="pending", nl="In afwachting", en="Pending", sort_order=10),
    CodeSeed(code="paid", nl="Betaald", en="Paid", sort_order=20),
    CodeSeed(code="failed", nl="Mislukt", en="Failed", sort_order=30),
    CodeSeed(code="cancelled", nl="Geannuleerd", en="Cancelled", sort_order=40),
)

PAYMENT_STATUS = CodeList(
    name="payment_status",
    schema="payment",
    codes=PaymentStatusCode,
    labels=PaymentStatusLabel,
    enum=PaymentStatus,
    fk_from=("payment.payment_records.status",),
)

PAYMENT_TYPE_CODES = (
    CodeSeed(code="charge", nl="Vordering", en="Charge", sort_order=10),
    CodeSeed(code="refund", nl="Terugbetaling", en="Refund", sort_order=20),
)

PAYMENT_TYPE = CodeList(
    name="payment_type",
    schema="payment",
    codes=PaymentTypeCode,
    labels=PaymentTypeLabel,
    enum=PaymentType,
    fk_from=("payment.payment_records.type",),
)

PAYABLE_TYPE_CODES = (
    CodeSeed(code="registration", nl="Inschrijving", en="Registration",
             sort_order=10),
    CodeSeed(code="membership", nl="Lidmaatschap", en="Membership", sort_order=20),
)

PAYABLE_TYPE = CodeList(
    name="payable_type",
    schema="payment",
    codes=PayableTypeCode,
    labels=PayableTypeLabel,
    enum=PayableType,
    fk_from=("payment.payment_records.payable_type",),
)

PAYMENT_PROVIDER_CODES = (
    CodeSeed(code="mollie", nl="Mollie", en="Mollie", sort_order=10),
)

PAYMENT_PROVIDER = CodeList(
    name="payment_provider",
    schema="payment",
    codes=PaymentProviderCode,
    labels=PaymentProviderLabel,
    enum=PaymentProvider,
    fk_from=("payment.gateway_payments.provider",),
)
