"""The Werkbank on the kit (#1931; end state §5.1, §5.2; CR-11 Q99).

The list is the kit's table with the kind's own next step in the row, the task
is a record with its decision as the edit state. Three rules sit under both
screens and are held here on what the pages and the answers carry:

- **the next step per kind** (Koen, 12 October 2026: handle it here where that
  is all there is to do, go straight to the subject where the work is there);
- **a task is for one role** — on the list, on the record and for the POST
  alike: a task of another role is "not found", and stays open;
- **a signpost task is not ticked off here** (#822): its subject's own screen
  closes it, on either screen and for a hand-made request too.

Broken on purpose (13 October 2026, each put back):
- `workbench.next_step`: the mail kind given the button "handle" → the per-kind
  test red on `mail.definitief_gefaald`;
- `workbench.task_for`: the role check out → the record of another role's task
  is drawn ("Taak niet gevonden" is not on the page);
- `workbench.handle`: the signpost refusal out → "a payment task was ticked
  off in the workbench";
- `_workbench_view`: the subject line out of the search → "the search does not
  look at what a task is about".
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    csrf_token_for,
    get_user_roles,
    make_session_value,
)
from app.domains.workflow import api
from app.domains.workflow.models import TaskStatus, WorkflowTask
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

LIST = "/admin/werkbank"


def _login(client) -> dict[str, str]:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


ADMIN_ONLY = "alleen-beheerder@example.com"


def _login_admin_only(client, db) -> dict[str, str]:
    """A board member with the role ADMIN and no other: the seeded admin holds
    all three, so it sees every task."""
    user = User(email=ADMIN_ONLY, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.commit()
    assert get_user_roles(db, ADMIN_ONLY) == {"ADMIN"}, "the test needs a role gap"
    value = make_session_value(ADMIN_ONLY)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _task(db, kind, subject_type, subject_id, *, title=None, role="ADMIN", created=None):
    task = api.create_task(
        db,
        kind=kind,
        title=title or f"Taak {kind}",
        subject_type=subject_type,
        subject_id=str(subject_id),
        required_role=role,
    )
    db.flush()
    if created is not None:
        task.created_at = created
    db.commit()
    return task


def _payment(db) -> str:
    from app.domains.payment.api import PaymentRecord

    record = PaymentRecord(
        payable_type="registration",
        payable_id=193101,
        type="charge",
        amount=Decimal("30.00"),
        method="transfer",
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.flush()
    return str(record.id)


def _mail(db) -> int:
    from app.domains.mail.api import EmailLog

    log = EmailLog(
        recipient="iemand@example.com",
        subject="Bevestiging inschrijving",
        email_type="other",
        status="failed",
    )
    db.add(log)
    db.flush()
    return log.id


def _submission(db) -> int:
    from app.domains.forms.models import Form, FormSubmission

    form = Form(title="Contact", status="open", is_anonymous=True, share_token="wb1931")
    db.add(form)
    db.flush()
    submission = FormSubmission(form_id=form.id, submitter_name="Lore Voorbeeld")
    db.add(submission)
    db.flush()
    return submission.id


def _job(db) -> int:
    from app.kernel.jobs import KernelJob

    job = KernelJob(
        name="nieuwsbrief.verzenden",
        payload={},
        status="failed",
        run_at=datetime.now(timezone.utc),
        attempts=3,
        max_attempts=3,
        last_error="ZeroDivisionError: division by zero",
    )
    db.add(job)
    db.flush()
    return job.id


SUBJECTS = {
    "bericht.behartigen": ("form_submission", _submission),
    "payment.webhook_mismatch": ("payment_record", _payment),
    "payment.refund_bevestigen": ("payment_record", _payment),
    "mail.definitief_gefaald": ("email_log", _mail),
    "kernel.job_gefaald": ("kernel_job", _job),
}


def _of_kind(db, kind, **more):
    subject_type, make = SUBJECTS[kind]
    return _task(db, kind, subject_type, make(db), **more)


def _row(html: str, task) -> str:
    start = html.index(f'data-task="{task.id}"')
    return html[start : html.index("</tr>", start)]


def _button(row: str):
    """The row's one visible action: ("a" | "button", its label), or None."""
    found = re.search(r"<(a|button)\b[^>]*data-row-action[^>]*>([^<]+)<", row)
    return (found.group(1), found.group(2).strip()) if found else None


