"""A phone number as a person reads it (#1675).

The national member report is imported with every space removed from a number
(`mdm.ledenrapport.clean_phone`): the report is read again and again and
compared with what is stored, and one stored form is what keeps a number from
counting as changed at every import. So "0470 12 34 56" is stored as
"0470123456" — and every screen showed those ten digits in a row, next to a
number a member typed with spaces.

Storage does not change. This is the ONE place that turns a stored number into
its readable form, for every screen (the Jinja filter `phone`), the e-mails and
the Design Studio. A `tel:` link, an export, a report and the comparison at
import keep the stored value: they are data, not reading.

**It never drops or adds a digit.** A value it does not recognise — a foreign
number, a number with an extension, free text, a service number — comes back
exactly as stored. Only the grouping changes, and only for a Belgian number:

    mobile            0470 12 34 56        +32 470 12 34 56
    one-digit zone    03 123 45 67         +32 3 123 45 67     (02, 03, 04, 09)
    two-digit zone    014 12 34 56         +32 14 12 34 56

The international prefix is kept as it was written (`+32` or `0032`): turning
one into the other would change the digits.
"""

from __future__ import annotations

import re

#: What may stand between the digits of a number someone typed.
_SEPARATORS = re.compile(r"[\s./-]+")
_NATIONAL = re.compile(r"^0(\d{8,9})$")
_INTERNATIONAL = re.compile(r"^(\+32|0032)(\d{8,9})$")
#: The zones of one digit after the leading zero: Brussels, Antwerp, Liège, Ghent.
_ONE_DIGIT_ZONES = frozenset("2349")
#: Service numbers (070, 078, 0800, 090x) are grouped their own way and are not
#: a zone: left as stored.
_NO_ZONE = ("70", "78", "80", "90")


def _grouped(rest: str) -> list[str] | None:
    """The groups of a Belgian number without its leading zero or country code,
    or None when it is none."""
    if len(rest) == 9 and rest[0] == "4" and rest[1] in "56789":
        return [rest[:3], rest[3:5], rest[5:7], rest[7:]]  # mobile: 470 12 34 56
    if len(rest) != 8 or rest[0] == "0" or rest.startswith(_NO_ZONE):
        return None
    if rest[0] in _ONE_DIGIT_ZONES:
        return [rest[0], rest[1:4], rest[4:6], rest[6:]]  # 3 123 45 67
    return [rest[:2], rest[2:4], rest[4:6], rest[6:]]  # 14 12 34 56


def readable_phone(value: str | None) -> str:
    """The stored number in its readable form, or the value itself when it is
    no Belgian number this recognises."""
    stored = value or ""
    compact = _SEPARATORS.sub("", stored)
    national = _NATIONAL.match(compact)
    if national:
        groups = _grouped(national.group(1))
        if groups:
            return " ".join(["0" + groups[0], *groups[1:]])
        return stored
    international = _INTERNATIONAL.match(compact)
    if international:
        groups = _grouped(international.group(2))
        if groups:
            return " ".join([international.group(1), *groups])
    return stored
