"""End-to-end interacties tussen bestelwijzigingen en betalingen/refunds (#83+#84).

De invarianten die geld kosten als ze fout lopen: een bestelling verlagen ná
betaling → terugbetaling → saldo settelt; verhogen → saldo blijft openstaan;
en een refund op een lidmaatschap-betaling (niet enkel registratie)."""

from decimal import Decimal

from app.domains.activities import service as activities_service
from app.domains.activities.api import ActivityProduct, Registration, RegistrationItem
from app.domains.mdm.api import Member, PaymentMethod
from app.domains.membership.api import Membership
from app.domains.payment.api import (
    PayableType,
    PaymentRecord,
    PaymentStatus,
    PaymentType,
    registration_balance,
)
from tests import payments_door
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    add_order_line,
    register_at_the_door,
    remove_order_line,
    seed_activity_with_product,
    seed_postal_code,
    sign_up_at_the_door,
)


def _add_product(db, comp, *, name, price, is_free=False):
    p = ActivityProduct(component_id=comp.id, name=name, price=Decimal(str(price)), is_free=is_free)
    db.add(p)
    db.flush()
    return p


def _register(client, db, comp, product, qty=1):
    activity_id = comp.activity_id
    resp = register_at_the_door(
        client,
        activity_id,
        json={
            "contact_name": "An",
            "phone": "0470000000",
            "contact_email": "an@example.com",
            "component_id": comp.id,
            "payment_method": "transfer",
            "items": [{"product_id": product.id, "quantity": qty}],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    reg = (
        db.query(Registration)
        .filter(Registration.component_id == comp.id)
        .order_by(Registration.id.desc())
        .first()
    )
    charge = (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id == reg.id,
            PaymentRecord.type == PaymentType.CHARGE,
        )
        .first()
    )
    return activity_id, reg, charge


def _pay(client, charge_id, amount):
    r = payments_door.update(client, charge_id, {"status": "paid", "amount_paid": str(amount)})
    assert r.status_code == 200, r.text


def _latest_refund(db, reg):
    db.expire_all()
    return (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id == reg.id,
            PaymentRecord.type == PaymentType.REFUND,
        )
        .order_by(PaymentRecord.created_at.desc())
        .first()
    )


def _confirm_refund(client, refund_id):
    """Penningmeester bevestigt de effectieve terugstorting (#216): status → paid
    zonder bedrag, de server vult amount_paid = het volledige (negatieve) refundbedrag."""
    r = payments_door.update(client, refund_id, {"status": "paid"})
    assert r.status_code == 200, r.text


def test_order_lowered_after_payment_creates_pending_refund(client, db_session):
    """#216: een betaalde bestelling verlagen maakt een terugbetaling als *verplichting*
    aan (pending, amount_paid leeg) — niet meteen als teruggestort. Het saldo blijft
    negatief tot de penningmeester de effectieve terugstorting bevestigt."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, charge = _register(
        client, db_session, comp, product, qty=2
    )  # verschuldigd 36
    _pay(client, charge.id, "36.00")

    item = (
        db_session.query(RegistrationItem)
        .filter(RegistrationItem.registration_id == reg.id)
        .first()
    )
    activities_service.update_order_line(
        db_session, activity_id, reg.id, item.id, quantity=1, actor=SEEDED_ADMIN_EMAIL
    )  # verschuldigd zakt naar 18
    balance = registration_balance(db_session, reg)
    # Verplichting, nog niet uitbetaald: saldo blijft −18, niets terugbetaald.
    assert Decimal(str(balance["balance"])) == Decimal("-18.00")
    assert Decimal(str(balance["total_refunded"])) == Decimal("0.00")

    # De refund is automatisch aangemaakt: precies één, dus de penningmeester moet
    # hem bevestigen — niet zelf een tweede registreren (#220 / UI-melding).
    refunds = (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id == reg.id,
            PaymentRecord.type == PaymentType.REFUND,
        )
        .all()
    )
    assert len(refunds) == 1
    refund = refunds[0]
    assert Decimal(str(refund.amount)) == Decimal("-18.00")
    assert refund.status == PaymentStatus.PENDING and refund.amount_paid is None
    assert refund.refund_of_id == charge.id

    # Penningmeester bevestigt de terugstorting → pas nu vereffent het saldo.
    _confirm_refund(client, refund.id)
    bal = payments_door.balance(client, reg.id).json()
    assert Decimal(str(bal["balance"])) == Decimal("0.00")
    assert Decimal(str(bal["total_refunded"])) == Decimal("18.00")


def test_order_decrease_does_not_double_refund(client, db_session):
    """#191: een tweede (no-op) edit maakt geen tweede terugbetaling."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=2)  # 36
    _pay(client, charge.id, "36.00")
    item = (
        db_session.query(RegistrationItem)
        .filter(RegistrationItem.registration_id == reg.id)
        .first()
    )
    for _ in range(2):
        activities_service.update_order_line(
            db_session, activity_id, reg.id, item.id, quantity=1, actor=SEEDED_ADMIN_EMAIL
        )
    db_session.expire_all()
    refunds = (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id == reg.id,
            PaymentRecord.type == PaymentType.REFUND,
        )
        .all()
    )
    assert len(refunds) == 1


