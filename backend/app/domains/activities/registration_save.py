"""The one save of a registration's record page (#2127; CR-11 phase 5, round 4).

A registration used to be saved in three goes: the order and the contact with
"Opslaan", the answers to the component's questions with a button of their own, a
refusal of one leaving the other written. The record page has ONE save now, and it
refuses as a whole: the order, the contact and the remark, and the answers are
written in one transaction, or nothing is — and every refusal comes back at its
place (`kernel.refusals`), with what was typed kept by the page.

The rules stay where they were: the order's in `service.set_order_quantities`, the
contact's in `service.update_registration_contact` and the registration's own
`check()`, the answers' in the forms port. This only runs them inside one savepoint,
hears every refusal and commits once — the shape of `fiche.save_fiche`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session

from app.domains.activities import service
from app.domains.activities.models import Registration
from app.domains.activities.service import ActiviteitFout
from app.i18n import _
from app.kernel.refusals import FieldError, Refusals


class RegistrationRefusal(ActiviteitFout):
    """The save is refused; `errors` says why and where, all of them."""

    def __init__(self, errors: list[FieldError]) -> None:
        self.errors = list(errors)
        super().__init__(" ".join(error.message for error in self.errors))


@dataclass
class RegistrationSave:
    """What the record page's form sends, read at the door."""

    #: The counter of every product (`product_<id>`), 0 being "not chosen".
    quantities: dict[int, int] = field(default_factory=dict)
    #: The contact fields and the remark the form carries; a field it does not carry
    #: stays as it is.
    contact: dict[str, Optional[str]] = field(default_factory=dict)
    #: The answers (`forms.answers_from_form`), or None when the component asks none.
    answers: Optional[list] = None
    #: Refusals the door heard while reading the form (an e-mail address that is none).
    errors: list[FieldError] = field(default_factory=list)


def save_registration(
    db: Session,
    activity_id: int,
    registration_id: int,
    data: RegistrationSave,
    *,
    actor: Optional[str] = None,
) -> Optional[Registration]:
    """Write the whole page in one transaction. None when the registration does not
    exist; `RegistrationRefusal` with nothing written when any part is refused."""
    reg = service._registratie(db, activity_id, registration_id)
    if reg is None:
        return None
    errors = Refusals(list(data.errors), kinds=(ActiviteitFout,), passing=(RegistrationRefusal,))
    savepoint = db.begin_nested()
    try:
        _order(db, activity_id, reg, data.quantities, actor, errors)
        if data.contact:
            service.update_registration_contact(
                db,
                activity_id,
                registration_id,
                data.contact,
                actor=actor,
                commit=False,
                errors=errors,
            )
        if data.answers is not None:
            _answers(db, registration_id, data.answers, actor, errors)
        if errors.found:
            raise RegistrationRefusal(errors.found)
    except Exception:
        # Also after a failed flush: the savepoint is then deactivated, not closed.
        try:
            savepoint.rollback()
        except InvalidRequestError:
            pass
        raise
    savepoint.commit()
    db.commit()
    db.refresh(reg)
    return reg


def _order(
    db: Session,
    activity_id: int,
    reg: Registration,
    quantities: dict[int, int],
    actor: Optional[str],
    errors: Refusals,
) -> None:
    """A count is refused at its counter: a negative one, or a product that is not the
    component's. What passes goes through one call, one reconciliation."""
    for product_id, quantity in quantities.items():
        place = f"product_{product_id}"
        if quantity < 0:
            errors.add(place, _("Aantal kan niet negatief zijn."))
            continue
        with errors.at(place):
            if service.controleer_bestelproduct(db, activity_id, reg, product_id) is None:
                errors.add(place, _("Dit product hoort niet bij dit onderdeel."))
    if errors.found:
        return
    with errors.at(""):
        service.set_order_quantities(db, activity_id, reg.id, quantities, actor=actor, commit=False)


def _answers(
    db: Session, registration_id: int, answers: list, actor: Optional[str], errors: Refusals
) -> None:
    """An answer the forms port refuses names its question (`VeldFout`): the page marks
    it, as the public form does (`f<question id>`)."""
    try:
        service.edit_answers(db, registration_id, answers, actor=actor, commit=False)
    except HTTPException as exc:
        question: Any = getattr(exc, "veld_id", None)
        errors.add(f"f{question}" if question is not None else "", str(exc.detail))
    except ActiviteitFout as exc:
        errors.add("", str(exc))
