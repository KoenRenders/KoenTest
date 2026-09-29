"""`Money`: an amount in a currency, as a value (CR-13 §B4.7, R11).

An amount of money has been a bare `Decimal` everywhere — a total, a balance, a
price — and its formatting lived in one function, `kernel/geld.py`'s `bedrag`
(#735). A value object gives it the two things a `Decimal` does not carry: the
currency, and a way to print itself that is the one the screens use.

**Rounding is the one the screens use today, not a new one.** `bedrag` formats
with `f"{value:.2f}"`, and on a `Decimal` that rounds half to even. A report that
shows an average of 12.345 prints `12,34` today; half-up would print `12,35` — a
change nobody asked for (R13). So `Money` keeps two decimals rounded half to
even, and `bedrag` becomes a call to this class instead of a second copy.

**`str(money)` is the amount as the screens show it** (§B4.7, the CR-12 lesson
of #1279): `Money("35")` prints `35,00` — without the euro sign, because the
templates write it themselves. An f-string, a log line or a mail body therefore
gets the amount, never `Money(amount=Decimal('35.00'), currency='EUR')`; that
is what `repr` is for.

Arithmetic stays within one currency: adding euros to another currency is an
error, not a sum.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Union

CENT = Decimal("0.01")
EUR = "EUR"

Number = Union[int, str, Decimal, float]


def _cents(value: Number | None) -> Decimal:
    raw = Decimal(str(value if value is not None else 0))
    return raw.quantize(CENT, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True, order=True)
class Money:
    """An amount rounded to the cent, in one currency (default euro)."""

    amount: Decimal
    currency: str = EUR

    def __init__(self, amount: Number | None = 0, currency: str = EUR) -> None:
        object.__setattr__(self, "amount", _cents(amount))
        object.__setattr__(self, "currency", currency)

    @classmethod
    def zero(cls, currency: str = EUR) -> Money:
        return cls(0, currency)

    def _same_currency(self, other: Money) -> None:
        if not isinstance(other, Money):
            raise TypeError(f"cannot combine Money with {type(other).__name__}")
        if other.currency != self.currency:
            raise ValueError(f"cannot combine {self.currency} with {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: int | Decimal) -> Money:
        if isinstance(factor, (Money, float)):
            raise TypeError("Money is multiplied by a count or a Decimal, not by money or a float")
        return Money(self.amount * factor, self.currency)

    __rmul__ = __mul__

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __bool__(self) -> bool:
        return self.amount != 0

    def __str__(self) -> str:
        """`35,00` — nl-BE notation, the sign kept (a refund shows its minus)."""
        return f"{self.amount:.2f}".replace(".", ",")

    def __repr__(self) -> str:
        return f"Money({str(self.amount)!r}, {self.currency!r})"
