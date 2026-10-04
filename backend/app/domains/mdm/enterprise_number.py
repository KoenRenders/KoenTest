"""`EnterpriseNumber`: a Belgian enterprise number (#1517).

*Ondernemingsnummer* (KBO/BCE): ten digits, the first a 0 or a 1, and the last
two a check — 97 minus the first eight modulo 97. It identifies a party in the
scheme ISO 6523 ICD 0208, whose value is exactly those ten digits; that is the
form stored (`organization_identifications`, scheme KBO, #924). People write it
as `0123.456.789`, `0123 456 789`, `0123456789` or, as a VAT number,
`BE0123456789`; all are read. An old nine-digit number (before the leading digit
existed) is read with its 0 in front, as KBO itself did.

`str(number)` is the dotted form people read, `0123.456.789`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class InvalidEnterpriseNumber(ValueError):
    """Text that is not an enterprise number, or whose check digits fail."""


class WrongCheckDigits(InvalidEnterpriseNumber):
    """Ten digits in the right shape, whose last two do not check the first eight —
    a typing error, told apart so the screen can say which."""


def _check(first_eight: int) -> int:
    return 97 - first_eight % 97


@dataclass(frozen=True)
class EnterpriseNumber:
    """Ten digits, starting with 0 or 1, whose last two check the first eight."""

    digits: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[01]\d{9}", self.digits):
            raise InvalidEnterpriseNumber(
                f"an enterprise number has ten digits starting with 0 or 1, not {self.digits!r}"
            )
        if _check(int(self.digits[:8])) != int(self.digits[8:]):
            raise WrongCheckDigits(f"the check digits of {self} do not match")

    @classmethod
    def parse(cls, text: str) -> EnterpriseNumber:
        """Read any usual spelling; refuse anything else with `InvalidEnterpriseNumber`.

        A leading `BE` (a VAT number) is dropped, then spaces, dots and dashes;
        what remains must be digits only — a letter elsewhere is not a spelling.
        """
        bare = re.sub(r"[\s.\-]", "", (text or "").strip())
        if bare[:2].upper() == "BE":
            bare = bare[2:]
        if not bare.isdigit():
            raise InvalidEnterpriseNumber(f"not an enterprise number: {text!r}")
        if len(bare) == 9:
            bare = "0" + bare
        return cls(bare)

    def __str__(self) -> str:
        return f"{self.digits[:4]}.{self.digits[4:7]}.{self.digits[7:]}"
