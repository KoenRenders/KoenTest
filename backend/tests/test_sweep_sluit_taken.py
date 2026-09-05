"""#675 — een taak sluit wanneer haar aanleiding verdwijnt.

`close_task` werd alleen vanuit de werkbank aangeroepen: geen enkele taak sloot
zichzelf, ook niet als de reden weg was. Een uitbetaalde terugbetaling liet haar
`payment.refund_bevestigen`-taak staan, een opgeloste webhook-mismatch idem. De
sweep maakte geen dubbele taken — hij vergelijkt titels — maar ruimde niets op.

De oplossing zat al in de sweep: `_sweep_sources` bouwt elke ronde de lijst van nu
geldende kandidaten. Staat een open taak daar niet meer in, dan is haar aanleiding
weg. Dezelfde titels als sleutel, dus geen nieuw mechanisme — het is de spiegel
van de idempotentiecheck.

Twee dingen die hier stil kapot kunnen:

1. **Alleen soorten die de sweep zelf maakt.** `payment.wees_record` komt uit een
   andere job, `bericht.behartigen` is event-gedreven. Van hun aanleiding weet
   `_sweep_sources` niets, dus "sluit alles wat niet matcht" zou taken sluiten
   waarvan de sweep het bestaan niet kent.
2. **`done_by="systeem"` met een reden**, anders toont het archief uit #674 taken
   die door niemand afgehandeld lijken.
"""
from decimal import Decimal

import pytest

from app.domains.payment.api import PaymentRecord
from app.domains.workflow import api
from app.domains.workflow.handlers import sweep
from app.domains.workflow.models import WorkflowTask

pytestmark = pytest.mark.ui_agnostisch


def _taak(db, *, kind, titel, rol="FINANCE"):
    taak = WorkflowTask(kind=kind, title=titel, status="open",
                        subject_type="payment_record", subject_id=1,
                        required_role=rol)
    db.add(taak)
    db.commit()
    return taak


def test_een_taak_zonder_aanleiding_sluit(db_session):
    """De kern: de refund is uitbetaald, dus de taak heeft geen reden meer."""
    taak = _taak(db_session, kind="payment.refund_bevestigen",
                 titel="Refund abc bevestigen (registration #1)")
    sweep(db_session, {"once": True})

    db_session.expire_all()
    vers = db_session.get(WorkflowTask, taak.id)
    assert vers.status == "done", "de taak bleef open terwijl haar aanleiding weg is"
    assert vers.done_by == "systeem", (
        "zonder done_by lijkt de taak in het archief door niemand afgehandeld")
    assert vers.decision and "aanleiding" in vers.decision.lower()


def test_een_taak_met_aanleiding_blijft_open(db_session):
    """De spiegel: zolang de refund openstaat, blijft de taak staan."""
    from app.domains.payment.api import create_refund

    charge = PaymentRecord(payable_type="registration", payable_id=6750,
                           amount=Decimal("30.00"), method="transfer", status="paid")
    charge.amount_paid = Decimal("30.00")
    db_session.add(charge)
    db_session.flush()
    refund = create_refund(db_session, charge.id, Decimal("10.00"),
                           actor="fin@test", settled=False)
    db_session.commit()

    sweep(db_session, {"once": True})
    db_session.expire_all()

    taken = db_session.query(WorkflowTask).filter(
        WorkflowTask.kind == "payment.refund_bevestigen",
        WorkflowTask.status == "open").all()
    assert any(str(refund.id) in t.title for t in taken), (
        "de sweep sloot een taak waarvan de aanleiding er nog is")


@pytest.mark.parametrize("kind", ["payment.wees_record", "bericht.behartigen"])
def test_soorten_van_buiten_de_sweep_blijven_ongemoeid(db_session, kind):
    """De valkuil: van deze aanleidingen weet _sweep_sources niets."""
    taak = _taak(db_session, kind=kind, titel=f"Taak van {kind}", rol="ADMIN")
    sweep(db_session, {"once": True})

    db_session.expire_all()
    assert db_session.get(WorkflowTask, taak.id).status == "open", (
        f"{kind} komt niet uit de sweep — die mag hem niet sluiten")


def test_de_sweep_maakt_nog_altijd_geen_dubbele_taken(db_session):
    """De idempotentie waar het sluiten de spiegel van is."""
    from app.domains.payment.api import create_refund

    charge = PaymentRecord(payable_type="registration", payable_id=6751,
                           amount=Decimal("30.00"), method="transfer", status="paid")
    charge.amount_paid = Decimal("30.00")
    db_session.add(charge)
    db_session.flush()
    create_refund(db_session, charge.id, Decimal("10.00"), actor="fin@test",
                  settled=False)
    db_session.commit()

    sweep(db_session, {"once": True})
    sweep(db_session, {"once": True})
    db_session.expire_all()

    titels = [t.title for t in db_session.query(WorkflowTask).filter(
        WorkflowTask.kind == "payment.refund_bevestigen").all()]
    assert len(titels) == len(set(titels)), f"dubbele taken: {titels}"


def test_een_gesloten_taak_staat_in_het_archief(db_session):
    """#674 en #675 samen: automatisch gesloten taken verdwijnen niet spoorloos."""
    taak = _taak(db_session, kind="payment.refund_bevestigen",
                 titel="Refund xyz bevestigen (registration #9)")
    sweep(db_session, {"once": True})
    db_session.expire_all()

    afgehandeld = api.tasks(db_session, ["FINANCE"], status="done")
    assert any(t.id == taak.id for t in afgehandeld)
