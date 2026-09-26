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

from app.domains.forms.models import FieldType
from app.kernel.codes import code_of

#: The three choice types, and the two an option can jump from (#336). The
#: service's `KEUZEVELDEN` and `VERTAKBARE_VELDEN` are these, imported: one
#: rule for the screens and the checks.
CHOICES = (FieldType.SELECT, FieldType.RADIO, FieldType.CHECKBOX)
BRANCHABLE = (FieldType.RADIO, FieldType.SELECT)
_SINGLE_LINE = frozenset({FieldType.TEXT, FieldType.EMAIL, FieldType.PHONE})
_INPUT_TYPES = {FieldType.EMAIL: "email", FieldType.PHONE: "tel"}


class FieldKind:
    """What a screen decides from a field's type, decided here (CR-12 phase 4).

    The templates asked `field_type == "radio"` fourteen times across four
    screens. Each of those questions is now a flag with the answer, so no
    template compares a code with a literal and the rule "which types are a
    choice" lives in one place instead of three.
    """

    __slots__ = ("type",)

    def __init__(self, field_type: Any) -> None:
        self.type = FieldType(code_of(field_type))

    is_info = property(lambda self: self.type is FieldType.INFO)
    is_select = property(lambda self: self.type is FieldType.SELECT)
    is_radio = property(lambda self: self.type is FieldType.RADIO)
    is_checkbox = property(lambda self: self.type is FieldType.CHECKBOX)
    is_rating = property(lambda self: self.type is FieldType.RATING)
    is_number = property(lambda self: self.type is FieldType.NUMBER)
    is_textarea = property(lambda self: self.type is FieldType.TEXTAREA)
    #: Any of the three choice types: options, counts per option, "Anders".
    is_choice = property(lambda self: self.type in CHOICES)
    is_branchable = property(lambda self: self.type in BRANCHABLE)
    #: One line of text: `text`, `email` and `phone`.
    is_single_line = property(lambda self: self.type in _SINGLE_LINE)
    #: The builder offers a minimum and maximum length for these.
    has_length_limits = property(
        lambda self: self.type in _SINGLE_LINE or self.type is FieldType.TEXTAREA)
    #: The `type` of the `<input>` for a single-line field.
    input_type = property(lambda self: _INPUT_TYPES.get(self.type, "text"))


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
    def kind(self) -> FieldKind:
        return FieldKind(object.__getattribute__(self, "_field").field_type)

    @property
    def row(self) -> Any:
        """The row itself, for code that needs the member after all."""
        return object.__getattribute__(self, "_field")


def screen_fields(fields: Any) -> list[ScreenField]:
    return [ScreenField(v) for v in fields]
