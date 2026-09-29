"""`ValidityPeriod`: a closed range of dates (CR-13 §B4.7).

A membership is valid from one date to another, both included; whether a date
falls inside is the question the member price, the renewal window and the
member list all ask. The value object answers it once, and refuses a period
that ends before it begins — the rule `membership.memberships` gets as a
`CHECK (valid_from <= valid_to)` in phase 3.

`str(period)` is `01-01-2026 – 31-12-2026`, in the one short-date format the
screens use (`app/i18n.short_date`), so a period in an f-string reads as a
period (§B4.7).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


class InvalidValidityPeriod(ValueError):
    """A period that ends before it begins."""


@dataclass(frozen=True)
class ValidityPeriod:
    """From `valid_from` to `valid_to`, both days included."""

    valid_from: date
    valid_to: date

    def __post_init__(self) -> None:
        if self.valid_to < self.valid_from:
            raise InvalidValidityPeriod(
                f"a period cannot end ({self.valid_to}) before it begins ({self.valid_from})"
            )

    def contains(self, day: date) -> bool:
        return self.valid_from <= day <= self.valid_to

    def __contains__(self, day: date) -> bool:
        return self.contains(day)

    def __str__(self) -> str:
        from app.i18n import short_date

        return f"{short_date(self.valid_from)} – {short_date(self.valid_to)}"

    def __repr__(self) -> str:
        return f"ValidityPeriod({self.valid_from.isoformat()}, {self.valid_to.isoformat()})"
