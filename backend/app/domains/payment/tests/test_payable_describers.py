"""T17 of CR-21 (#1748): every payable type has a registered describer.

`payment` never branches on a payable type to describe it (CR-21 Q48); it asks the
describer the owning domain registered in `app/main.py`. A type that is added to
`PayableType` without one would show nameless payments on the payments screen, in the
export and under Wijzigingen — so this is a hard gate, and the lookup itself refuses
with the same sentence.

What the describers answer is not checked here by count: the output of the screen, the
export and the change lines is pinned by the snapshots of
`tests/integration/test_payment_screens_characterisation.py` (T16).

Proven red (8 October 2026): the line that registers `PayableType.MEMBERSHIP` in
`app/main.py` taken out → the first test red, naming `membership` and the message; a
member `ORDER = "order"` added to `PayableType` → the same test red, naming `order`.
"""

from __future__ import annotations

import pytest

import app.main  # noqa: F401 - the describers are registered at app start
from app.domains.payment import describers
from app.domains.payment.api import PayableType, registered_describers

MESSAGE = "describe a payable through its describer (CR-21 Q48)"


def test_every_payable_type_has_a_registered_describer():
    assert len(PayableType) >= 2, "the gate reads the payable types"
    missing = [t.value for t in PayableType if t not in registered_describers()]
    assert not missing, f"payable types without a describer: {missing} — {MESSAGE}"


def test_asking_for_a_type_without_one_is_refused_by_name(monkeypatch):
    """A script that calls into `payment` without the app's start gets a clear error,
    not a payment without a name."""
    monkeypatch.setattr(describers, "_describers", {})
    with pytest.raises(LookupError) as refusal:
        describers.describer(PayableType.REGISTRATION)
    assert "registration" in str(refusal.value) and MESSAGE in str(refusal.value)


def test_a_payable_its_owner_no_longer_knows_is_named_by_type_and_id(db_session):
    """An id the describer does not return still gets a description: the export names
    it by its type and id, as it did before the describers."""
    gone = describers.describe_one(db_session, PayableType.REGISTRATION, 987_654_321)
    assert gone.export_label == "registration #987654321"
    assert gone.contact_name is None and gone.context_href is None
    # The payable's own page is the type's to name, so the link stands for it too.
    assert gone.payable_href == "/admin/inschrijvingen/987654321"
    assert gone.payable_label == "Inschrijving"