def test_order_increased_after_payment_leaves_balance_owed(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="18.00")
    activity_id, reg, charge = _register(
        client, db_session, comp, product, qty=1
    )  # verschuldigd 18
    _pay(client, charge.id, "18.00")

    add_order_line(db_session, activity_id, reg.id, extra.id, 1)  # verschuldigd 36
    balance = registration_balance(db_session, reg)
    assert Decimal(str(balance["total_due"])) == Decimal("36.00")
    assert Decimal(str(balance["balance"])) == Decimal("18.00")  # nog €18 te ontvangen


def _charges(db, reg):
    db.expire_all()
    return (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id == reg.id,
            PaymentRecord.type == PaymentType.CHARGE,
        )
        .all()
    )


def test_order_increase_creates_supplemental_transfer_charge(client, db_session):
    """#185 (C): een bestelregel toevoegen maakt een aanvullende charge voor het
    verschil aan — transfer + pending, met OGM — zodat het saldo in het
    betalingenoverzicht klopt met een eerlijke methode."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="16.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)  # €18
    _pay(client, charge.id, "18.00")

    add_order_line(db_session, activity_id, reg.id, extra.id, 1)  # +€16
    amounts = sorted(Decimal(str(c.amount)) for c in _charges(db_session, reg))
    assert amounts == [Decimal("16.00"), Decimal("18.00")]
    supp = next(c for c in _charges(db_session, reg) if Decimal(str(c.amount)) == Decimal("16.00"))
    assert supp.method == PaymentMethod.TRANSFER
    assert supp.status == PaymentStatus.PENDING
    assert supp.structured_communication  # OGM aanwezig


def test_paying_supplemental_charge_settles_balance(client, db_session):
    """#185 (C): de aanvullende charge op 'betaald' zetten vereffent het saldo."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="16.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)
    _pay(client, charge.id, "18.00")
    add_order_line(db_session, activity_id, reg.id, extra.id, 1)
    supp = next(c for c in _charges(db_session, reg) if Decimal(str(c.amount)) == Decimal("16.00"))
    _pay(client, supp.id, "16.00")
    bal = payments_door.balance(client, reg.id).json()
    assert Decimal(str(bal["balance"])) == Decimal("0.00")


def test_lowering_unpaid_order_consolidates_to_one_open_charge(client, db_session):
    """#195: zonder betaling is er één open charge voor het volledige openstaande
    bedrag; verhogen/verlagen herrekent die integraal (geen stapeling)."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="16.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)  # 18 open
    add_order_line(db_session, activity_id, reg.id, extra.id, 2)  # +32 → 50
    assert sorted(Decimal(str(c.amount)) for c in _charges(db_session, reg)) == [Decimal("50.00")]

    item = (
        db_session.query(RegistrationItem)
        .filter(
            RegistrationItem.registration_id == reg.id,
            RegistrationItem.product_id == extra.id,
        )
        .first()
    )
    activities_service.update_order_line(
        db_session, activity_id, reg.id, item.id, quantity=1, actor=SEEDED_ADMIN_EMAIL
    )  # → 34
    assert sorted(Decimal(str(c.amount)) for c in _charges(db_session, reg)) == [Decimal("34.00")]


def test_multiple_increases_consolidate_to_single_open_charge(client, db_session):
    """#195: na een volledige betaling meerdere keren verhogen → één open charge voor
    het totale openstaande bedrag, niet één per toevoeging."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="10.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)  # 18
    _pay(client, charge.id, "18.00")  # volledig betaald
    for _ in range(2):
        add_order_line(db_session, activity_id, reg.id, extra.id, 1)
    open_charges = [
        c
        for c in _charges(db_session, reg)
        if c.amount_paid is None or Decimal(str(c.amount_paid)) == 0
    ]
    assert len(open_charges) == 1
    assert Decimal(str(open_charges[0].amount)) == Decimal("20.00")


