"""Fase 4b (#403): workflow-definities/instanties + werkbank-sweep (5 bronnen)."""
from decimal import Decimal

import pytest

from app.domains.workflow import api
from app.domains.workflow.handlers import sweep
from app.domains.workflow.models import WorkflowDefinition, WorkflowInstance, WorkflowTask


def test_definitie_start_advance_complete(db_session):
    db_session.add(WorkflowDefinition(code="test2stap", name="Test", steps=[
        {"kind": "stap.een", "title": "Eerst {wie}", "role": "ADMIN"},
        {"kind": "stap.twee", "title": "Dan FINANCE", "role": "FINANCE"},
    ]))
    db_session.flush()

    instance = api.start(db_session, "test2stap", subject_type="x", subject_id=1,
                         context={"wie": "Koen"})
    taak1 = (db_session.query(WorkflowTask)
             .filter(WorkflowTask.instance_id == instance.id).one())
    assert taak1.kind == "stap.een" and taak1.title == "Eerst Koen"

    api.complete_task(db_session, taak1.id, done_by="a@b", decision="ok")
    db_session.flush()
    taken = (db_session.query(WorkflowTask)
             .filter(WorkflowTask.instance_id == instance.id)
             .order_by(WorkflowTask.id).all())
    assert len(taken) == 2 and taken[1].kind == "stap.twee"
    assert taken[1].required_role == "FINANCE"
    assert instance.status == "running" and instance.current_step == 1

    # Afwijzing is óók een beslissing: besluit bewaard, flow eindigt gewoon.
    api.complete_task(db_session, taken[1].id, done_by="f@b", decision="Afgewezen: niet nodig")
    db_session.expire_all()
    assert instance.status == "done" and instance.done_at is not None
    assert taken[1].decision == "Afgewezen: niet nodig"


def test_onbekende_definitie_faalt_luid(db_session):
    with pytest.raises(ValueError):
        api.start(db_session, "bestaat-niet", subject_type="x", subject_id=1)


def test_bericht_start_via_definitie(client, db_session):
    client.post("/berichten", data={"naam": "Mie", "email": "mie@example.com",
                                    "bericht": "Workflow-test"})
    instance = (db_session.query(WorkflowInstance)
                .filter(WorkflowInstance.definition_code == "bericht")
                .order_by(WorkflowInstance.id.desc()).first())
    assert instance is not None
    taak = (db_session.query(WorkflowTask)
            .filter(WorkflowTask.instance_id == instance.id).one())
    assert taak.kind == "bericht.behartigen" and "Mie" in taak.title


def test_sweep_vult_werkbank_uit_de_bronnen(db_session):
    from app.domains.payment.api import GatewayPayment, PaymentRecord
    from app.kernel.jobs import KernelJob

    # refund-bevestiging (pending refund)
    db_session.add(PaymentRecord(payable_type="membership", payable_id=7,
                                 amount=Decimal("-5.00"), method="transfer",
                                 status="pending", type="refund"))
    # webhook-mismatch
    gp = GatewayPayment(provider="mollie", amount=Decimal("10.00"), status="paid")
    db_session.add(gp)
    db_session.flush()
    db_session.add(PaymentRecord(payable_type="registration", payable_id=8,
                                 amount=Decimal("10.00"), method="online",
                                 status="pending", gateway_payment_id=gp.id))
    # definitief gefaalde job
    db_session.add(KernelJob(name="iets.anders", payload={}, status="failed",
                             run_at=__import__("datetime").datetime.now(
                                 __import__("datetime").timezone.utc),
                             last_error="Boem"))
    db_session.flush()

    sweep(db_session, {"once": True})
    kinds = {t.kind for t in db_session.query(WorkflowTask)
             .filter(WorkflowTask.status == "open").all()}
    assert {"payment.refund_bevestigen", "payment.webhook_mismatch",
            "kernel.job_gefaald"} <= kinds

    # Idempotent: tweede run maakt geen duplicaten.
    before = db_session.query(WorkflowTask).count()
    sweep(db_session, {"once": True})
    assert db_session.query(WorkflowTask).count() == before


def test_sweep_kill_switch(db_session, monkeypatch):
    from app.config import settings
    from app.domains.payment.api import PaymentRecord

    monkeypatch.setattr(settings, "workbench_enabled", False)
    db_session.add(PaymentRecord(payable_type="membership", payable_id=9,
                                 amount=Decimal("-1.00"), method="transfer",
                                 status="pending", type="refund"))
    db_session.flush()
    before = db_session.query(WorkflowTask).count()
    sweep(db_session, {"once": True})
    assert db_session.query(WorkflowTask).count() == before


def test_werkbank_deep_link_full_page(client, db_session):
    from tests.conftest import SEEDED_ADMIN_EMAIL
    from app.domains.auth.api import SESSION_COOKIE, make_session_value

    client.post("/berichten", data={"naam": "Deep", "email": "d@example.com",
                                    "bericht": "Link"})
    task = db_session.query(WorkflowTask).order_by(WorkflowTask.id.desc()).first()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    # Zonder HX-Request → volledige pagina (deep-link).
    page = client.get(f"/admin/werkbank/taken/{task.id}")
    assert page.status_code == 200 and "<html" in page.text and "Werkbank" in page.text
    # Met HX-Request → fragment.
    frag = client.get(f"/admin/werkbank/taken/{task.id}", headers={"HX-Request": "true"})
    assert "<html" not in frag.text


def test_werkbank_twee_niveau_filter(client, db_session):
    """#502: de werkbank filtert op categorie + subtype, data-gedreven uit de
    dotted `kind` (bv. 'membership.reminder')."""
    from tests.conftest import SEEDED_ADMIN_EMAIL
    from app.domains.auth.api import SESSION_COOKIE, make_session_value

    api.create_task(db_session, kind="membership.reminder", title="Herinnering An",
                    subject_type="membership", subject_id=1)
    api.create_task(db_session, kind="membership.renewal", title="Vernieuwing Bob",
                    subject_type="membership", subject_id=2)
    api.create_task(db_session, kind="bericht.behartigen", title="Bericht Cara",
                    subject_type="form_submission", subject_id=3)
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    html = client.get("/admin/werkbank/lijst").text
    assert all(n in html for n in ("Herinnering An", "Vernieuwing Bob", "Bericht Cara"))
    # De categorie-opties zijn data-gedreven aanwezig.
    assert 'value="membership"' in html and 'value="bericht"' in html

    # Categorie membership → enkel de twee membership-taken.
    html = client.get("/admin/werkbank/lijst?category=membership").text
    assert "Herinnering An" in html and "Vernieuwing Bob" in html and "Bericht Cara" not in html

    # + subtype reminder → enkel die ene.
    html = client.get("/admin/werkbank/lijst?category=membership&subtype=reminder").text
    assert "Herinnering An" in html and "Vernieuwing Bob" not in html
