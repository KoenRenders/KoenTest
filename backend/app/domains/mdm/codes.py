"""The code lists master data owns (CR-12).

A list lands here when it is used by more than one domain, which is what
master data means (§B4.1). Doubt therefore resolves towards `mdm`: moving a
list later copies rows and re-points a foreign key, and the stored values do
not change, so a wrong guess is cheap.

Phase 0 declared the language list; phase 1 adds the payment method. The four
single-language code tables already here (`gender`, `contact_type`,
`relation_type`, `legal_form`) are split into the codes/labels shape in phase 2.
"""
from app.domains.mdm.models import (
    LanguageCode,
    LanguageLabel,
    PaymentMethod,
    PaymentMethodCode,
    PaymentMethodLabel,
)
from app.kernel.codes import CodeList, CodeSeed

#: The two languages every label table is keyed against.
LANGUAGE_CODES = (
    CodeSeed(code="nl", nl="Nederlands", en="Dutch", sort_order=10),
    CodeSeed(code="en", nl="Engels", en="English", sort_order=20),
)

LANGUAGE = CodeList(
    name="language",
    schema="mdm",
    codes=LanguageCode,
    labels=LanguageLabel,
    # No enum: nothing in Python branches on a language code. The active
    # language comes from the tenant setting and is used as a lookup key, never
    # compared to a member (§B4.3).
    enum=None,
    # Deliberately empty, and this is the one list where that needs saying.
    # Every `_labels` table in every schema stores a language code, so a
    # hand-written list here would need a line per phase and would be wrong
    # the first time somebody forgot. The shape gate checks it instead: it
    # walks every registered list and holds that its labels table carries the
    # foreign key to `mdm.language_codes`.
    fk_from=(),
)


PAYMENT_METHOD_CODES = (
    CodeSeed(code="online", nl="Online", en="Online", sort_order=10),
    CodeSeed(code="transfer", nl="Overschrijving", en="Bank transfer",
             sort_order=20),
    CodeSeed(code="cash", nl="Cash", en="Cash", sort_order=30),
)

PAYMENT_METHOD = CodeList(
    name="payment_method",
    schema="mdm",
    codes=PaymentMethodCode,
    labels=PaymentMethodLabel,
    enum=PaymentMethod,
    # The two columns that store a payment method, in two different schemas.
    # This is the cross-schema foreign key §B2.4 allows, and the reason the
    # list sits in `mdm` rather than in `payment`.
    fk_from=("payment.payment_records.method",
             "activities.registrations.payment_method"),
)
