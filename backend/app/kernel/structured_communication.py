"""`StructuredCommunication`: the Belgian structured payment reference (CR-13 §B4.7).

*Gestructureerde mededeling* (OGM): twelve digits — ten digits and a two-digit
check, the ten-digit number modulo 97 with 0 written as 97 — shown as
`+++DDD/DDDD/DDDDD+++`. Banks also print it between asterisks.

Until now the codebase could only *make* one (`payment`'s generator, #157);
reading one back — what a treasurer types, what a bank statement shows — and
checking its digits was missing functionality (§B4.7), not a refactor. The
generator now builds this value, so there is one implementation of the check.

`str(ogm)` is the `+++…+++` form, the one a payer copies (§B4.7: a value object
never prints its dataclass in an f-string).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DIGITS = re.compile(r"\d")


class InvalidStructuredCommunication(ValueError):
    """Text that is not a structured communication, or whose check digits fail."""


def _check(base: int) -> int:
    return base % 97 or 97


@dataclass(frozen=True)
class StructuredCommunication:
    """Twelve digits whose last two are the mod-97 check of the first ten."""

    digits: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\d{12}", self.digits):
            raise InvalidStructuredCommunication(
                f"a structured communication has 12 digits, not {self.digits!r}"
            )
        base, check = int(self.digits[:10]), int(self.digits[10:])
        if _check(base) != check:
            raise InvalidStructuredCommunication(
                f"the check digits of {self._formatted()} do not match (expected {_check(base):02d})"
            )

    @classmethod
    def from_base(cls, base: int) -> StructuredCommunication:
        """Build one from a number (a sequence value), kept to ten digits."""
        base10 = base % 10_000_000_000
        return cls(f"{base10:010d}{_check(base10):02d}")

    @classmethod
    def parse(cls, text: str) -> StructuredCommunication:
        """Read `+++123/4567/89002+++`, `***…***`, spaced or bare digits.

        Only the digits count; anything that is not twelve of them, or whose check
        fails, is refused with `InvalidStructuredCommunication`.
        """
        if not isinstance(text, str) or not text.strip():
            raise InvalidStructuredCommunication("an empty structured communication")
        stripped = text.strip()
        if re.search(r"[^\d+*/ .\-]", stripped):
            raise InvalidStructuredCommunication(f"{text!r} holds more than digits and separators")
        return cls("".join(_DIGITS.findall(stripped)))

    @classmethod
    def is_valid(cls, text: str) -> bool:
        try:
            cls.parse(text)
        except InvalidStructuredCommunication:
            return False
        return True

    def _formatted(self) -> str:
        d = self.digits
        return f"+++{d[0:3]}/{d[3:7]}/{d[7:12]}+++"

    def __str__(self) -> str:
        return self._formatted()

    def __repr__(self) -> str:
        return f"StructuredCommunication({self._formatted()!r})"
