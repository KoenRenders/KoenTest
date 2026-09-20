"""*Openstaand* als rapportageobject: saldo, niet status (#1078).

Het betalingenscherm heeft een tab *Openstaand* en bepaalt die met het **saldo**
(`bedrag − betaald > 0`, per record). De rapportering kende dat begrip niet: van
`f_payments` waren alleen status, type, soort en ouderdom filterbaar, en de
ouderdomsklasse staat op *Betaald* zodra de STATUS `paid` is — niet zodra er niets
meer openstaat.

**Dat die twee uiteenlopen is gemeten op PROD**, niet geredeneerd: van 95 rijen is
er één volledig vereffend terwijl de status dat niet zegt. Het scherm laat die
buiten *Openstaand*, de ouderdomsklasse rekent ze erin. Eén rij op 95 — en precies
daarom bouwt deze test het onderscheidende geval zélf: een testdatabank die het
toevallig niet heeft, laat elke tegenproef groen.

**Twee metingen bepalen wat hier staat, en ze zijn allebei duur geleerd.**

*Eén: het saldo is ABSOLUUT.* De eerste versie van dit object gebruikte
`open_amount > 0`. Het scherm gebruikt `saldo_open`, en dat rekent op
`abs(bedrag − betaald)` — met de reden erbij: een terugbetaling draagt een
NEGATIEF bedrag, dus de eenrichtingsvergelijking liet veertien openstaande
refunds en élke te veel betaalde vordering uit het filter vallen (#668, al
gerepareerd op het scherm). Het object herhaalde die bug dus. Op PROD gemeten:
6 rijen met een positief saldo, **1 met een negatief**, 88 vereffend — die ene
zou als *Nee* geteld zijn waar het scherm *Ja* zegt.

*Twee: de eerste tegenproef was te zwak.* Die haalde de saldo-regel weg en
verving hem door de status. Dat bewees dat dit object de júiste kolom leest, niet
dat het er de juiste vraag aan stelt. Vandaar dat de testdata nu óók een
openstaande terugbetaling en een overbetaling draagt, en dat de tegenproef
(de `ABS` weghalen) **beide** moet laten omvallen — valt er maar één om, dan
dekt de data het andere geval niet.

Vier rijen dragen de hele test — twee aan weerszijden van het status-verschil, en
twee met een negatief saldo:

* **status `paid`, toch een rest open** (20,00 waarvan 15,00 betaald) — het scherm
  zegt *openstaand*, de ouderdomsklasse zegt *Betaald*;
* **status `pending`, toch helemaal vereffend** (10,00 waarvan 10,00 betaald) — het
  scherm zegt *niet openstaand*, de ouderdomsklasse zegt van wel. Dit is de rij die
  op PROD écht bestaat.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden — twee keer,
want de eerste ingreep alleen was niet genoeg (gemeten):

* de `sql` op `age_bucket` laten steunen in plaats van op het saldo → de twee
  status-rijen vallen om, elk aan hun eigen kant, en de vergelijking met het
  scherm ook. Dit bewijst dat saldo ≠ status;
* de `ABS` weghalen → de melding noemt **beide** negatieve rijen in één keer:
  `['open_refund', 'te_veel_betaald']`. Dit bewijst dat de formule zelf klopt, en
  dát is wat de eerste ingreep niet toetste.

De asserties verzamelen daarom álle ontbrekende gevallen vóór ze falen. Een lus
vol losse asserts laat de eerste de tweede verbergen, en dan lijkt één ongedekt
geval er één terwijl het er twee zijn.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.domains.payment.api import PaymentRecord
from app.domains.reporting.api import BY_KEY, Filter, Operator, Selection, run_validated

TENANT = 7788


@pytest.fixture
def twee_kanten(db_session):
    """Vier rijen: twee waar scherm en status uit elkaar lopen, en twee met een
    NEGATIEF saldo — de gevallen van #668."""
    from datetime import timedelta, timezone, datetime

    nu = datetime.now(timezone.utc)
    rest_open = PaymentRecord(
        tenant_id=TENANT, payable_type="registration", payable_id=5001,
        amount=Decimal("20.00"), amount_paid=Decimal("15.00"),
        method="transfer", status="paid", type="charge",
        created_at=nu - timedelta(days=10), paid_at=nu - timedelta(days=5))
    vereffend = PaymentRecord(
        tenant_id=TENANT, payable_type="registration", payable_id=5002,
        amount=Decimal("10.00"), amount_paid=Decimal("10.00"),
        method="transfer", status="pending", type="charge",
        created_at=nu - timedelta(days=10))
    # #668: een terugbetaling draagt een NEGATIEF bedrag, en een te veel betaalde
    # vordering levert eveneens een negatief saldo. Het scherm rekent daarom op de
    # ABSOLUTE waarde; een eenrichtingsvergelijking laat allebei uit het filter
    # vallen — veertien openstaande refunds destijds. Zonder deze twee rijen meet
    # deze test alleen het makkelijke geval, en dat is precies wat er misging.
    open_refund = PaymentRecord(
        tenant_id=TENANT, payable_type="registration", payable_id=5003,
        amount=Decimal("-5.00"), amount_paid=None,
        method="transfer", status="pending", type="refund",
        created_at=nu - timedelta(days=10))
    te_veel_betaald = PaymentRecord(
        tenant_id=TENANT, payable_type="registration", payable_id=5004,
        amount=Decimal("10.00"), amount_paid=Decimal("12.00"),
        method="transfer", status="paid", type="charge",
        created_at=nu - timedelta(days=10), paid_at=nu - timedelta(days=5))
    db_session.add_all([rest_open, vereffend, open_refund, te_veel_betaald])
    db_session.commit()
    return {"rest_open": rest_open, "vereffend": vereffend,
            "open_refund": open_refund, "te_veel_betaald": te_veel_betaald}