def test_quantity_increase_creates_supplemental_charge(client, db_session):
    """#185 (C): óók een aantalverhoging (geen los product) maakt een aanvullende charge."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)  # €18
    _pay(client, charge.id, "18.00")
    item = (
        db_session.query(RegistrationItem)
        .filter(RegistrationItem.registration_id == reg.id)
        .first()
    )
    activities_service.update_order_line(
        db_session, activity_id, reg.id, item.id, quantity=3, actor=SEEDED_ADMIN_EMAIL
    )  # €54 → +€36
    amounts = sorted(Decimal(str(c.amount)) for c in _charges(db_session, reg))
    assert amounts == [Decimal("18.00"), Decimal("36.00")]


def test_deleted_order_line_excluded_from_balance(client, db_session):
    """#194: een soft-deleted bestelregel telt niet meer mee in het verschuldigde
    (lazy relationship-load wordt nu ook gefilterd)."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="5.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)  # 18
    add_order_line(db_session, activity_id, reg.id, extra.id, 1)  # +5 → 23
    bal = payments_door.balance(client, reg.id).json()
    assert Decimal(str(bal["total_due"])) == Decimal("23.00")

    item = (
        db_session.query(RegistrationItem)
        .filter(RegistrationItem.registration_id == reg.id, RegistrationItem.product_id == extra.id)
        .first()
    )
    remove_order_line(db_session, activity_id, reg.id, item.id)
    bal = payments_door.balance(client, reg.id).json()
    assert Decimal(str(bal["total_due"])) == Decimal("18.00")  # verwijderde regel telt niet meer


def test_partial_payment_lower_via_patch_reduces_to_paid(client, db_session):
    """#193: een partieel betaalde charge krimpt bij verlaging tot het betaalde deel,
    zonder terugbetaling (enkel het onbetaalde deel vervalt)."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=2)  # 36, pending
    _pay(client, charge.id, "18.00")  # partieel 18 van 36

    item = (
        db_session.query(RegistrationItem)
        .filter(RegistrationItem.registration_id == reg.id)
        .first()
    )
    activities_service.update_order_line(
        db_session, activity_id, reg.id, item.id, quantity=1, actor=SEEDED_ADMIN_EMAIL
    )  # D = 18
    charges = _charges(db_session, reg)
    assert len(charges) == 1
    assert Decimal(str(charges[0].amount)) == Decimal("18.00")  # gekrompen tot het betaalde deel
    refunds = (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id == reg.id,
            PaymentRecord.type == PaymentType.REFUND,
        )
        .all()
    )
    assert refunds == []


def test_partial_payment_remove_extra_refunds_only_received(client, db_session):
    """#193: na een partiële betaling op een aanvullende charge wordt bij het verwijderen
    enkel het te véél ontvangene terugbetaald (niet het volledige charge-bedrag); geen 500."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="18.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)  # 18
    _pay(client, charge.id, "18.00")  # origineel volledig betaald
    add_order_line(db_session, activity_id, reg.id, extra.id, 1)  # +18 → supplement
    supp = next(c for c in _charges(db_session, reg) if c.id != charge.id)
    _pay(client, supp.id, "8.00")  # partieel 8 → netto ontvangen 26

    item = (
        db_session.query(RegistrationItem)
        .filter(RegistrationItem.registration_id == reg.id, RegistrationItem.product_id == extra.id)
        .first()
    )
    # D = 18; a save that raised here was the 500 this test is about
    assert remove_order_line(db_session, activity_id, reg.id, item.id) is not None
    db_session.expire_all()
    refunds = (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id == reg.id,
            PaymentRecord.type == PaymentType.REFUND,
        )
        .all()
    )
    assert sum((Decimal(str(r.amount)) for r in refunds), Decimal("0")) == Decimal("-8.00")
    # Verplichting nog niet uitbetaald → saldo −8; na bevestiging door de penningmeester €0.
    bal = payments_door.balance(client, reg.id).json()
    assert Decimal(str(bal["balance"])) == Decimal("-8.00")
    _confirm_refund(client, _latest_refund(db_session, reg).id)
    bal = payments_door.balance(client, reg.id).json()
    assert Decimal(str(bal["balance"])) == Decimal("0.00")


