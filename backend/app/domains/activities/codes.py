"""The code lists the activities domain owns (CR-12 phase 4).

Two lists, and neither is ordinary.

- **`registration_type`** moves out of `public`. It has existed since the
  first migration with two rows, `INDIVIDUAL` and `FAMILY`, but in `public` it
  could get no foreign key from the columns that store it (§8: no key across
  schemas). In this schema it can, so both columns get one. No enum: nothing in
  Python branches on the type; the code only sets a default, and it names that
  default with the constant below.
- **`registration_state`** is DERIVED (§B5.3 note 5): open, closed, past or
  cancelled, computed by `service.registration_state` and stored nowhere. It
  gets a code table and labels and no storing column, so that its four words
  come from `code_label()` like every other code's, and the dictionary that
  held them in the service can go. `RegistrationState` is its enum.
"""
from app.domains.activities.models import (
    RegistrationState,
    RegistrationStateCode,
    RegistrationStateLabel,
    RegistrationTypeCode,
    RegistrationTypeLabel,
)
from app.kernel.codes import Code, CodeList, CodeSeed

REGISTRATION_TYPE_CODES = (
    CodeSeed(code="INDIVIDUAL", nl="Individueel", en="Individual", sort_order=10),
    CodeSeed(code="FAMILY", nl="Gezin", en="Family", sort_order=20),
)

REGISTRATION_TYPE = CodeList(
    name="registration_type", schema="activities",
    codes=RegistrationTypeCode, labels=RegistrationTypeLabel, enum=None,
    fk_from=("activities.registrations.registration_type",
             "activities.activity_sub_registrations.registration_type_code"),
)

#: The registration type every new registration gets today.
INDIVIDUAL = Code("INDIVIDUAL")

#: The words are the ones the service's `STATUS_LABELS` held (§B8.5); "Afgesloten"
#: for a passed deadline was Koen's choice on 16 September 2026.
REGISTRATION_STATE_CODES = (
    CodeSeed(code="open", nl="Open", en="Open", sort_order=10),
    CodeSeed(code="closed", nl="Afgesloten", en="Closed", sort_order=20),
    CodeSeed(code="past", nl="Voorbij", en="Past", sort_order=30),
    CodeSeed(code="cancelled", nl="Geannuleerd", en="Cancelled", sort_order=40),
)

REGISTRATION_STATE = CodeList(
    name="registration_state", schema="activities",
    codes=RegistrationStateCode, labels=RegistrationStateLabel,
    enum=RegistrationState, derived=True,
)
