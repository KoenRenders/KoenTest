"""#704 + #705 — van een betalingstaak naar de betaalkaart, en zonder een uur wachten.

**#704.** Alle drie de betalingstaken zetten `subject_type="payment_record"` maar
vulden `subject_id` met `record.payable_id`. Het type zei dus iets wat de waarde niet
was — en dat was geen slordigheid: de kolom was een `Integer` terwijl
`PaymentRecord.id` een UUID in een `String(36)` is. **Het record-id paste er niet
in**, en leefde alleen in de titeltekst.

Dat brak precies de taak die een verwijzing het hardst nodig heeft: bij een
`payment.wees_record` bestáát het payable per definitie niet — dat ís de aanleiding.
Een link die op het payable steunt, is daar dus per definitie stuk.

**#705.** De sweep plant zichzelf elk uur opnieuw in, dus een openstaande
terugbetaling kon tot een uur onzichtbaar blijven. Berichten zijn wél
gebeurtenisgedreven; uitgerekend het soort taak dat over geld gaat werd het traagst
zichtbaar.

De sweep wordt **vervroegd**, de taak wordt niet zelf aangemaakt: de titel is de
idempotentiesleutel, en twee plekken die die sleutel bouwen leveren dezelfde refund
twee keer op. En `once=True` is wat het veilig maakt — zonder die vlag plant elke
extra sweep een opvolger en verdubbelt de cadans blijvend.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from app.domains.payment.api import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_agnostisch

PAYABLE = ("registration", 7040)


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db.flush()
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _charge(db, payable_id=PAYABLE[1], bedrag="30.00"):
    rec = PaymentRecord(payable_type="registration", payable_id=payable_id,
                        type="charge", amount=Decimal(bedrag),
                        amount_paid=Decimal(bedrag), method="transfer",
                        status="paid", paid_at=datetime.now(timezone.utc))
    db.add(rec)
    db.flush()
    return rec


def _sweep(db):
    from app.domains.workflow.handlers import sweep

    sweep(db, {"once": True})
    db.flush()


def _taken(db, kind=None):
    from app.domains.workflow.models import WorkflowTask

    q = db.query(WorkflowTask)
    if kind:
        q = q.filter(WorkflowTask.kind == kind)
    return q.all()


# ── 1. Het onderwerp is het record, niet het payable ───────────────────────

def test_een_refundtaak_verwijst_naar_het_record(client, db_session):
    from app.domains.payment.api import create_refund

    charge = _charge(db_session)
    refund = create_refund(db_session, charge.id, Decimal("10.00"), settled=False)
    db_session.flush()

    _sweep(db_session)
    taak = next(t for t in _taken(db_session, "payment.refund_bevestigen"))
    assert taak.subject_type == "payment_record"
    assert taak.subject_id == str(refund.id), (
        "de taak wijst naar het payable in plaats van naar het record")


def test_een_weesrecord_verwijst_ook_naar_het_record(client, db_session):
    """De taak die dit het hardst nodig heeft: hier bestáát het payable niet — dat is
    de aanleiding — dus een verwijzing die daarop steunt, is per definitie stuk."""
    from app.domains.payment.handlers import reconcile

    wees = PaymentRecord(payable_type="registration", payable_id=999999,
                         type="charge", amount=Decimal("15.00"),
                         method="transfer", status="pending")
    db_session.add(wees)
    db_session.flush()

    reconcile(db_session, {"once": True})
    db_session.flush()

    taak = next(t for t in _taken(db_session, "payment.wees_record"))
    assert taak.subject_id == str(wees.id), (
        "de weestaak wijst naar een payable dat niet bestaat")


def test_het_record_id_past_in_de_kolom(client, db_session):
    """De reden dat het payable erin stond: een UUID paste niet in een Integer.
    Zonder deze test zou een terugkeer naar `Integer` pas opvallen bij de eerste
    betalingstaak in productie."""
    from app.domains.workflow.models import WorkflowTask

    kolom = WorkflowTask.__table__.c.subject_id
    assert not isinstance(kolom.type, type(WorkflowTask.__table__.c.id.type)), (
        "subject_id is weer een Integer; een record-UUID past daar niet in")
    assert kolom.type.length >= 36


# ── 2. De sprong naar de kaart ─────────────────────────────────────────────

def test_de_taak_toont_een_link_naar_de_betaling(client, db_session):
    from app.domains.payment.api import create_refund

    charge = _charge(db_session, payable_id=7041)
    refund = create_refund(db_session, charge.id, Decimal("10.00"), settled=False)
    db_session.flush()
    _sweep(db_session)
    db_session.commit()
    taak = next(t for t in _taken(db_session, "payment.refund_bevestigen"))
    _login(client, db_session)

    html = client.get(f"/admin/werkbank/taken/{taak.id}").text
    assert f"/admin/betalingen?record={refund.id}" in html, (
        "geen link naar de betaalkaart")


def test_het_betaalscherm_filtert_op_dat_record(client, db_session):
    """Een FILTER en geen anker: de lijst wordt gefilterd, dus een anker kan naar
    een kaart wijzen die op die pagina niet gerenderd is."""
    eerste = _charge(db_session, payable_id=7042, bedrag="30.00")
    tweede = _charge(db_session, payable_id=7043, bedrag="44.44")
    db_session.commit()
    _login(client, db_session)

    html = client.get(f"/admin/betalingen?record={eerste.id}").text
    assert "30.00" in html
    assert "44.44" not in html, "de andere betaling staat er ook, dus er wordt niet gefilterd"


def test_een_onbekend_record_toont_een_lege_lijst(client, db_session):
    """Geen 500 en geen stille terugval op "alles": een link naar een verwijderde
    betaling hoort te zeggen dat er niets is."""
    _charge(db_session, payable_id=7044)
    db_session.commit()
    _login(client, db_session)

    resp = client.get("/admin/betalingen?record=bestaat-niet")
    assert resp.status_code == 200
    assert "Geen betalingen" in resp.text


# ── 3. De vervroegde sweep ─────────────────────────────────────────────────

def test_een_openstaande_refund_plant_meteen_een_sweep(client, db_session):
    from app.domains.payment.api import create_refund
    from app.kernel.jobs import KernelJob

    charge = _charge(db_session, payable_id=7045)
    create_refund(db_session, charge.id, Decimal("10.00"), settled=False)
    db_session.flush()

    jobs = (db_session.query(KernelJob)
            .filter(KernelJob.name == "workflow.sweep").all())
    assert jobs, "er is geen sweep vervroegd"
    assert any(j.payload.get("once") for j in jobs), (
        "de vervroegde sweep plant een opvolger; dat verdubbelt de cadans blijvend")


def test_een_afgehandelde_refund_plant_er_geen(client, db_session):
    """De keerzijde: een reeds uitbetaalde terugbetaling levert geen taak op, dus
    ook geen reden om de sweep te vervroegen. Zonder deze grens zou élke refund een
    extra job planten."""
    from app.domains.payment.api import create_refund
    from app.kernel.jobs import KernelJob

    charge = _charge(db_session, payable_id=7046)
    create_refund(db_session, charge.id, Decimal("10.00"), settled=True)
    db_session.flush()

    assert not (db_session.query(KernelJob)
                .filter(KernelJob.name == "workflow.sweep").all())


def test_de_taak_wordt_niet_dubbel_aangemaakt(client, db_session):
    """Waarom vervroegen en niet zelf aanmaken: de titel is de idempotentiesleutel.
    Twee sweeps na elkaar horen één taak op te leveren."""
    from app.domains.payment.api import create_refund

    charge = _charge(db_session, payable_id=7047)
    create_refund(db_session, charge.id, Decimal("10.00"), settled=False)
    db_session.flush()

    _sweep(db_session)
    _sweep(db_session)
    assert len(_taken(db_session, "payment.refund_bevestigen")) == 1
