"""#668/#669 — het openstaand-filter.

**#668 is een tekenfout met geld erachter.** De vergelijking was

    (amount - amount_paid) > drempel

en die gaat uit van één richting. Bij een vordering is `amount` positief, dus wat
openstaat is positief. Bij een terugbetaling is `amount` NEGATIEF: een openstaande
refund van 10 gaf -10, kleiner dan de drempel, en verdween. Op HDEV toonde het
filter 28 records waar er 42 hoorden te staan — veertien onzichtbare openstaande
terugbetalingen, geld dat de vereniging nog moet uitbetalen.

`abs()` is hier niet ruwer maar preciezer, en haalt een tweede geval boven: een
TE VEEL betaalde vordering heeft ook een negatief verschil en was even onzichtbaar
terwijl die net actie vraagt.

**#669** splitst de twee soorten predicaat die in één keuzelijst stonden: de
statuskolom (pending/paid/failed/cancelled) en de afgeleide toestand
(amount != amount_paid). Ze combineren nu met EN.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domains.payment.service import matches_filter

pytestmark = pytest.mark.ui_agnostisch


def _rec(**kw):
    """Een record met net genoeg velden voor matches_filter."""
    basis = dict(payable_type="registration", payable_id=1, type="charge",
                 status="pending", amount=Decimal("20.00"), amount_paid=None,
                 contact_name=None, structured_communication=None,
                 description=None, component_name=None,
                 membership_year=None, component_id=None)
    basis.update(kw)
    return SimpleNamespace(**basis)


# (omschrijving, record, hoort erbij)
GEVALLEN = [
    ("openstaande vordering",
     _rec(amount=Decimal("20.00"), amount_paid=None), True),
    ("betaalde vordering",
     _rec(amount=Decimal("20.00"), amount_paid=Decimal("20.00"), status="paid"), False),
    ("openstaande terugbetaling — de bug van #668",
     _rec(type="refund", amount=Decimal("-10.00"), amount_paid=None), True),
    ("deels uitbetaalde terugbetaling",
     _rec(type="refund", amount=Decimal("-10.00"), amount_paid=Decimal("-9.00")), True),
    ("vereffende terugbetaling — mag NIET matchen, anders is abs() te grof",
     _rec(type="refund", amount=Decimal("-10.00"), amount_paid=Decimal("-10.00"),
          status="paid"), False),
    ("te veel betaalde vordering — was even onzichtbaar",
     _rec(amount=Decimal("20.00"), amount_paid=Decimal("25.00"), status="paid"), True),
    ("afrondingsruis is geen openstaand saldo",
     _rec(amount=Decimal("20.00"), amount_paid=Decimal("19.9999")), False),
]


@pytest.mark.parametrize("omschrijving,record,verwacht",
                         GEVALLEN, ids=[g[0] for g in GEVALLEN])
def test_openstaand_kijkt_naar_de_grootte_van_het_saldo(omschrijving, record, verwacht):
    assert matches_filter(record, openstaand=True) is verwacht, omschrijving


def test_de_oude_waarde_blijft_werken():
    """status=openstaand staat in bestaande links en opgeslagen export-URL's."""
    refund = _rec(type="refund", amount=Decimal("-10.00"), amount_paid=None)
    assert matches_filter(refund, status="openstaand") is True


def test_status_all_plus_openstaand_geeft_hetzelfde_als_de_oude_waarde():
    """De herindeling van #669 mag niets verliezen."""
    records = [g[1] for g in GEVALLEN]
    oud = [r for r in records if matches_filter(r, status="openstaand")]
    nieuw = [r for r in records if matches_filter(r, status="all", openstaand=True)]
    assert oud == nieuw


def test_de_twee_predicaten_combineren_met_en():
    """De winst van #669: openstaande posten bínnen een statuskeuze.

    Kon vroeger niet — je koos óf een status óf openstaand.
    """
    mislukt_open = _rec(status="failed", amount=Decimal("20.00"), amount_paid=None)
    mislukt_vereffend = _rec(status="failed", amount=Decimal("20.00"),
                             amount_paid=Decimal("20.00"))
    open_maar_pending = _rec(status="pending", amount=Decimal("20.00"), amount_paid=None)

    assert matches_filter(mislukt_open, status="failed", openstaand=True) is True
    assert matches_filter(mislukt_vereffend, status="failed", openstaand=True) is False
    assert matches_filter(open_maar_pending, status="failed", openstaand=True) is False
    # Zonder de schakelaar blijft de statuskeuze doen wat ze deed.
    assert matches_filter(mislukt_vereffend, status="failed") is True