def test_koen_scenario_integral_recompute(client, db_session):
    """Scenario van Koen (#195): initiële bestelling volledig betaald → verlaging met
    uitgevoerde refund → verhoging met partiële betaling → verhoging met 2× hetzelfde
    product. Na elke bewerking geldt de invariant; er is hoogstens één open post."""
    _, comp, p1 = seed_activity_with_product(db_session, price="18.00")
    p2 = _add_product(db_session, comp, name="P2", price="20.00")
    p3 = _add_product(db_session, comp, name="P3", price="15.00")

    def _bal():
        return payments_door.balance(client, reg.id).json()

    def _open():
        return [
            c
            for c in _charges(db_session, reg)
            if c.amount_paid is None or Decimal(str(c.amount_paid)) == 0
        ]

    # 1) Initieel P1×2 = €36, volledig betaald via overschrijving.
    activity_id, reg, charge = _register(client, db_session, comp, p1, qty=2)
    _pay(client, charge.id, "36.00")
    assert Decimal(str(_bal()["balance"])) == Decimal("0.00")

    item1 = (
        db_session.query(RegistrationItem)
        .filter(RegistrationItem.registration_id == reg.id, RegistrationItem.product_id == p1.id)
        .first()
    )

    # 2) Verlaging P1×2 → ×1 (€18) → terugbetaling €18 als verplichting; de
    #    penningmeester bevestigt de terugstorting, pas dan vereffent het saldo.
    activities_service.update_order_line(
        db_session, activity_id, reg.id, item1.id, quantity=1, actor=SEEDED_ADMIN_EMAIL
    )
    refund = _latest_refund(db_session, reg)
    assert refund.status == PaymentStatus.PENDING and refund.amount_paid is None
    _confirm_refund(client, refund.id)
    b = _bal()
    assert Decimal(str(b["total_due"])) == Decimal("18.00")
    assert Decimal(str(b["balance"])) == Decimal("0.00")
    assert Decimal(str(b["total_refunded"])) == Decimal("18.00")

    # 3) Verhoging: P2 (€20) → totaal €38. Eén open charge €20, partieel €8 betaald.
    add_order_line(db_session, activity_id, reg.id, p2.id, 1)
    oc = _open()
    assert len(oc) == 1 and Decimal(str(oc[0].amount)) == Decimal("20.00")
    _pay(client, oc[0].id, "8.00")  # partieel
    assert Decimal(str(_bal()["balance"])) == Decimal("12.00")  # 38 − (18 + 8)

    # 4) Verhoging met 2× hetzelfde product P3 (€15) → totaal €68. Eén open post.
    for _ in range(2):
        add_order_line(db_session, activity_id, reg.id, p3.id, 1)
    b = _bal()
    assert Decimal(str(b["total_due"])) == Decimal("68.00")
    # netto ontvangen = 36 − 18 (refund) + 8 (partieel) = 26 → openstaand 42
    assert Decimal(str(b["balance"])) == Decimal("42.00")
    oc = _open()
    assert len(oc) == 1 and Decimal(str(oc[0].amount)) == Decimal("42.00")

    # Invariant: som van alle records = besteltotaal.
    recs = (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id == reg.id,
        )
        .all()
    )
    assert sum((Decimal(str(r.amount)) for r in recs), Decimal("0")) == Decimal("68.00")


