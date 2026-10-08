"""#1241 — het te betalen bedrag staat in Belgische notatie op het gezinsportaal.

Since #1590 the two blocks stand on the renewal page (`/leden/gezin/vernieuwen`,
`_renewal_running.html`), no longer on Mijn gezin itself.

Gezien op de schermafdruk van de betaalinstructies: er stond **€ 20.00**, met een punt.
Dat is het beeld dat een lid moet vertellen wélk bedrag het moet overschrijven, en een
punt op een Belgische betaalinstructie is de laatste plek waar je twijfel wil. Het
`geld`-filter (#735) bestaat al en wordt elders gebruikt; deze twee regels drukten de
rauwe `Decimal` af.

**Twee takken, twee tests, en de tweede staat op geen enkele afdruk.** Het blok voor een
online betaling die nog niet afgerond is (#618-3) komt in de reeks niet voor. Hem
overslaan zou precies de tweede plek zijn die achterblijft — en dan staat er over een
half jaar weer één van de twee verkeerd, zonder dat iemand het merkt.

De browserkant van de overschrijvingstak staat in
`tests_e2e/test_verlengflow_schermen.py`; hier wordt de opmaak zelf getoetst, want die
is niet van het scherm maar van de sjabloon.

Rood te maken door het filter van één van beide regels te halen: dan staat er `20.00` en
faalt die test op de punt.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

LID = "vernieuwer@example.com"
BEDRAG = Decimal("20.00")
BELGISCH = "20,00"
AMERIKAANS = "20.00"


def _gezin_met_lopende_vernieuwing(db, method: str):
    """Een gezin waarvan de vernieuwing loopt: dekking dit jaar, betaling open.

    `open_renewal_payment` zoekt een membership-betaling van dit gezin die niet betaald,
    geannuleerd of mislukt is, en `_lopende_vernieuwing` kiest daarna op `method` welk
    van de twee blokken het portaal toont. Vandaar dezelfde opbouw met één verschil.
    """
    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord

    member, person = create_test_family(db, email=LID)
    jaar = date.today().year
    db.add(
        Membership(
            member_id=member.id,
            year=jaar,
            is_active=True,
            valid_from=date(jaar, 1, 1),
            valid_to=date(jaar, 12, 31),
        )
    )
    vernieuwing = Membership(
        member_id=member.id,
        year=jaar + 1,
        is_active=False,
        valid_from=date(jaar + 1, 1, 1),
        valid_to=date(jaar + 1, 12, 31),
    )
    db.add(vernieuwing)
    db.flush()
    db.add(
        PaymentRecord(
            payable_type="membership",
            payable_id=vernieuwing.id,
            type="charge",
            amount=BEDRAG,
            method=method,
            status="pending",
            structured_communication="+++000/0000/55532+++",
        )
    )
    db.commit()
    return person


def _portaal(client, db, method: str) -> str:
    _gezin_met_lopende_vernieuwing(db, method)
    client.cookies.set(SESSION_COOKIE, make_session_value(LID))
    resp = client.get("/leden/gezin/vernieuwen")
    assert resp.status_code == 200, f"/leden/gezin/vernieuwen → {resp.status_code}"
    return resp.text


def test_de_overschrijving_toont_het_bedrag_met_een_komma(client, db_session):
    html = _portaal(client, db_session, "transfer")
    assert "Lidmaatschap geregistreerd" in html, (
        "het blok met de betaalinstructies staat er niet; deze test meet dan niets"
    )
    assert BELGISCH in html, f"geen {BELGISCH} op het scherm"
    assert AMERIKAANS not in html, (
        f"het bedrag staat er (ook) als {AMERIKAANS} — een punt op een Belgische betaalinstructie"
    )


def test_de_lopende_online_betaling_toont_het_bedrag_met_een_komma(client, db_session):
    """De tak die op geen enkele afdruk staat, en juist daarom hier."""
    html = _portaal(client, db_session, "online")
    assert "Je betaling loopt nog" in html, (
        "het blok voor een niet-afgeronde online betaling staat er niet; deze test meet dan niets"
    )
    assert BELGISCH in html, f"geen {BELGISCH} op het scherm"
    assert AMERIKAANS not in html, f"het bedrag staat er (ook) als {AMERIKAANS}"
