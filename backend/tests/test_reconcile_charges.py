"""Reconciliatie van betalingen bij een gewijzigde of geschrapte payable (#619).

Twee flows, één definitie: `reconcile_charges` herrekent de records van een payable
naar een nieuw totaal. Bij activiteiten volgde de financiële kant een bestelwijziging
al (#185/#195); bij lidmaatschappen gebeurde er niets, waardoor een geschrapt
lidmaatschap ofwel een eeuwige vordering achterliet ofwel een betaling zonder
terugbetaling.

**Bevinding die dit bestand rechtvaardigt:** geen enkele test noemde
`reconcile_registration_charges`. De reconciliatie die we hier hergebruiken was dus
zélf niet afgedekt. De A-gevallen zijn daarmee ook de regressiebescherming voor de
activiteiten die er nog niet was.
"""
from datetime import date
from decimal import Decimal

from app.domains.membership.api import Membership
from app.domains.payment.api import (
    PaymentRecord, PaymentRecordHistory, get_records_for, reconcile_charges,
    reconcile_registration_charges,
)
from app.domains.payment.handlers import find_orphan_records
from tests.conftest import (create_test_family, create_test_member,
                            seed_activity_with_product)


# ── De invariant die in élk geval geldt ──────────────────────────────────────

def _controleer_invariant(db, payable_type, payable_id, verwacht_totaal):
    """Som van alle niet-verwijderde records == het nieuwe totaal, en nooit een
    openstaande post náást een terugbetaling."""
    records = get_records_for(db, payable_type, payable_id)
    som = sum((Decimal(str(r.amount)) for r in records), Decimal("0"))
    assert som == Decimal(str(verwacht_totaal)), \
        f"som {som} != {verwacht_totaal} voor {payable_type}/{payable_id}"

    open_posten = [r for r in records if r.amount_paid is None and r.type == "charge"]
    refunds = [r for r in records if r.type == "refund"]
    assert not (open_posten and refunds), \
        "openstaande post naast een terugbetaling — dat is nooit een geldige stand"
    return records


def _charge(db, payable_type, payable_id, amount, amount_paid=None, method="transfer"):
    rec = PaymentRecord(
        payable_type=payable_type, payable_id=payable_id, type="charge",
        amount=Decimal(amount),
        amount_paid=Decimal(amount_paid) if amount_paid is not None else None,
        method=method, status="paid" if amount_paid is not None else "pending")
    db.add(rec)
    db.flush()
    return rec


# ── A. Activiteiten — bestelwijziging ───────────────────────────────────────

def test_A1_onbetaald_verlaagd_geeft_een_nieuwe_open_post(db_session):
    _charge(db_session, "registration", 101, "25.00")
    reconcile_charges(db_session, "registration", 101, Decimal("15.00"))

    records = _controleer_invariant(db_session, "registration", 101, "15.00")
    assert len(records) == 1
    assert records[0].amount_paid is None
    assert records[0].structured_communication  # OGM voor de overschrijving


def test_A2_onbetaald_naar_nul_laat_niets_achter(db_session):
    _charge(db_session, "registration", 102, "25.00")
    reconcile_charges(db_session, "registration", 102, 0)

    assert _controleer_invariant(db_session, "registration", 102, "0") == []


def test_A3_betaald_verlaagd_geeft_een_pending_terugbetaling(db_session):
    _charge(db_session, "registration", 103, "25.00", amount_paid="25.00")
    reconcile_charges(db_session, "registration", 103, Decimal("15.00"))

    records = _controleer_invariant(db_session, "registration", 103, "15.00")
    refunds = [r for r in records if r.type == "refund"]
    assert len(refunds) == 1
    assert refunds[0].amount == Decimal("-10.00")
    assert refunds[0].status == "pending", "de uitbetaling blijft mensenwerk"


def test_A4_online_betaald_krijgt_een_transfer_terugbetaling(db_session):
    charge = _charge(db_session, "registration", 104, "25.00", amount_paid="25.00",
                     method="online")
    reconcile_charges(db_session, "registration", 104, Decimal("10.00"))

    refunds = [r for r in get_records_for(db_session, "registration", 104)
               if r.type == "refund"]
    assert len(refunds) == 1
    assert refunds[0].refund_of_id == charge.id
    assert refunds[0].method == "transfer", "terugstorten is mensenwerk, niet via Mollie"


def test_A5_deels_betaald_sluit_de_charge_op_het_ontvangene(db_session):
    charge = _charge(db_session, "registration", 105, "25.00", amount_paid="10.00")
    reconcile_charges(db_session, "registration", 105, Decimal("8.00"))

    db_session.refresh(charge)
    assert charge.amount == Decimal("10.00"), "de charge sluit op wat effectief betaald is"
    records = _controleer_invariant(db_session, "registration", 105, "8.00")
    refunds = [r for r in records if r.type == "refund"]
    assert len(refunds) == 1 and refunds[0].amount == Decimal("-2.00")


