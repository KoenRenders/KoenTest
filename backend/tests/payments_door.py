"""The payment tests' way to the payment rules, in process (CR-13 phase 4b, #1251).

The seven JSON routes under `/api/v1/payment-status` had no caller but tests and
are gone. Each was a thin door over one function of `payment.service` — the
function the back office's own wrappers (`registreer_terugbetaling`,
`bewerk_betaling`, `ververs_betaalstatus`, …) call as well. The tests used the
routes to book a payment, a refund or a deletion as set-up, or to read the list
and a registration's balance; what they proved was the rule underneath.

So each helper here calls that one service function, commits as the route did,
and answers as the route answered: an `Answer` with the status code and the
body — 400 with the refusal's own words, 404 for a record that does not exist.
The body of a record is `PaymentRecordResponse`, the read model the payments
list is built on.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.domains.payment import service
from app.domains.payment.models import PaymentError, PaymentRecord
from app.domains.payment.schemas import PaymentRecordResponse
from tests.conftest import SEEDED_ADMIN_EMAIL
from tests.forms_door import Answer, _db


def _record(record: PaymentRecord) -> dict:
    return PaymentRecordResponse.model_validate(record).model_dump(mode="json")


def _amount(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _find(db, record_id: str) -> PaymentRecord | None:
    return db.query(PaymentRecord).filter(PaymentRecord.id == str(record_id)).first()


def records(client) -> Answer:
    """Every payment record with its context, as the payments list reads them."""
    db = _db(client)
    db.expire_all()
    return Answer(200, [r.model_dump(mode="json") for r in service.enriched_records(db)])


def export_ods(client, *, context: str = "all", status: str = "all") -> bytes:
    """The payments and claims as a spreadsheet, for the list's filter."""
    from app.domains.payment.exports import build_payments_export_ods

    return build_payments_export_ods(_db(client), context=context, status=status)


def refresh(client, record_id: str, *, actor: str = SEEDED_ADMIN_EMAIL) -> Answer:
    """Ask the gateway for the status of one online payment and apply it."""
    db = _db(client)
    record = _find(db, record_id)
    if record is None:
        return Answer(404, {"detail": "Payment record not found"})
    try:
        service.refresh_record_status(db, record.id, actor=actor)
    except PaymentError as refusal:
        return Answer(400, {"detail": str(refusal)})
    db.commit()
    db.refresh(record)
    return Answer(200, _record(record))


def refund(client, record_id: str, body: dict, *, actor: str = SEEDED_ADMIN_EMAIL) -> Answer:
    """Book a refund on a charge: `amount` (positive), and optionally `note` and `method`."""
    db = _db(client)
    try:
        amount = _amount(body.get("amount"))
    except InvalidOperation:
        amount = None
    if amount is None:
        return Answer(422, {"detail": "amount"})
    extra = {"method": body["method"]} if "method" in body else {}
    try:
        booked = service.create_refund(
            db, str(record_id), amount, note=body.get("note"), actor=actor, **extra
        )
    except ValueError as refusal:
        return Answer(400, {"detail": str(refusal)})
    db.commit()
    db.refresh(booked)
    return Answer(200, _record(booked))


def balance(client, registration_id: int) -> Answer:
    """What a registration owes, paid, got back and still has open."""
    from app.domains.activities.api import Registration

    db = _db(client)
    db.expire_all()
    registration = db.query(Registration).filter(Registration.id == registration_id).first()
    if registration is None:
        return Answer(404, {"detail": "Registration not found"})
    stand = service.registration_balance(db, registration)
    return Answer(200, {key: str(value) for key, value in stand.items()})


def update(client, record_id: str, body: dict, *, actor: str = SEEDED_ADMIN_EMAIL) -> Answer:
    """Edit one record: `status`, `amount_paid` and `note`, each optional."""
    db = _db(client)
    record = _find(db, record_id)
    if record is None:
        return Answer(404, {"detail": "Payment record not found"})
    try:
        service.edit_payment_record(
            db,
            record.id,
            status=body.get("status"),
            amount_paid=_amount(body.get("amount_paid")),
            note=body.get("note"),
            actor=actor,
        )
    except ValueError as refusal:
        return Answer(400, {"detail": str(refusal)})
    db.commit()
    db.refresh(record)
    return Answer(200, _record(record))


def delete(client, record_id: str, *, actor: str = SEEDED_ADMIN_EMAIL) -> Answer:
    """Delete one record as a deliberate act of the treasurer, or be refused."""
    db = _db(client)
    try:
        record = service.delete_payment_record(db, str(record_id), actor=actor)
    except PaymentError as refusal:
        return Answer(400, {"detail": str(refusal)})
    if record is None:
        return Answer(404, {"detail": "Payment record not found"})
    db.commit()
    return Answer(204)