def _menu(row: str) -> list[str]:
    return [label.strip() for label in re.findall(r'role="menuitem"[^>]*>([^<]+)<', row)]


def _main(html: str) -> str:
    start = html.index("<main")
    return html[start : html.index("</main>", start)]


# ── the list ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kind, button, menu",
    [
        ("bericht.behartigen", ("button", "Afgehandeld"), ["Open de inzending"]),
        ("payment.webhook_mismatch", ("a", "Ga naar de betaling"), []),
        ("payment.refund_bevestigen", ("a", "Ga naar de betaling"), []),
        ("mail.definitief_gefaald", ("a", "Open in de e-maillog"), ["Afgehandeld"]),
        ("kernel.job_gefaald", ("button", "Afgehandeld"), []),
    ],
)
def test_the_row_offers_the_kinds_own_next_step(client, db_session, kind, button, menu):
    task = _of_kind(db_session, kind)
    _login(client)

    row = _row(client.get(LIST).text, task)

    assert _button(row) == button, f"{kind}: the row's button is {_button(row)}"
    assert _menu(row) == menu, f"{kind}: under ⋯ stands {_menu(row)}"
    if button[0] == "a":
        assert f'href="{api.subject_url(db_session, task)}"' in row, "the button does not go there"
    else:
        assert f'hx-post="{LIST}/taken/{task.id}/afgehandeld"' in row


def test_a_done_task_offers_nothing_in_its_row(client, db_session):
    task = _of_kind(db_session, "bericht.behartigen")
    api.close_task(db_session, task.id, done_by="iemand@example.com", decision="ok")
    db_session.commit()
    _login(client)

    row = _row(client.get(LIST + "?status=done").text, task)

    assert _button(row) is None and _menu(row) == []
    assert "Afgehandeld" in row, "the status badge of a done task"
    assert "—" in row, "a done task stands open since nothing"


def test_the_row_says_what_the_task_is_about(client, db_session):
    """Under the title: the payment with its amount, the form with the
    submission's number, the mail's subject, the job with its attempts — what
    the card of before never showed."""
    tasks = {kind: _of_kind(db_session, kind) for kind in SUBJECTS}
    _login(client)
    html = client.get(LIST).text

    assert "€ 30,00" in _row(html, tasks["payment.webhook_mismatch"])
    message = tasks["bericht.behartigen"]
    assert f"Formulier Contact · inzending #{message.subject_id}" in _row(html, message)
    assert "Bevestiging inschrijving" in _row(html, tasks["mail.definitief_gefaald"])
    assert "nieuwsbrief.verzenden · 3/3 pogingen" in _row(html, tasks["kernel.job_gefaald"])


def test_afgehandeld_in_the_row_closes_the_task_and_gives_the_list_back(client, db_session):
    task = _of_kind(db_session, "kernel.job_gefaald", title="Job die weg mag")
    stays = _of_kind(db_session, "kernel.job_gefaald", title="Job die blijft")
    headers = _login(client)

    answer = client.post(
        f"{LIST}/taken/{task.id}/afgehandeld",
        headers={**headers, "HX-Request": "true", "HX-Current-URL": f"http://testserver{LIST}"},
    )

    assert answer.status_code == 200
    assert answer.headers.get("HX-Retarget") == "#werkbank-lijst"
    assert "Job die blijft" in answer.text and "Job die weg mag" not in answer.text
    db_session.expire_all()
    closed = db_session.get(WorkflowTask, task.id)
    assert closed.status is TaskStatus.DONE and closed.done_by == SEEDED_ADMIN_EMAIL
    assert closed.decision is None, "the row ticks off without a decision"
    assert db_session.get(WorkflowTask, stays.id).status is TaskStatus.OPEN


def test_the_figures_count_open_today_and_older_than_a_week(client, db_session):
    now = datetime.now(timezone.utc)
    _of_kind(db_session, "kernel.job_gefaald")
    _of_kind(db_session, "kernel.job_gefaald", created=now - timedelta(days=9))
    done = _of_kind(db_session, "kernel.job_gefaald", created=now - timedelta(days=20))
    api.close_task(db_session, done.id, done_by="iemand@example.com")
    db_session.commit()
    roles = sorted(get_user_roles(db_session, SEEDED_ADMIN_EMAIL))

    counts = api.figures(api.tasks(db_session, roles, status="all"))

    assert (counts["open"], counts["today"], counts["old"], counts["done"]) == (2, 1, 1, 1)
    _login(client)
    html = client.get(LIST).text
    assert "Ouder dan een week" in html and "Vandaag" in html
    old = _row(html, db_session.query(WorkflowTask).order_by(WorkflowTask.created_at).all()[1])
    assert "9 dagen" in old, "an open task says how long it stands open"