def _openstaand(db, waarde: str) -> list[str]:
    """De betaal-id's die de rapportering onder *Openstaand = waarde* zet."""
    resultaat = run_validated(
        db,
        Selection(object_keys=("payment_record", "payment_count"),
                  filters=(Filter(object_key="payment_open",
                                  operator=Operator.EQ, values=(waarde,)),)),
        tenant_id=TENANT)
    return sorted(str(r["payment_record"]) for r in resultaat.rows)


def test_het_object_volgt_het_saldo_en_niet_de_status(db_session, twee_kanten):
    """Toets 1: dezelfde verzameling als het tab *Openstaand*.

    Beide rijen staan aan de kant waar het SCHERM ze zet, en beide zouden aan de
    andere kant staan als het object op de status of op de ouderdomsklasse steunde.
    """
    ja = set(_openstaand(db_session, "Ja"))
    nee = set(_openstaand(db_session, "Nee"))

    # ALLE ontbrekende gevallen in één melding, niet de eerste de beste: valt de
    # tegenproef om, dan moet ze zeggen wélke gevallen niet gedekt zijn. Met een
    # lus vol asserts verbergt de eerste de tweede, en dan lijkt één ongedekt geval
    # er één — terwijl het er twee zijn.
    ontbreekt = [naam for naam in ("rest_open", "open_refund", "te_veel_betaald")
                 if str(twee_kanten[naam].id) not in ja]
    assert not ontbreekt, f"horen bij Openstaand = Ja maar staan er niet: {ontbreekt}"
    assert str(twee_kanten["vereffend"].id) in nee, "vereffend hoort bij Nee"
    # En niets méér dan die vier: een object dat altijd Ja zegt, klopt hierboven.
    assert len(ja) == 3 and len(nee) == 1


def test_de_rapportering_zegt_hetzelfde_als_het_scherm(db_session, twee_kanten):
    """Dezelfde vraag langs de twee wegen, en ze moeten hetzelfde antwoorden.

    Het scherm gebruikt `matches_zicht(record, "openstaand")`; de rapportering het
    nieuwe object. Zonder deze test zou het object kunnen kloppen met zichzelf en
    tóch iets anders tonen dan de lijst waar het naar verwijst.
    """
    from app.domains.payment.api import enriched_records
    # `matches_zicht` staat niet op de facade — die exporteert `apply_zicht` voor
    # het scherm. Voor een vergelijking rij per rij is de regel zelf nodig; de
    # laaggate geldt voor productiecode.
    from app.domains.payment.service import matches_zicht

    ja = set(_openstaand(db_session, "Ja"))
    ids = {str(k.id) for k in twee_kanten.values()}
    op_het_scherm = {str(r.id) for r in enriched_records(db_session)
                     if str(r.id) in ids and matches_zicht(r, "openstaand")}

    assert ja == op_het_scherm


def test_het_object_staat_in_de_catalogus_en_is_bruikbaar(db_session, twee_kanten):
    """Toets 3: vindbaar, met zijn omschrijving, filterbaar én groepeerbaar."""
    from app.domains.reporting.assistant import render_catalogue

    obj = BY_KEY["payment_open"]
    # De verduidelijking tussen haakjes is de huisvorm van dit universum — zeven
    # objecten dragen er al een (*Gemeente (adres)*, *Aantal leden (personen)*, …) —
    # en ze is hier nodig omdat "Openstaand" in deze klasse al het BEDRAG is.
    # Zonder haakjes slaat de poort op dubbele namen binnen een klasse aan
    # (`test_reporting_universe_gate.py`): dat is de fout van #871, waar twee
    # objecten *Soort* heetten.
    assert obj.name == "Openstaand (ja/nee)" and obj.klass == "Betalingen"
    assert not obj.is_measure, "een dimensie, anders kan je er niet op filteren"
    assert "saldo" in obj.description.lower()

    catalogus = render_catalogue()
    assert "payment_open" in catalogus and "Openstaand (ja/nee)" in catalogus

    # Groeperen: twee groepen, elk één rij — de waarden zijn Ja en Nee en niets anders.
    resultaat = run_validated(
        db_session,
        Selection(object_keys=("payment_open", "payment_count")),
        tenant_id=TENANT)
    assert {r["payment_open"] for r in resultaat.rows} == {"Ja", "Nee"}
