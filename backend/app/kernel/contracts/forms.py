"""Events die het forms-component publiceert (contract, zie forms/CONTRACT.md) —
and, below them, the ports it handles."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from app.kernel.events import KernelEvent
from app.kernel.ports import Port


@dataclass(frozen=True)
class SubmissionCreated(KernelEvent):
    """Een formulier-inzending is aangemaakt (synchroon, in-transactie —
    event-ladder trede 1). Consumenten: workflow (behartigen-taak, #398)."""

    form_id: int
    form_slug: Optional[str]
    submission_id: int
    submitter_name: Optional[str]
    submitter_email: Optional[str]


@dataclass(frozen=True)
class SubmissionDeleted(KernelEvent):
    """A form submission was deleted (synchronous, in-transaction). Consumers:
    workflow closes the open task of this submission (#1377), so the werkbank no
    longer points at a submission that does not exist."""

    form_id: int
    form_slug: Optional[str]
    submission_id: int


# ── Ports this component handles (`kernel/ports.py`, §3.2.1 step 2) ──────────


@dataclass(frozen=True)
class AttachedAnswer:
    """One answer to one question of a form, as plain values — the six fields of
    forms' own `AnswerIn`, so the handler can hand it to the form's rules."""

    field_id: int
    text: Optional[str] = None
    number: Optional[Decimal] = None
    #: One option (radio, select) or several (checkbox).
    option_ids: tuple[int, ...] = ()
    rating: Optional[int] = None
    #: The free text beside a ticked "Andere…" option.
    other_text: Optional[str] = None


@dataclass(frozen=True)
class AttachedSubmission:
    """The outcome of both ports below: the submission that holds the answers."""

    submission_id: int


@dataclass(frozen=True)
class SubmitAttached(Port):
    """Store the answers another domain's record carries (a registration's answers
    to its component's questions, CR-14 §B4.2), as a submission attached to that
    record: judged by the form's own rules, flushed, not committed — the caller's
    transaction commits it or takes it back. No mail and no event.

    Outcome: `AttachedSubmission`.
    Refuses with forms' `VeldFout` (an `HTTPException`, 422, naming the question in
    `veld_id`): a required question without an answer, an option that is not the
    question's, a value outside its range.
    """

    form_id: int
    answers: tuple[AttachedAnswer, ...]
    submitter_name: str
    submitter_email: str


@dataclass(frozen=True)
class UpdateAttached(Port):
    """Replace the answers of an attached submission (the board corrects a
    registration's answers, CR-14 §B4.7): the same rules as when they were given,
    flushed, not committed.

    Outcome: `AttachedSubmission`.
    Refuses with forms' `VeldFout` as `SubmitAttached` does, and with
    `LookupError` for a submission that does not exist or is not attached.
    """

    submission_id: int
    answers: tuple[AttachedAnswer, ...]
