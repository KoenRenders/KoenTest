"""The tables of the audit domain (CR-13 phase 4, §B4.5): none of its own.

Every history table (`PersonHistory`, `MembershipHistory`, `PaymentRecordHistory`,
…) is its domain's model, next to the table it records, in that domain's schema.
Each owner writes its own rows (`<domain>/history.py`); audit reads them for the
change screens (`changes.py`). A table audit owns goes here.
"""
