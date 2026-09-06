"""#682 — samenhorende betaalrecords lezen als één geheel.

Koen keek naar een inschrijving met drie records: een vordering van 30 (betaald),
een terugvordering van 10 (nog niet uitbetaald) en een bijkomende vordering van 10
(betaald). Drie dingen klopten niet.

**De volgorde stond omgekeerd.** Eén sorteerregel beantwoordde twee verschillende
vragen. Nieuwste-eerst is juist voor een lijst — je wil zien wat er net gebeurd is
— maar fout bínnen een groep, waar de volgorde het verhaal vertelt: eerst de
vordering, dan wat erop volgde. De bijkomende vordering van 10 stond vóór de
oorspronkelijke 30.

**Er stond geen kader om de groep.** De totaalregel zweefde onder de kaarten
zonder dat iets aangaf wélke ze optelt.

**De totaalregel verstopte de terugvordering.** "Bedrag 30,00 · Ontvangen 40,00 ·
Saldo -10,00" is rekenkundig juist, maar "meer ontvangen dan gevorderd" leest als
een fout, en het enige wat nog actie vraagt zat onzichtbaar in het saldo.

Deze tests toetsen **posities ten opzichte van elkaar**, niet aanwezigheid: dat
alle drie de kaarten er staan, gold voordien ook. En ze bewijzen dat de bedragen
ná de herschikking identiek zijn — een presentatiewijziging die stilletjes een
bedrag verschuift is erger dan de verwarring die ze oplost.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domains.payment.api import PaymentRecord, get_records_for
from app.domains.payment.service import group_cards
from tests._invarianten import assert_saldo_klopt

pytestmark = pytest.mark.ui_agnostisch


def _rec(db, payable_id, amount, *, soort="charge", betaald=None, minuten=0,
         refund_of=None):
    rec = PaymentRecord(payable_type="registration", payable_id=payable_id,
                        type=soort, amount=Decimal(amount), method="transfer",
                        status="paid" if betaald else "pending",
                        refund_of_id=refund_of)
    if betaald is not None:
        rec.amount_paid = Decimal(betaald)
    db.add(rec)
    db.flush()
    rec.created_at = datetime.now(timezone.utc) + timedelta(minutes=minuten)
    db.flush()
    return rec


def _koens_geval(db, payable_id):
    """Precies wat Koen zag: 30 betaald, 10 terug te betalen, 10 bijkomend."""
    vordering = _rec(db, payable_id, "30.00", betaald="30.00", minuten=0)
    terug = _rec(db, payable_id, "-10.00", soort="refund", minuten=5,
                 refund_of=vordering.id)
    bijkomend = _rec(db, payable_id, "10.00", betaald="10.00", minuten=9)
    db.commit()
    return vordering, terug, bijkomend


# ── 1. Volgorde ──────────────────────────────────────────────────────────────

def test_binnen_een_groep_staat_de_oudste_vordering_bovenaan(db_session):
    """De positie ten opzichte van elkaar, niet de aanwezigheid."""
    vordering, _terug, bijkomend = _koens_geval(db_session, 6820)

    kaarten = group_cards(get_records_for(db_session, "registration", 6820))[0]["kaarten"]
    ids = [k["charge"].id for k in kaarten]
    assert ids.index(vordering.id) < ids.index(bijkomend.id), (
        "de bijkomende vordering staat vóór de vordering waar ze bij hoort")


def test_tussen_groepen_blijft_de_nieuwste_bovenaan(db_session):
    """De regressie die punt 1 het makkelijkst veroorzaakt.

    Binnen een groep oudste-eerst zetten is één regel; per ongeluk óók de volgorde
    tussen de groepen omdraaien is dezelfde regel op de verkeerde plek. Dan zou de
    lijst stilletjes van nieuwste-eerst naar oudste-eerst kantelen — een verandering
    die niemand vroeg en die op een lijst van honderden records meteen opvalt.
    """
    _rec(db_session, 6821, "20.00", minuten=0)
    _rec(db_session, 6822, "20.00", minuten=30)
    db_session.commit()

    records = (get_records_for(db_session, "registration", 6821)
               + get_records_for(db_session, "registration", 6822))
    groepen = group_cards(records)
    payables = [g["kaarten"][0]["charge"].payable_id for g in groepen]
    assert payables == [6822, 6821], "de nieuwste groep hoort bovenaan de lijst"


def test_de_twee_volgordes_gelden_tegelijk(db_session):
    """Twee groepen, elk met twee vorderingen: nieuwste groep eerst, en bínnen elke
    groep de oudste vordering eerst. Dat de twee regels samen kloppen is het punt —
    apart getoetst zou een implementatie die er één toepast al slagen."""
    oud_a = _rec(db_session, 6823, "10.00", minuten=0)
    nieuw_a = _rec(db_session, 6823, "10.00", minuten=10)
    oud_b = _rec(db_session, 6824, "10.00", minuten=20)
    nieuw_b = _rec(db_session, 6824, "10.00", minuten=30)
    db_session.commit()

    records = (get_records_for(db_session, "registration", 6823)
               + get_records_for(db_session, "registration", 6824))
    groepen = group_cards(records)
    volgorde = [[k["charge"].id for k in g["kaarten"]] for g in groepen]
    assert volgorde == [[oud_b.id, nieuw_b.id], [oud_a.id, nieuw_a.id]]


# ── 2. De eerlijke totaalregel ───────────────────────────────────────────────

def test_de_openstaande_terugvordering_krijgt_een_eigen_term(db_session):
    _vordering, _terug, _bijkomend = _koens_geval(db_session, 6825)

    groep = group_cards(get_records_for(db_session, "registration", 6825))[0]
    assert groep["terug_te_betalen"] == Decimal("10.00")


def test_een_uitbetaalde_terugvordering_staat_er_niet_meer_bij(db_session):
    """Alleen tonen wat nog actie vraagt: anders krijgt elke afgehandelde
    inschrijving een term die niets meer betekent."""
    vordering = _rec(db_session, 6826, "30.00", betaald="30.00", minuten=0)
    _rec(db_session, 6826, "-10.00", soort="refund", betaald="-10.00", minuten=5,
         refund_of=vordering.id)
    db_session.commit()

    groep = group_cards(get_records_for(db_session, "registration", 6826))[0]
    assert groep["terug_te_betalen"] == Decimal("0")


def test_een_gewone_inschrijving_krijgt_geen_lege_kolom(db_session):
    _rec(db_session, 6827, "30.00", betaald="30.00", minuten=0)
    _rec(db_session, 6827, "10.00", betaald="10.00", minuten=5)
    db_session.commit()

    groep = group_cards(get_records_for(db_session, "registration", 6827))[0]
    assert groep["terug_te_betalen"] == Decimal("0")


def test_een_te_veel_ontvangen_bedrag_is_geen_terugvordering(db_session):
    """Waarom dit een ándere grootheid is dan het saldo, en geen tweede som ervan.

    Een inschrijving die per ongeluk te veel betaald kreeg heeft óók een negatief
    saldo, maar er staat geen terugbetaling open. Zou de term uit het saldo
    afgeleid worden, dan beloofde het scherm hier een uitbetaling die nergens
    geregistreerd is.
    """
    _rec(db_session, 6828, "30.00", betaald="40.00", minuten=0)
    _rec(db_session, 6828, "10.00", betaald="10.00", minuten=5)
    db_session.commit()

    groep = group_cards(get_records_for(db_session, "registration", 6828))[0]
    assert groep["totaal"]["saldo"] < 0, "het saldo is negatief"
    assert groep["terug_te_betalen"] == Decimal("0"), (
        "maar er staat geen terugbetaling open")


# ── 3. De bedragen bewegen niet ──────────────────────────────────────────────

def test_de_bedragen_zijn_identiek_na_de_herschikking(db_session):
    """De belangrijkste test van de drie punten samen."""
    _koens_geval(db_session, 6829)

    groep = group_cards(get_records_for(db_session, "registration", 6829))[0]
    assert groep["totaal"]["due"] == Decimal("30.00")
    assert groep["totaal"]["paid"] == Decimal("40.00")
    assert groep["totaal"]["saldo"] == Decimal("-10.00")
    assert_saldo_klopt(db_session, "registration", 6829, Decimal("30.00"))


# ── 4. Wat het scherm ervan toont ────────────────────────────────────────────

def _login(client):
    from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                      make_session_value)
    from tests.conftest import SEEDED_ADMIN_EMAIL

    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_het_scherm_benoemt_wat_er_nog_uitbetaald_moet_worden(client, db_session):
    """De term staat er alleen als er iets openstaat.

    Beide helften horen erbij: dat hij verschijnt bewijst dat de openstaande
    terugvordering niet langer alleen in het saldo zit, en dat hij wégblijft
    bewijst dat een gewone inschrijving geen betekenisloze kolom krijgt.

    De term heette eerst "Terug te betalen", en dat is óók de naam van de
    statusbadge van een refund (`refund_due` in `payment/ui.py`). Deze test moest
    daarom op `"Terug te betalen: €"` zoeken om niet de badge te meten — een
    achtervoegsel dat de assertie overeind hield in plaats van de tekst. Sinds #684
    heet de totaalregel "Nog uit te betalen" en is de naam op zichzelf uniek; de
    valkuil is weg in plaats van omzeild.
    """
    _koens_geval(db_session, 6830)
    _login(client)

    met = client.get("/admin/betalingen?context=all")
    assert met.status_code == 200
    assert "Nog uit te betalen" in met.text

    for rec in get_records_for(db_session, "registration", 6830):
        if rec.type == "refund":
            rec.amount_paid = Decimal("-10.00")
            rec.status = "paid"
    db_session.commit()

    zonder = client.get("/admin/betalingen?context=all")
    assert zonder.status_code == 200
    assert "Nog uit te betalen" not in zonder.text, (
        "een afgehandelde terugbetaling hoort de term niet te laten staan")


def test_de_badge_en_de_totaalregel_zijn_niet_langer_dezelfde_tekst(client, db_session):
    """Het geval dat de verwarring veroorzaakte: één kaart die beide toont.

    De statusbadge benoemt een TOESTAND ("deze terugbetaling moet nog uitbetaald
    worden"), de totaalregel telt een BEDRAG op over de hele inschrijving. Ze
    stonden onder dezelfde naam boven elkaar.

    Elk precies één keer — dat is de assertie. Alleen toetsen dat de nieuwe tekst
    er staat zou ook slagen als de oude naam er nog naast stond.
    """
    _koens_geval(db_session, 6831)
    _login(client)

    html = client.get("/admin/betalingen?context=all").text
    assert html.count("Nog uit te betalen") == 1, "de totaalregel"
    assert html.count(">Terug te betalen<") == 1, "de statusbadge"