def test_the_search_looks_at_what_a_task_is_about(client, db_session):
    message = _of_kind(db_session, "bericht.behartigen", title="Bericht behartigen")
    job = _of_kind(db_session, "kernel.job_gefaald", title="Achtergrondtaak mislukt")
    _login(client)

    html = client.get(LIST + "/lijst?q=inzending").text

    assert f'data-task="{message.id}"' in html, "the search does not look at what a task is about"
    assert f'data-task="{job.id}"' not in html
    assert "Geen taken gevonden" in client.get(LIST + "/lijst?q=bestaatniet").text


def test_the_filters_and_the_sort(client, db_session):
    payment = _of_kind(db_session, "payment.webhook_mismatch")
    mail = _of_kind(db_session, "mail.definitief_gefaald")
    finance = _of_kind(db_session, "payment.refund_bevestigen", role="FINANCE")
    _login(client)

    category = client.get(LIST + "/lijst?kind=payment").text
    assert f'data-task="{payment.id}"' in category and f'data-task="{mail.id}"' not in category
    exact = client.get(LIST + "/lijst?kind=mail.definitief_gefaald").text
    assert f'data-task="{mail.id}"' in exact and f'data-task="{payment.id}"' not in exact
    for_finance = client.get(LIST + "/lijst?rol=FINANCE").text
    assert f'data-task="{finance.id}"' in for_finance
    assert f'data-task="{payment.id}"' not in for_finance, "the role filter keeps another role"

    by_kind = client.get(LIST + "/lijst?sort=soort").text
    assert by_kind.index(f'data-task="{payment.id}"') < by_kind.index(f'data-task="{mail.id}"'), (
        "sorted by kind, Betaling stands before E-mail"
    )
    newest = client.get(LIST + "/lijst").text
    assert newest.index(f'data-task="{mail.id}"') < newest.index(f'data-task="{payment.id}"'), (
        "the newest task is not first"
    )


def test_the_list_page_carries_the_toolbar_outside_the_polled_fragment(client, db_session):
    _of_kind(db_session, "kernel.job_gefaald")
    _login(client)

    page = client.get(LIST).text
    fragment = client.get(LIST + "/lijst").text

    assert 'id="werkbank-melding"' in page, "nowhere to show why a task was not ticked off"
    assert 'type="search"' in page and 'type="search"' not in fragment
    assert "<optgroup" in page and 'name="rol"' in page
    assert "data-table-frame" in fragment and 'hx-trigger="every 30s"' not in fragment


# ── whose task it is ────────────────────────────────────────────────────────


def test_a_task_of_another_role_is_not_found_and_stays_open(client, db_session):
    """The list never showed it; the record and the POST do not know it either.
    The refusal is an HTML 422 for the page's message line — what the browser
    swaps in."""
    task = _of_kind(
        db_session, "kernel.job_gefaald", title="Alleen voor de penningmeester", role="FINANCE"
    )
    headers = _login_admin_only(client, db_session)

    assert f'data-task="{task.id}"' not in client.get(LIST + "?status=all").text, (
        "a task of another role is on the list"
    )
    record = client.get(f"{LIST}/taken/{task.id}")
    assert "Taak niet gevonden" in _main(record.text)
    assert "data-form-flow" not in record.text, "the record of another role's task is drawn"
    assert "Alleen voor de penningmeester" not in record.text, "the title of another role's task"

    for form in ({}, {"besluit": "toch gedaan", "standalone": "1"}):
        answer = client.post(f"{LIST}/taken/{task.id}/afgehandeld", data=form, headers=headers)
        assert answer.status_code == 422, "a task of another role was handled"
        assert answer.headers.get("HX-Retarget") == "#werkbank-melding"
        assert "Taak niet gevonden" in answer.text
    db_session.expire_all()
    assert db_session.get(WorkflowTask, task.id).status is TaskStatus.OPEN, (
        "a task of another role was handled"
    )


