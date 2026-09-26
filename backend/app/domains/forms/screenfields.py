"""The field as a SCREEN needs it: `field_type` as the code (CR-12 phase 4).

`FormField.field_type` carries a `FieldType` member since phase 4, because
twelve places in Python branch on it and an enum is what makes those safe
(§B4.3). A template may not do the same: rendered into an attribute a member
reads `FieldType.RADIO` and equals no code, which the enum guard refuses
outright.

The form renderer is the one screen that legitimately branches on this
vocabulary — it draws a different control per type, so the branch *is* the
feature, and §B5.3 does not ask for those template comparisons to go. What it
needs is the code, and this adapter is the boundary that hands it over
(§B4.7): everything else passes straight through to the row.

One adapter rather than a copy per template: the four templates that render a
field read a dozen of its attributes, and listing them here would be a second
place to forget one.
"""
from __future__ import annotations

from typing import Any

from app.kernel.codes import code_of


class ScreenField:
    """A `FormField` with its `field_type` as the stored code."""

    __slots__ = ("_field",)

    def __init__(self, field: Any) -> None:
        object.__setattr__(self, "_field", field)

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_field"), name)

    @property
    def field_type(self) -> str:
        return code_of(object.__getattribute__(self, "_field").field_type) or ""

    @property
    def row(self) -> Any:
        """The row itself, for code that needs the member after all."""
        return object.__getattribute__(self, "_field")


def screen_fields(fields: Any) -> list[ScreenField]:
    return [ScreenField(v) for v in fields]