def test_full_refund_scenario(client, db_session):
    """Omgekeerd scenario (#195): een betaalde bestelling volledig afbouwen → het hele
    betaalde bedrag wordt terugbetaald; besteltotaal €0, saldo €0, geen open post."""
    _, comp, p1 = seed_activity_with_product(db_session, price="18.00")
    p2 = _add_product(db_session, comp, name="P2", price="20.00")
    free = _add_product(db_session, comp, name="Gratis", price="0", is_free=True)

    def _bal():
        return payments_door.balance(client, reg.id).json()

    # 1) P1×1 = €18, volledig betaald.
    activity_id, reg, charge = _register(client, db_session, comp, p1, qty=1)
    _pay(client, charge.id, "18.00")

    # 2) P2 (€20) erbij → totaal €38; de open charge €20 volledig betaald.
    add_order_line(db_session, activity_id, reg.id, p2.id, 1)
    open20 = [
        c
        for c in _charges(db_session, reg)
        if c.amount_paid is None or Decimal(str(c.amount_paid)) == 0
    ][0]
    _pay(client, open20.id, "20.00")
    assert Decimal(str(_bal()["balance"])) == Decimal("0.00")

    # 3) P2 verwijderen → €20 terugbetaling (verplichting), penningmeester bevestigt.
    item_p2 = (
        db_session.query(RegistrationItem)
        .filter(RegistrationItem.registration_id == reg.id, RegistrationItem.product_id == p2.id)
        .first()
    )
    remove_order_line(db_session, activity_id, reg.id, item_p2.id)
    _confirm_refund(client, _latest_refund(db_session, reg).id)
    assert Decimal(str(_bal()["total_refunded"])) == Decimal("20.00")

    # 4) P1 → gratis product → totaal €0; de resterende €18 wordt ook terugbetaald.
    item_p1 = (
        db_session.query(RegistrationItem)
        .filter(RegistrationItem.registration_id == reg.id, RegistrationItem.product_id == p1.id)
        .first()
    )
    activities_service.update_order_line(
        db_session, activity_id, reg.id, item_p1.id, product_id=free.id, actor=SEEDED_ADMIN_EMAIL
    )
    _confirm_refund(client, _latest_refund(db_session, reg).id)

    b = _bal()
    assert Decimal(str(b["total_due"])) == Decimal("0.00")
    assert Decimal(str(b["balance"])) == Decimal("0.00")
    assert Decimal(str(b["total_refunded"])) == Decimal("38.00")  # alles terugbetaald

    open_charges = [
        c
        for c in _charges(db_session, reg)
        if c.amount_paid is None or Decimal(str(c.amount_paid)) == 0
    ]
    assert open_charges == []  # geen open post meer

    recs = (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id == reg.id,
        )
        .all()
    )
    assert sum((Decimal(str(r.amount)) for r in recs), Decimal("0")) == Decimal("0.00")


def test_marking_paid_without_amount_autofills_full_amount(client, db_session):
    """#199: 'betaald' zetten zonder bedrag vult amount_paid = het verschuldigde; saldo €0."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)
    r = payments_door.update(client, charge.id, {"status": "paid"})  # géén amount_paid
    assert r.status_code == 200, r.text
    db_session.expire_all()
    row = db_session.query(PaymentRecord).filter(PaymentRecord.id == charge.id).first()
    assert Decimal(str(row.amount_paid)) == Decimal("18.00")
    bal = payments_door.balance(client, reg.id).json()
    assert Decimal(str(bal["balance"])) == Decimal("0.00")


def test_adding_same_product_increments_quantity(client, db_session):
    """#197: hetzelfde product toevoegen verhoogt het aantal i.p.v. een dubbele regel."""
    _, comp, product = seed_activity_with_product(db_session, price="10.00")
    extra = _add_product(db_session, comp, name="Extra", price="5.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)
    for _ in range(2):
        add_order_line(db_session, activity_id, reg.id, extra.id, 1)
    db_session.expire_all()
    items = (
        db_session.query(RegistrationItem)
        .filter(RegistrationItem.registration_id == reg.id, RegistrationItem.product_id == extra.id)
        .all()
    )
    assert len(items) == 1
    assert items[0].quantity == 2


def test_refund_on_membership_payment(client, db_session):
    seed_postal_code(db_session)
    resp = sign_up_at_the_door(
        client,
        json={
            "street": "Milostraat",
            "house_number": "40",
            "postal_code": "2400",
            "payment_method": "transfer",
            "members": [
                {
                    "last_name": "Janssens",
                    "first_name": "An",
                    "email": "an@example.com",
                    "mobile": "0470123456",
                    "date_of_birth": "1980-01-01",
                    "gender_code": "M",
                    "relation_type": "HOOFDLID",
                }
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    member = db_session.query(Member).order_by(Member.id.desc()).first()
    ms = db_session.query(Membership).filter(Membership.member_id == member.id).first()
    charge = (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.MEMBERSHIP,
            PaymentRecord.payable_id == ms.id,
        )
        .first()
    )
    _pay(client, charge.id, str(charge.amount))

    r = payments_door.refund(client, charge.id, {"amount": "5.00", "note": "korting"})
    assert r.status_code == 200, r.text
    refund = r.json()
    assert refund["type"] == "refund"
    assert Decimal(str(refund["amount"])) == Decimal("-5.00")
    assert refund["refund_of_id"] == charge.id