def test_A6_verhoging_geeft_een_open_post_geen_terugbetaling(db_session):
    _charge(db_session, "registration", 106, "25.00", amount_paid="25.00")
    reconcile_charges(db_session, "registration", 106, Decimal("40.00"))

    records = _controleer_invariant(db_session, "registration", 106, "40.00")
    assert not [r for r in records if r.type == "refund"]
    open_posten = [r for r in records if r.amount_paid is None]
    assert len(open_posten) == 1 and open_posten[0].amount == Decimal("15.00")


def test_A7_schrappen_en_weer_toevoegen_komt_terug_op_de_beginstand(db_session):
    _charge(db_session, "registration", 107, "25.00", amount_paid="25.00")
    reconcile_charges(db_session, "registration", 107, Decimal("15.00"))
    reconcile_charges(db_session, "registration", 107, Decimal("25.00"))

    records = _controleer_invariant(db_session, "registration", 107, "25.00")
    assert len(records) == 1, "geen stapel losse records"
    assert records[0].amount_paid == Decimal("25.00")


def test_registratie_variant_gebruikt_hetzelfde_pad(client, db_session):
    """De dunne laag boven reconcile_charges rekent met het echte besteltotaal."""
    activity, comp, product = seed_activity_with_product(db_session, is_free=False)
    resp = client.post(f"/api/v1/activities/{activity.id}/register", json={
        "contact_name": "An", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 2}]})
    assert resp.status_code in (200, 201), resp.text
    from app.domains.activities.api import Registration, compute_registration_total

    reg = db_session.get(Registration, resp.json()["id"])
    reconcile_registration_charges(db_session, reg)
    db_session.flush()
    _controleer_invariant(db_session, "registration", reg.id,
                          compute_registration_total(reg)[0])


# ── B. Lidmaatschap schrappen ───────────────────────────────────────────────

def _lidmaatschap(db, member, jaar=None):
    jaar = jaar or date.today().year
    ms = Membership(member_id=member.id, year=jaar, is_active=True,
                    valid_from=date(jaar, 1, 1), valid_to=date(jaar, 12, 31))
    db.add(ms)
    db.flush()
    return ms


def _schrap(db, ms, actor="admin@example.com"):
    from app.domains.membership.register_router import _reconcile_geschrapt_lidmaatschap
    from app.soft_delete import soft_delete

    soft_delete(ms)
    _reconcile_geschrapt_lidmaatschap(db, ms, actor)
    db.flush()


def test_B1_onbetaalde_vordering_verdwijnt(db_session):
    member = create_test_member(db_session)
    ms = _lidmaatschap(db_session, member)
    _charge(db_session, "membership", ms.id, "35.00")

    _schrap(db_session, ms)
    assert _controleer_invariant(db_session, "membership", ms.id, "0") == []


def test_B2_betaald_lidmaatschap_geeft_een_pending_terugbetaling(db_session):
    member = create_test_member(db_session)
    ms = _lidmaatschap(db_session, member)
    _charge(db_session, "membership", ms.id, "35.00", amount_paid="35.00")

    _schrap(db_session, ms)

    records = _controleer_invariant(db_session, "membership", ms.id, "0")
    refunds = [r for r in records if r.type == "refund"]
    assert len(refunds) == 1
    assert refunds[0].amount == Decimal("-35.00") and refunds[0].status == "pending"
    assert "schrappen lidmaatschap" in (refunds[0].note or "")


def test_B3_online_betaald_lidmaatschap_idem(db_session):
    member = create_test_member(db_session)
    ms = _lidmaatschap(db_session, member)
    _charge(db_session, "membership", ms.id, "35.00", amount_paid="35.00", method="online")

    _schrap(db_session, ms)

    refunds = [r for r in get_records_for(db_session, "membership", ms.id)
               if r.type == "refund"]
    assert len(refunds) == 1 and refunds[0].method == "transfer"


def test_B4_deels_betaald_lidmaatschap(db_session):
    member = create_test_member(db_session)
    ms = _lidmaatschap(db_session, member)
    charge = _charge(db_session, "membership", ms.id, "35.00", amount_paid="20.00")

    _schrap(db_session, ms)

    db_session.refresh(charge)
    assert charge.amount == Decimal("20.00")
    records = _controleer_invariant(db_session, "membership", ms.id, "0")
    refunds = [r for r in records if r.type == "refund"]
    assert len(refunds) == 1 and refunds[0].amount == Decimal("-20.00")


def test_B5_zonder_betaling_gebeurt_er_niets(db_session):
    """Handmatig ingevoerd lid: geen fout, geen record uit het niets."""
    member = create_test_member(db_session)
    ms = _lidmaatschap(db_session, member)

    _schrap(db_session, ms)
    assert get_records_for(db_session, "membership", ms.id) == []


