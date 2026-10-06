"""A phone number is shown readable, by one formatter (#1675).

Two halves:

- the formatter (`app.kernel.phone.readable_phone`): the stored forms, each with
  its readable form; what it does not recognise comes out as stored; the digits
  that go in are the digits that come out;
- a gate over the templates: an expression that SHOWS a number goes through the
  `phone` filter. An input's `value`, a `tel:` address and an argument of a kit
  macro carry the stored value and are exempt — the kit's own `field` formats
  in read mode, and that is one of the guarded places.

The gate proven with an ADDED violation (6 October 2026; nothing that exists was
broken): a line `<p>{{ m.mobile }}</p>` added to `_leden_kaarten.html` → the gate
named that file and that expression; the line taken out → green. It ran: its own
count of guarded places stood in the output of the failing run.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.kernel.phone import readable_phone
from tests._bestanden import bestanden

APP = Path(__file__).resolve().parents[1] / "app"


@pytest.mark.parametrize(
    ("stored", "shown"),
    [
        # mobile: what the import stores, and what people type
        ("0470123456", "0470 12 34 56"),
        ("0470 12 34 56", "0470 12 34 56"),
        ("0470/12.34.56", "0470 12 34 56"),
        ("0470-12-34-56", "0470 12 34 56"),
        ("  0470123456 ", "0470 12 34 56"),
        ("+32470123456", "+32 470 12 34 56"),
        ("+32 470 123 456", "+32 470 12 34 56"),
        # the prefix stays as written: 0032 is not turned into +32
        ("0032470123456", "0032 470 12 34 56"),
        # a landline, grouped by its zone
        ("031234567", "03 123 45 67"),
        ("021234567", "02 123 45 67"),
        ("041234567", "04 123 45 67"),
        ("091234567", "09 123 45 67"),
        ("014123456", "014 12 34 56"),
        ("014/12.34.56", "014 12 34 56"),
        ("+3231234567", "+32 3 123 45 67"),
        ("+3214123456", "+32 14 12 34 56"),
    ],
)
def test_a_belgian_number_reads_in_groups(stored, shown):
    assert readable_phone(stored) == shown


@pytest.mark.parametrize(
    "stored",
    [
        "+31612345678",  # a foreign number
        "0470123456 (na 18u)",  # a number with a note
        "0470123456 ext 12",
        "080012345",  # a service number has its own grouping
        "078151515",
        "0412345678",  # ten digits that are no mobile range
        "04701234",  # too short
        "047012345678",  # too long
        "1234",
        "geen",
        "",
    ],
)
def test_what_is_not_recognised_comes_out_as_stored(stored):
    assert readable_phone(stored) == stored


def test_nothing_is_nothing():
    assert readable_phone(None) == ""


@pytest.mark.parametrize(
    "stored",
    ["0470123456", "+32470123456", "0032470123456", "031234567", "014123456", "+3214123456"],
)
def test_the_digits_in_are_the_digits_out(stored):
    """Only the grouping changes: no digit dropped, added or moved."""
    keep = re.compile(r"[^\d+]")
    assert keep.sub("", readable_phone(stored)) == keep.sub("", stored)
    assert readable_phone(readable_phone(stored)) == readable_phone(stored), "not stable"


# ── The gate ────────────────────────────────────────────────────────────────

_EXPRESSION = re.compile(r"\{\{(.*?)\}\}", re.S)
_STRING = re.compile(r"\"[^\"]*\"|'[^']*'")
#: A name that holds a number: `m.mobile`, `reg.phone`, `_mobile`, `organisatie.phone`.
_NUMBER = re.compile(r"(?<![\w.])(?:\w+\.)*_?(?:mobile|phone)\b(?!\s*[(=])")
_FILTERED = re.compile(r"\|\s*phone\b")


def _scan() -> tuple[list[str], int, int]:
    """(violations, guarded places, exempt places) over every template."""
    violations: list[str] = []
    guarded = exempt = 0
    for path in bestanden(APP.rglob("*.html"), wat="the templates that may show a phone number"):
        text = path.read_text(encoding="utf-8")
        for found in _EXPRESSION.finditer(text):
            expression = found.group(1)
            if _FILTERED.search(expression):
                guarded += 1
                continue
            bare = _STRING.sub('""', expression)
            if not _NUMBER.search(bare):
                continue
            before = text[max(found.start() - 12, 0) : found.start()]
            if bare.lstrip("- ").startswith("ui.") or before.endswith(('value="', "tel:")):
                exempt += 1  # the stored value: a macro's argument, an input, an address
                continue
            line = text.count("\n", 0, found.start()) + 1
            violations.append(f"{path.relative_to(APP)}:{line}: {{{{{expression.strip()[:70]}}}}}")
    return violations, guarded, exempt


def test_no_template_shows_a_number_without_the_formatter():
    violations, guarded, exempt = _scan()
    print(f"GATE phone: {guarded} guarded places, {exempt} exempt (stored value)")
    # A gate that looks for a pattern counts its hits: with none it reads green.
    assert guarded >= 6, f"the gate found only {guarded} places that show a number"
    assert exempt >= 4, f"the gate saw only {exempt} inputs and macro arguments"
    assert violations == [], (
        "A phone number is shown as stored. Show it through the one formatter: "
        "{{ value|phone }} (#1675).\n" + "\n".join(violations)
    )


def test_the_kits_field_formats_a_number_it_shows_and_keeps_it_in_the_input():
    """The kit's `field(kind="phone")` is where Mijn gezin and the member
    record show a number: read, grouped; edited, the stored value."""
    from app.ui import templates

    macros = templates.env.get_template("_macros.html").module
    read = str(macros.field("mobile", "Gsm", kind="phone", value="0470123456", edit=False))
    edit = str(macros.field("mobile", "Gsm", kind="phone", value="0470123456", edit=True))
    assert "0470 12 34 56" in read and "0470123456" not in read
    assert 'value="0470123456"' in edit and "0470 12 34 56" not in edit


def test_the_footer_reads_the_number_and_dials_the_stored_one():
    from app.ui import legal_parts

    parts = legal_parts(
        {"address_lines": [], "email": "", "phone": "0470123456", "iban": "", "bic": ""}
    )
    phone = next(p for p in parts if p["kind"] == "phone")
    assert phone["text"] == "0470 12 34 56"
    assert phone["href"] == "tel:0470123456"
