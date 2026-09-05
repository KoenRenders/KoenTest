"""#673 — meerdere vorderingen op één inschrijving lezen als één geheel.

Koen had 3x eten (€30) betaald, voegde 1x toe, en zag een kaart "Bedrag: 10,00 —
Openstaand" met daaronder "4x eten — 40,00 — Totaal 40,00". Hij dacht dat de
betaalde 30 opengezet en herschreven was.

Dat was niet zo: de betaalde charge bleef ongemoeid en er kwam een apart record
van 10 bij. **Geen geldbug — het scherm las verkeerd.** Twee vorderingen stonden
als gelijkwaardige losse kaarten naast elkaar, terwijl de totaalregel eronder de
hele inschrijving telde.

De oudste vordering blijft nu de volledige kaart; latere springen in. Dat is
visuele ordening, geen hiërarchie: tussen twee charges bestaat geen `refund_of_id`
— het zijn broers op dezelfde inschrijving, en het scherm markeert dat anders dan
de refund-nesting.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domains.payment.api import PaymentRecord
from app.domains.payment.service import group_cards
from tests._invarianten import assert_saldo_klopt

pytestmark = pytest.mark.ui_agnostisch


def _charge(db, payable_id, amount, *, betaald=None, minuten=0):
    rec = PaymentRecord(payable_type="registration", payable_id=payable_id,
                        amount=Decimal(amount), method="transfer",
                        status="paid" if betaald else "pending")
    if betaald is not None:
        rec.amount_paid = Decimal(betaald)
    db.add(rec)
    db.flush()
    rec.created_at = datetime.now(timezone.utc) + timedelta(minutes=minuten)
    db.flush()
    return rec


def test_de_tweede_vordering_springt_in(db_session):
    """Eén hoofdkaart, één ingesprongen — niet twee gelijkwaardige."""
    eerste = _charge(db_session, 6730, "30.00", betaald="30.00", minuten=0)
    tweede = _charge(db_session, 6730, "10.00", minuten=5)
    db_session.commit()

    groepen = group_cards([eerste, tweede])
    assert len(groepen) == 1
    kaarten = {k["charge"].id: k for k in groepen[0]["kaarten"]}
    assert kaarten[eerste.id]["is_extra"] is False, "de oudste is de hoofdkaart"
    assert kaarten[tweede.id]["is_extra"] is True, "de latere hoort in te springen"


def test_de_oudste_is_de_hoofdkaart_ook_als_ze_later_binnenkomt(db_session):
    """De kaartenlijst staat nieuwste-eerst; welke kaart de hoofdkaart is, hangt
    van de aanmaakdatum af en niet van de volgorde op het scherm."""
    laatste = _charge(db_session, 6731, "10.00", minuten=5)
    oudste = _charge(db_session, 6731, "30.00", betaald="30.00", minuten=0)
    db_session.commit()

    groepen = group_cards([laatste, oudste])
    kaarten = {k["charge"].id: k for k in groepen[0]["kaarten"]}
    assert kaarten[oudste.id]["is_extra"] is False
    assert kaarten[laatste.id]["is_extra"] is True


def test_een_lege_vordering_komt_niet_op_het_scherm(db_session):
    """De valstrik: bij het reconciliëren blijft er soms een charge van 0 staan.

    Ze is chronologisch vaak de EERSTE, dus zonder deze uitzondering wordt een
    kaart van 0,00 de hoofdkaart met de echte bedragen eronder — verwarrender dan
    het probleem dat #673 oplost. Ze kan bovendien nooit betaald worden.
    """
    leeg = _charge(db_session, 6732, "0.00", betaald="0.00", minuten=0)
    echt = _charge(db_session, 6732, "30.00", betaald="30.00", minuten=5)
    db_session.commit()

    groepen = group_cards([leeg, echt])
    ids = [k["charge"].id for k in groepen[0]["kaarten"]]
    assert leeg.id not in ids, "de lege vordering staat nog op het scherm"
    assert ids == [echt.id]
    kaart = groepen[0]["kaarten"][0]
    assert kaart["is_extra"] is False, (
        "de echte vordering hoort de hoofdkaart te zijn, niet een ingesprongen kind")


def test_het_totaal_verandert_niet_door_de_herindeling(db_session):
    """De belangrijkste test: een visuele herschikking die stilletjes een bedrag
    uit het totaal laat vallen, is erger dan de verwarring die ze oplost."""
    _charge(db_session, 6733, "0.00", betaald="0.00", minuten=0)
    _charge(db_session, 6733, "30.00", betaald="30.00", minuten=5)
    _charge(db_session, 6733, "10.00", minuten=9)
    db_session.commit()

    from app.domains.payment.api import get_records_for
    records = get_records_for(db_session, "registration", 6733)
    groepen = group_cards(records)

    # De ingesprongen vordering telt gewoon mee; de lege draagt 0 bij.
    assert groepen[0]["totaal"]["due"] == Decimal("40.00")
    assert groepen[0]["totaal"]["paid"] == Decimal("30.00")
    assert groepen[0]["totaal"]["saldo"] == Decimal("10.00")
    assert_saldo_klopt(db_session, "registration", 6733, Decimal("40.00"))


def test_een_enkele_vordering_springt_niet_in(db_session):
    """Het gewone geval mag er niet anders uitzien dan voorheen."""
    alleen = _charge(db_session, 6734, "25.00")
    db_session.commit()
    groepen = group_cards([alleen])
    assert groepen[0]["kaarten"][0]["is_extra"] is False