def test_B6_tweemaal_schrappen_is_idempotent(db_session):
    member = create_test_member(db_session)
    ms = _lidmaatschap(db_session, member)
    _charge(db_session, "membership", ms.id, "35.00", amount_paid="35.00")

    _schrap(db_session, ms)
    _schrap(db_session, ms)

    refunds = [r for r in get_records_for(db_session, "membership", ms.id)
               if r.type == "refund"]
    assert len(refunds) == 1, "geen tweede terugbetaling"


# ── C. Gezin schrappen ──────────────────────────────────────────────────────

def test_C1_twee_betaalde_lidmaatschappen_geven_twee_terugbetalingen(db_session):
    member = create_test_member(db_session)
    jaar = date.today().year
    ms1 = _lidmaatschap(db_session, member, jaar)
    ms2 = _lidmaatschap(db_session, member, jaar + 1)
    c1 = _charge(db_session, "membership", ms1.id, "35.00", amount_paid="35.00")
    c2 = _charge(db_session, "membership", ms2.id, "35.00", amount_paid="35.00")

    for ms in (ms1, ms2):
        _schrap(db_session, ms)

    for ms, charge in ((ms1, c1), (ms2, c2)):
        refunds = [r for r in get_records_for(db_session, "membership", ms.id)
                   if r.type == "refund"]
        assert len(refunds) == 1
        assert refunds[0].refund_of_id == charge.id, "elk aan zijn eigen charge"


def test_C2_betaald_en_onbetaald_naast_elkaar(db_session):
    member = create_test_member(db_session)
    jaar = date.today().year
    betaald = _lidmaatschap(db_session, member, jaar)
    onbetaald = _lidmaatschap(db_session, member, jaar + 1)
    _charge(db_session, "membership", betaald.id, "35.00", amount_paid="35.00")
    _charge(db_session, "membership", onbetaald.id, "35.00")

    for ms in (betaald, onbetaald):
        _schrap(db_session, ms)

    assert len([r for r in get_records_for(db_session, "membership", betaald.id)
                if r.type == "refund"]) == 1
    assert get_records_for(db_session, "membership", onbetaald.id) == []


def test_C3_een_activiteitsinschrijving_blijft_ongemoeid(db_session):
    """Dit issue raakt alleen lidmaatschappen."""
    member = create_test_member(db_session)
    ms = _lidmaatschap(db_session, member)
    _charge(db_session, "membership", ms.id, "35.00", amount_paid="35.00")
    inschrijving = _charge(db_session, "registration", 999, "12.00", amount_paid="12.00")

    _schrap(db_session, ms)

    db_session.refresh(inschrijving)
    assert inschrijving.deleted_at is None
    assert inschrijving.amount == Decimal("12.00")
    assert len(get_records_for(db_session, "registration", 999)) == 1


# ── D. Randen en naburige systemen ──────────────────────────────────────────

def test_D1_er_ontstaan_geen_weesrecords(db_session):
    member = create_test_member(db_session)
    ms = _lidmaatschap(db_session, member)
    _charge(db_session, "membership", ms.id, "35.00", amount_paid="35.00")

    _schrap(db_session, ms)
    db_session.flush()

    wezen = find_orphan_records(db_session)
    assert not [w for w in wezen if w.payable_id == ms.id], \
        "de reconciliatie hoort net géén wezen te maken"


def test_D2_de_audit_historie_legt_elk_geraakt_record_vast(db_session):
    member = create_test_member(db_session)
    ms = _lidmaatschap(db_session, member)
    charge = _charge(db_session, "membership", ms.id, "35.00", amount_paid="20.00")

    _schrap(db_session, ms, actor="penning@example.com")

    snapshots = (db_session.query(PaymentRecordHistory)
                 .filter(PaymentRecordHistory.payment_record_id == charge.id).all())
    assert snapshots, "geen snapshot van de bijgestelde charge"
    assert any(s.actor == "penning@example.com" for s in snapshots)


def test_D3_bevestigde_terugbetaling_brengt_het_saldo_op_nul(db_session):
    member = create_test_member(db_session)
    ms = _lidmaatschap(db_session, member)
    _charge(db_session, "membership", ms.id, "35.00", amount_paid="35.00")
    _schrap(db_session, ms)

    refund = [r for r in get_records_for(db_session, "membership", ms.id)
              if r.type == "refund"][0]
    refund.amount_paid = refund.amount
    refund.status = "paid"
    db_session.flush()

    records = get_records_for(db_session, "membership", ms.id)
    netto = sum((Decimal(str(r.amount_paid or 0)) for r in records), Decimal("0"))
    assert netto == Decimal("0"), "ontvangen − teruggestort = 0"
