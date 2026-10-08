"""What forms does when another domain says something happened (CR-13 §B4.9),
and what it does when another domain asks it for something (its ports,
`kernel/ports.py`).

Registered by importing this module in `main.py` (and in a script that creates
tenants outside the app, such as `seed_e2e.py` — #1492).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.kernel.contracts.forms import (
    AttachedAnswer,
    AttachedSubmission,
    SubmitAttached,
    UpdateAttached,
)
from app.kernel.contracts.mdm import TenantCreated
from app.kernel.events import subscribe
from app.kernel.ports import handles


@subscribe(TenantCreated)
def seed_contact_form_of_new_tenant(event: TenantCreated, db: Session) -> None:
    """A new tenant starts with a contact form, as the first one did (#1509)."""
    from app.domains.forms.service import seed_contact_form

    seed_contact_form(db, event.tenant_id)


# ── Ports (`kernel/contracts/forms.py`) ──────────────────────────────────────
#
# A handler is thin: the contract in, the service function that always did the
# work, the outcome out. No rule is written here, and nothing is committed — the
# caller's transaction commits.


def _answers_in(answers: tuple[AttachedAnswer, ...]) -> list:
    from app.domains.forms.schemas import AnswerIn

    return [
        AnswerIn(
            field_id=answer.field_id,
            text=answer.text,
            number=answer.number,
            option_ids=list(answer.option_ids),
            rating=answer.rating,
            other_text=answer.other_text,
        )
        for answer in answers
    ]


@handles(SubmitAttached)
def submit_attached(port: SubmitAttached, db: Session) -> AttachedSubmission:
    from app.domains.forms.models import Form
    from app.domains.forms.service import submit_attached as store

    form = db.get(Form, port.form_id)
    if form is None:
        raise LookupError("form")
    submission = store(
        db,
        form,
        _answers_in(port.answers),
        submitter_name=port.submitter_name,
        submitter_email=port.submitter_email,
    )
    return AttachedSubmission(submission_id=submission.id)


@handles(UpdateAttached)
def update_attached(port: UpdateAttached, db: Session) -> AttachedSubmission:
    from app.domains.forms.service import update_attached as replace

    submission = replace(db, port.submission_id, _answers_in(port.answers))
    return AttachedSubmission(submission_id=submission.id)
