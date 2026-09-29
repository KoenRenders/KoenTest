"""CR-13 B8 test 6: the value objects, without a database, exhaustive at the edges.

`Money`, `StructuredCommunication` and `ValidityPeriod` (`app/kernel/`) run in
parallel with phase 1 (§B4.7): no schema, no session. Each prints itself on
purpose — a value object in an f-string, a log line or a mail body shows its
meaning, never its dataclass (§B4.7, the CR-12 lesson of #1279) — and a test
below holds each to that.

The two functions they absorbed keep answering exactly as before:
`kernel.geld.bedrag` (#735) here, and `payment`'s `generate_structured_communication`
(#157) in its own test — each compared against the old formula, not against itself.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.kernel.geld import bedrag
from app.kernel.money import Money
from app.kernel.structured_communication import (
    InvalidStructuredCommunication,
    StructuredCommunication,
)
from app.kernel.validity_period import InvalidValidityPeriod, ValidityPeriod

pytestmark = pytest.mark.ui_agnostisch


# ── Money ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        (0, "0,00"),
        (None, "0,00"),
        (35, "35,00"),
        ("12.5", "12,50"),
        (Decimal("1342.00"), "1342,00"),
        (Decimal("-7.50"), "-7,50"),
        # Half to even, the rounding `f"{:.2f}"` did before (R13).
        (Decimal("12.345"), "12,34"),
        (Decimal("12.355"), "12,36"),
        (Decimal("0.005"), "0,00"),
        (Decimal("0.015"), "0,02"),
    ],
)
def test_money_prints_as_the_screens_did(value, shown):
    assert str(Money(value)) == shown
    assert f"{Money(value)}" == shown
    old = f"{Decimal(str(value if value is not None else 0)):.2f}".replace(".", ",")
    assert bedrag(value) == old == shown


def test_money_arithmetic_stays_in_one_currency():
    assert Money("10.00") + Money("2.50") == Money("12.50")
    assert Money("10.00") - Money("12.50") == Money("-2.50")
    assert Money("12.50") * 2 == Money("25.00")
    assert 3 * Money("5") == Money("15")
    assert -Money("3") == Money("-3")
    assert not Money(0) and Money("0.01")
    assert Money("1") < Money("2")
    with pytest.raises(ValueError, match="EUR with USD"):
        Money(1) + Money(1, "USD")
    with pytest.raises(TypeError):
        Money(1) + Decimal("1")
    with pytest.raises(TypeError):
        Money(1) * 1.5


def test_money_repr_is_for_debugging():
    assert repr(Money("3.1")) == "Money('3.10', 'EUR')"


# ── StructuredCommunication ──────────────────────────────────────────────────


def _old_generator(base: int) -> str:
    """#157's formula, copied here as the reference the value object must match."""
    base10 = base % 10_000_000_000
    check = base10 % 97 or 97
    digits = f"{base10:010d}{check:02d}"
    return f"+++{digits[0:3]}/{digits[3:7]}/{digits[7:12]}+++"


@pytest.mark.parametrize("base", [0, 1, 96, 97, 98, 194, 9_999_999_999, 10_000_000_001, 123_456])
def test_structured_communication_is_built_as_before(base):
    ogm = StructuredCommunication.from_base(base)
    assert str(ogm) == _old_generator(base)
    # And it reads back.
    assert StructuredCommunication.parse(str(ogm)) == ogm


def test_the_check_of_a_multiple_of_97_is_97():
    assert str(StructuredCommunication.from_base(97)) == "+++000/0000/09797+++"
    assert str(StructuredCommunication.from_base(0)) == "+++000/0000/00097+++"


@pytest.mark.parametrize(
    "text",
    ["+++000/0001/23456+++", "***000/0001/23456***", "000 0001 23456", "000000123456"],
)
def test_structured_communication_parses_the_forms_a_bank_prints(text):
    valid = str(StructuredCommunication.from_base(1234))
    digits = "".join(ch for ch in valid if ch.isdigit())
    shaped = text.replace("000000123456", digits)
    shaped = shaped.replace("000/0001/23456", f"{digits[:3]}/{digits[3:7]}/{digits[7:]}")
    shaped = shaped.replace("000 0001 23456", f"{digits[:3]} {digits[3:7]} {digits[7:]}")
    assert str(StructuredCommunication.parse(shaped)) == valid


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("+++000/0001/23400+++", "check digits"),
        ("12345678901", "12 digits"),
        ("1234567890123", "12 digits"),
        ("+++abc/defg/hijkl+++", "more than digits"),
    ],
)
def test_structured_communication_refuses(text, reason):
    with pytest.raises(InvalidStructuredCommunication, match=reason):
        StructuredCommunication.parse(text)
    assert not StructuredCommunication.is_valid(text)


def test_structured_communication_prints_its_plus_form():
    ogm = StructuredCommunication.from_base(5)
    assert f"{ogm}" == "+++000/0000/00505+++"
    assert repr(ogm) == "StructuredCommunication('+++000/0000/00505+++')"


# ── ValidityPeriod ───────────────────────────────────────────────────────────


def test_a_period_contains_both_its_ends():
    period = ValidityPeriod(date(2026, 1, 1), date(2026, 12, 31))
    assert period.contains(date(2026, 1, 1))
    assert period.contains(date(2026, 12, 31))
    assert date(2026, 6, 15) in period
    assert not period.contains(date(2025, 12, 31))
    assert not period.contains(date(2027, 1, 1))


def test_a_one_day_period_is_allowed_and_a_reversed_one_is_not():
    day = date(2026, 5, 5)
    assert ValidityPeriod(day, day).contains(day)
    with pytest.raises(InvalidValidityPeriod, match="cannot end"):
        ValidityPeriod(date(2026, 5, 6), day)


def test_a_period_prints_in_the_screens_short_date():
    period = ValidityPeriod(date(2026, 1, 1), date(2026, 12, 31))
    assert f"{period}" == "01-01-2026 – 31-12-2026"
    assert repr(period) == "ValidityPeriod(2026-01-01, 2026-12-31)"


# ── Every value object prints on purpose ─────────────────────────────────────


@pytest.mark.parametrize("cls", [Money, StructuredCommunication, ValidityPeriod])
def test_every_value_object_defines_its_own_str_and_repr(cls):
    """§B4.7: a value object without an explicit `__str__` is a test failure."""
    assert "__str__" in vars(cls), f"{cls.__name__} prints its dataclass in an f-string"
    assert "__repr__" in vars(cls), f"{cls.__name__} has no repr of its own"
