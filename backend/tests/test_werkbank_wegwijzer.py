"""#822 — wegwijzer of werkplek, en de weg naar het onderwerp.

Koens regel, 10 september 2026: *"een betaling 'afhandelen' via de werkbank-record is
zinloos"*, en *"bericht-behartigen is voor mij een workflow-actie die wel in de
werkbank kan horen, idem die mails en kernel-job."*

Dus: **heeft de entiteit een eigen scherm met eigen acties, dan is de werkbank een
wegwijzer. Kun je alleen beoordelen en noteren, dan is de werkbank de werkplek.**

Bij een webhook-mismatch is dat extra scherp: de oplossing is de status opnieuw
ophalen bij Mollie, en die knop staat op het betaalscherm. Hier "Afgehandeld" kunnen
zetten zou verbergen dat het geld nog steeds niet geboekt staat.

**De splitsing hangt aan het ONDERWERP en niet aan de taaksoort**, want dan volgt een
nieuwe betalingstaak vanzelf de juiste vorm. Ze loopt dwars door `SWEEP_SOORTEN`
heen: `mail.definitief_gefaald` en `kernel.job_gefaald` sluiten zichzelf én blijven
werkplek. Dat zijn twee onafhankelijke eigenschappen, en een eerdere opzet van dit
issue gooide ze op één hoop.

**De weg naar het onderwerp is de eigenlijke aanleiding.** Van de vier
onderwerpsoorten had er precies één een link (`payment_record`); bij drie van de vijf
taaksoorten las je de titel en ging je zoeken.

`kernel_job` krijgt bewust géén link: daar is geen scherm voor. In plaats van een knop
naar een pagina waar de job niet staat, tonen de detailrijen zijn naam, status,
pogingen en laatste fout. Een dode verwijzing is erger dan geen — zie #811, waar er
zes tegelijk stukbleken.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `payment_record` uit
`EIGEN_SCHERM_MET_ACTIES` gehaald → de eerste twee vallen om; `_onderwerp_link` laten
teruggeven `None` → de linktests vallen om.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.payment.api import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _taak(db, kind: str, subject_type: str, subject_id: str):
    from app.domains.workflow.api import create_task

    taak = create_task(db, kind=kind, title=f"proef {kind}",
                       subject_type=subject_type, subject_id=subject_id,
                       required_role="FINANCE")
    db.flush()
    return taak


def _detail(client, taak):
    return client.get(f"/admin/werkbank/taken/{taak.id}",
                      headers={"HX-Request": "true"}).text


def _record(db):
    rec = PaymentRecord(payable_type="registration", payable_id=8221,
                        type="charge", amount=Decimal("10.00"), method="transfer",
                        status="pending", created_at=datetime.now(timezone.utc))
    db.add(rec)
    db.flush()
    return rec


@pytest.mark.parametrize("kind", ["payment.refund_bevestigen",
                                  "payment.webhook_mismatch"])
def test_een_betalingstaak_is_een_wegwijzer(client, db_session, kind):
    _login(client, db_session)
    taak = _taak(db_session, kind, "payment_record", str(_record(db_session).id))

    html = _detail(client, taak)

    assert "Afgehandeld" not in html, (
        "een betaling 'afhandelen' via de werkbank is zinloos; bij een mismatch zou "
        "het bovendien verbergen dat het geld nog niet geboekt staat")
    assert "Besluit" not in html
    assert "Ga naar het onderwerp" in html, "de link is niet de primaire actie"


def test_een_beoordeeltaak_blijft_de_werkplek(client, db_session):
    """De tegenproef, en zonder haar is "alles verbergen" niet te onderscheiden van
    "het juiste verbergen"."""
    _login(client, db_session)
    taak = _taak(db_session, "kernel.job_gefaald", "kernel_job", "1")

    html = _detail(client, taak)

    assert "Afgehandeld" in html and "Besluit" in html, (
        "een taak die je alleen kan beoordelen verliest haar werkplek")


def test_een_mislukte_job_toont_zijn_gegevens_ter_plaatse(client, db_session):
    """Er is geen scherm voor kernel-jobs, dus dit ís de weg naar het onderwerp."""
    from app.kernel.jobs import KernelJob

    _login(client, db_session)
    job = KernelJob(name="proef.job", payload={}, status="failed",
                    run_at=datetime.now(timezone.utc), attempts=5, max_attempts=5,
                    last_error="ZeroDivisionError: division by zero")
    db_session.add(job)
    db_session.flush()
    taak = _taak(db_session, "kernel.job_gefaald", "kernel_job", str(job.id))

    html = _detail(client, taak)

    assert "proef.job" in html and "ZeroDivisionError" in html, (
        "je kan niet zien wat je beoordeelt")
    assert "Bekijk het onderwerp" not in html, (
        "er is geen scherm voor een kernel-job; een knop daarheen is een dode link")


def test_een_mailtaak_verwijst_naar_het_logboek(client, db_session):
    from app.domains.mail.api import EmailLog

    _login(client, db_session)
    log = EmailLog(recipient="iemand@example.com", subject="Proef",
                   email_type="generic", status="failed")
    db_session.add(log)
    db_session.flush()
    taak = _taak(db_session, "mail.definitief_gefaald", "email_log", str(log.id))

    html = _detail(client, taak)

    assert "/admin/e-maillog?recipient=iemand%40example.com" in html, (
        "de mailtaak verwijst niet naar het logboek van die ontvanger")
    assert "Afgehandeld" in html, "een mailtaak blijft een werkplek"


def test_een_berichttaak_verwijst_naar_de_inzendingen(client, db_session):
    from app.domains.forms.models import Form, FormSubmission

    _login(client, db_session)
    form = Form(title="Proefformulier", status="open", is_anonymous=True,
                share_token="w822")
    db_session.add(form)
    db_session.flush()
    inzending = FormSubmission(form_id=form.id, submitter_name="Iemand")
    db_session.add(inzending)
    db_session.flush()
    taak = _taak(db_session, "bericht.behartigen", "form_submission",
                 str(inzending.id))

    html = _detail(client, taak)

    assert f"/admin/formulieren/{form.id}/inzendingen" in html, (
        "de berichttaak verwijst niet naar de inzendingen van haar formulier")
    assert "Afgehandeld" in html, "een berichttaak blijft een werkplek"
