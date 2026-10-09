"""The refusals of one save, each with its place (#1561, shared since #1590).

A record is saved as a whole: one transaction for the record and its groups. When
such a save is refused, the screen wants every refusal at once and each at its
place — the field, the row, or the record as a whole — so it can mark them all
(`ui.save_refusal`, `static/record-form.js`).

This is the small machinery for that, with no knowledge of any domain: the place
of a refusal (`FieldError`) and a collector (`Refusals`) that notes a refusal a
rule raises and lets the save go on to hear the next one. The rules themselves
stay where they are — on the object, in the service — and are called inside
`at(place)`; the save's own savepoint takes back whatever was written before the
collector says "refused".

The activity's fiche built it first (`activities.fiche`, #1561); the household
is the second record with one save (#1590), and two copies of a collector would
drift — so it lives here, and both use it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True)
class FieldError:
    """One refusal and its place in the form: a field's name, a row (`c.<key>`),
    or "" for the record as a whole."""

    field: str
    message: str


#: The statuses a door answers for a refusal the visitor can do something about.
#: A 404 is not one — the thing is gone — and neither is a 403.
REFUSAL_STATUSES = (400, 409, 422)


def as_refusal(raised: Exception) -> FieldError:
    """What a door heard, as a refusal of the form as a whole (#1831) — or the
    same exception again when it is none.

    Two shapes are a refusal: an HTTP error with one of `REFUSAL_STATUSES`, whose
    `detail` is the sentence, and a domain's own refusal, whose text is the
    sentence. An HTTP error with another status is no refusal and is raised on,
    for the application to answer. Reads `status_code` and `detail` by name: the
    kernel knows no web framework.
    """
    status = getattr(raised, "status_code", None)
    if status is not None and status not in REFUSAL_STATUSES:
        raise raised
    return FieldError("", str(getattr(raised, "detail", raised)))


class Refusals:
    """What one save refuses. `kinds` are the exception types that are a refusal
    of a rule (a domain's own error type); `passing` are subtypes of those that
    are not to be noted here and travel on (a question, the save's own verdict)."""

    def __init__(
        self,
        found: list[FieldError] | None = None,
        *,
        kinds: tuple[type[Exception], ...],
        passing: tuple[type[Exception], ...] = (),
    ) -> None:
        self.found: list[FieldError] = list(found or [])
        self._kinds = kinds
        self._passing = passing

    def add(self, place: str, message: str) -> None:
        self.found.append(FieldError(place, message))

    @contextmanager
    def at(self, place: str) -> Iterator[None]:
        """A rule that refuses inside this block is noted at `place`, and the save
        goes on to hear the next one."""
        try:
            yield
        except self._kinds as refusal:
            if self._passing and isinstance(refusal, self._passing):
                raise
            self.add(place, str(refusal))

    def touches(self, row: str) -> bool:
        """This row, or a field of it, was refused: it is not written."""
        return any(e.field == row or e.field.startswith(row + ".") for e in self.found)