def test_a_signpost_task_cannot_be_ticked_off_here(client, db_session):
    task = _of_kind(db_session, "payment.webhook_mismatch")
    headers = _login(client)

    for form in ({}, {"besluit": "geregeld", "standalone": "1"}):
        answer = client.post(f"{LIST}/taken/{task.id}/afgehandeld", data=form, headers=headers)
        assert answer.status_code == 422
        assert "scherm van het onderwerp" in answer.text
        assert answer.headers.get("HX-Retarget") == "#werkbank-melding"
    db_session.expire_all()
    assert db_session.get(WorkflowTask, task.id).status is TaskStatus.OPEN, (
        "a payment task was ticked off in the workbench"
    )


# ── the record ──────────────────────────────────────────────────────────────


def test_an_open_task_reads_first_and_afhandelen_opens_the_decision(client, db_session):
    task = _of_kind(db_session, "bericht.behartigen", title="Bericht via het contactformulier")
    _login(client)

    read = _main(client.get(f"{LIST}/taken/{task.id}").text)
    assert 'data-mode="read"' in read and 'name="besluit"' not in read
    assert re.search(rf'href="{LIST}/taken/{task.id}\?bewerken=1"[^>]*>\s*Afhandelen', read), (
        "the primary of an open task is Afhandelen, to its edit state"
    )
    assert "data-summary-card" in read and "Open sinds" in read
    assert "Lore Voorbeeld" in read, "the card Onderwerp does not say who wrote"
    assert "Bekijk het onderwerp" in read and 'id="werkbank-melding"' in read

    editing = _main(client.get(f"{LIST}/taken/{task.id}?bewerken=1").text)
    assert 'data-mode="edit"' in editing and 'name="besluit"' in editing
    assert f'hx-post="{LIST}/taken/{task.id}/afgehandeld"' in editing
    assert 'name="standalone"' in editing
    bar = editing[editing.index("data-action-bar") :]
    assert "Afgehandeld" in bar and "Annuleren" in bar, "one save, named Afgehandeld"
    assert not re.search(r">\s*Afhandelen\s*<", editing), "the primary stays while editing"


def test_the_records_save_closes_the_task_and_goes_back(client, db_session):
    task = _of_kind(db_session, "bericht.behartigen")
    headers = _login(client)
    back = f"{LIST}?status=all"

    answer = client.post(
        f"{LIST}/taken/{task.id}/afgehandeld",
        data={"besluit": "  Telefonisch beantwoord  ", "standalone": "1"},
        headers={
            **headers,
            "HX-Request": "true",
            "HX-Current-URL": f"http://testserver{LIST}/taken/{task.id}?terug={back}&bewerken=1",
        },
    )

    assert answer.status_code == 204
    assert answer.headers.get("HX-Redirect") == back, "the save does not go back to the list"
    db_session.expire_all()
    closed = db_session.get(WorkflowTask, task.id)
    assert closed.status is TaskStatus.DONE and closed.decision == "Telefonisch beantwoord"


def test_a_done_task_shows_its_decision_and_has_no_primary(client, db_session):
    task = _of_kind(db_session, "bericht.behartigen")
    api.close_task(db_session, task.id, done_by="koen@example.com", decision="Teruggebeld")
    db_session.commit()
    _login(client)

    page = _main(client.get(f"{LIST}/taken/{task.id}?bewerken=1").text)

    assert 'data-mode="read"' in page, "a done task opens in edit mode"
    assert 'name="besluit"' not in page and "Afhandelen" not in page
    decision = page[page.index('id="wb-besluit"') :]
    assert "Teruggebeld" in decision and "koen@example.com" in decision


@pytest.mark.parametrize("kind", ["payment.webhook_mismatch", "payment.refund_bevestigen"])
def test_a_payment_task_is_a_signpost_on_its_record(client, db_session, kind):
    task = _of_kind(db_session, kind)
    _login(client)

    page = _main(client.get(f"{LIST}/taken/{task.id}?bewerken=1").text)

    assert 'data-mode="read"' in page and 'name="besluit"' not in page
    assert 'id="wb-besluit"' not in page, "a signpost task has no decision of its own"
    assert re.search(
        rf'href="{re.escape(api.subject_url(db_session, task))}"[^>]*>\s*Ga naar het onderwerp',
        page,
    ), "the primary of a signpost goes to its subject"
    assert "sluit zichzelf" in page and "€ 30,00" in page
