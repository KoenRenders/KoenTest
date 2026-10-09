"""CR-13 phase 4d (#1251): a message is submitted through forms' port and the
confirmation is mail's own doing — what is stored and what is mailed stays.

Three calls leave the list of commands between domains here: the chatbot's tool
called forms' `submit_bericht` (a command that committed), and forms called
`mail.api.send_form_confirmation` twice — for a message and for an ordinary form.
Now the tool asks forms through the port `SubmitMessage`; forms says that a
submission was made and to whom a confirmation goes (`SubmissionCreated.
confirm_to`); mail subscribes, words the mail and queues it.

No behaviour changes, so the proof is **the same rows and the same mail on the
same input**: every case below was recorded on the code BEFORE the change — what
the caller got back, the submission, the task in the workbench, and **every mail
with its recipient, type, subject and text** — and the code after must give it
again, character for character (`tests/_snapshot.py`).

**How a mail is seen:** at mail's one way out, `mail.service._send`, replaced by
a recorder. Before the change the mail reached it from the request (its
background task); after it, from the queued job — so each case runs the queue
before it looks. The recording does not see WHEN a mail leaves, only that it is
the same mail; the PR says what changes there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domains.chatbot.tools import submit_idea
from app.domains.forms.api import CONTACT_FORM_SLUG, Form, FormSubmission
from app.domains.workflow.models import WorkflowInstance
from app.kernel.jobs import run_due_jobs
from tests import forms_door
from tests._snapshot import compare, normalise
from tests.conftest import form_guard_fields

pytestmark = pytest.mark.ui_serverrendered

SNAPSHOTS = Path(__file__).parent / "snapshots" / "form_confirmation_1251"
BEFORE = "a message went through forms' port and mail queued the confirmation (CR-13 phase 4d)"


@pytest.fixture
def mails(monkeypatch):
    """Every mail that reaches mail's one way out, in order."""
    from app.domains.mail import service

    sent: list[str] = []

    def record(to_email, subject, body_html, cc=None, email_type="other"):
        # The link to change an answer carries two tokens of this run, and the
        # tenant's home address — which is the environment's, not the code's.
        body = re.sub(
            r"https?://[^/\"<]+/formulier/[\w-]+/edit/[\w-]+",
            "<HOME>/formulier/<TOKEN>/edit/<TOKEN>",
            body_html,
        )
        sent.append(f"mail to {to_email} cc={cc} type={email_type}\n  {subject}\n  {body}")

    monkeypatch.setattr(service, "_send", record)
    return sent


def _contact_form(db, *, confirmation: bool) -> Form:
    form = db.query(Form).filter(Form.slug == CONTACT_FORM_SLUG).one()
    form.send_confirmation = confirmation
    form.confirmation_message = "We antwoorden binnen de week." if confirmation else None
    db.flush()
    return form


def _record(name: str, said: object, db, mails: list[str], form: Form) -> None:
    run_due_jobs(db)
    db.expire_all()
    lines = [f"answer: {said}"]
    for row in db.query(FormSubmission).filter_by(form_id=form.id).order_by(FormSubmission.id):
        lines.append(f"submission: name={row.submitter_name!r} email={row.submitter_email!r}")
    tasks = db.query(WorkflowInstance).filter(WorkflowInstance.definition_code == "bericht").count()
    lines.append(f"message tasks: {tasks}")
    lines.extend(mails or ["(no mail)"])
    compare(SNAPSHOTS, name, normalise("\n".join(lines), {}, {}), BEFORE)


# ── a message: the contact page and the chatbot's tool ───────────────────────

MESSAGE = {"naam": "Mie Proef", "email": "mie-1251@example.com", "bericht": "Is er nog plaats?"}


@pytest.mark.parametrize("confirmation", [True, False], ids=["confirmed", "no_confirmation"])
def test_the_contact_page_stores_and_mails_as_it_did(client, db_session, mails, confirmation):
    form = _contact_form(db_session, confirmation=confirmation)

    answer = client.post("/berichten", data={**form_guard_fields(), **MESSAGE})

    said = f"{answer.status_code} HX-Redirect={answer.headers.get('HX-Redirect')}"
    _record(
        f"contact_page_{'confirmed' if confirmation else 'no_confirmation'}",
        said,
        db_session,
        mails,
        form,
    )


def test_the_contact_page_dropped_by_the_guard_leaves_nothing_as_before(client, db_session, mails):
    """Without the guard's fields the page thanks and stores nothing."""
    form = _contact_form(db_session, confirmation=True)

    answer = client.post("/berichten", data=MESSAGE)

    said = f"{answer.status_code} HX-Redirect={answer.headers.get('HX-Redirect')}"
    _record("contact_page_dropped", said, db_session, mails, form)


def test_the_chatbots_tool_stores_and_mails_as_it_did(db_session, mails):
    form = _contact_form(db_session, confirmation=True)

    said = submit_idea(db_session, "Bot Proef", "Een idee voor de kermis.", "bot-1251@example.com")

    _record("chatbot_tool", said, db_session, mails, form)


def test_the_chatbots_tool_refuses_as_it_did(db_session, mails):
    """No address: the tool answers its own sentence and nothing is stored."""
    form = _contact_form(db_session, confirmation=True)

    said = submit_idea(db_session, "Bot Proef", "Een idee voor de kermis.", None)

    _record("chatbot_tool_refused", said, db_session, mails, form)


# ── the chatbot's door: the visitor asks Raakje to pass a message on ─────────


@pytest.mark.parametrize("ends", ["answered", "fails_after_the_tool"])
def test_the_chatbots_door_keeps_the_message_as_it_did(
    client, db_session, mails, monkeypatch, ends
):
    """The whole request: the model asks for the tool, the tool stores the
    message, and — in the second case — the conversation fails right after. The
    message is kept either way, and the request commits it: before the change
    forms did, behind its facade; now the door of the request does."""
    from sqlalchemy import event

    from app.config import settings
    from app.domains.chatbot import providers, ui
    from app.domains.chatbot.limits import chat_char_budget
    from app.domains.chatbot.providers.base import AssistantMessage, ToolCall

    class Provider:
        rounds = 0

        def complete(self, messages, tools=None, tool_choice=None):
            Provider.rounds += 1
            if Provider.rounds == 1:
                idea = {
                    "name": "Bel Proef",
                    "email": "bel-1251@example.com",
                    "content": "Mag ik helpen op de kermis?",
                }
                return AssistantMessage(tool_calls=[ToolCall("call-1", "submit_idea", idea)])
            if ends == "fails_after_the_tool":
                raise RuntimeError("the provider is gone")
            return AssistantMessage(content="Ik heb het doorgegeven.")

    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(ui, "tenant_public_chat_enabled", lambda db: True)
    monkeypatch.setattr(providers, "get_provider", lambda: Provider())
    monkeypatch.setattr(chat_char_budget, "charge", lambda request, n, **k: None)
    form = _contact_form(db_session, confirmation=True)
    commits: list[int] = []
    event.listen(db_session, "after_commit", lambda session: commits.append(1))

    answer = client.post("/raakje/vraag", data={"vraag": "Geef dit door aan het bestuur."})

    said = (
        f"{answer.status_code} failed={answer.headers.get('X-Raakje-Failed')} "
        f"rounds={Provider.rounds} committed={'yes' if commits else 'no'}"
    )
    _record(f"chatbot_door_{ends}", said, db_session, mails, form)


# ── an ordinary form ─────────────────────────────────────────────────────────


def _form(client, **settings) -> dict:
    payload = {
        "title": "Helpers gezocht",
        "description": "Geef je op",
        "status": "open",
        "send_confirmation": True,
        "confirmation_message": "Tot dan!",
        "allow_edit": False,
        "fields": [{"field_type": "text", "label": "Naam", "required": True, "position": 0}],
    }
    made = forms_door.create_form(client, payload | settings)
    assert made.status_code == 200, made.text
    return made.json()


@pytest.mark.parametrize(
    ("name", "settings"),
    [
        ("form_confirmed", {}),
        ("form_confirmed_with_edit_link", {"allow_edit": True}),
        ("form_anonymous", {"is_anonymous": True}),
        ("form_without_confirmation", {"send_confirmation": False}),
    ],
)
def test_a_form_stores_and_mails_as_it_did(client, db_session, mails, name, settings):
    form = _form(client, **settings)

    answer = forms_door.submit(
        client,
        form["share_token"],
        {
            **form_guard_fields(),
            "submitter_name": "Jan Proef",
            "submitter_email": "jan-1251@example.com",
            "answers": [{"field_id": form["fields"][0]["id"], "text": "Jan"}],
        },
    )

    body = answer.json()
    said = f"{answer.status_code} status={body.get('status')} edit_token={'yes' if body.get('edit_token') else 'no'}"
    _record(name, said, db_session, mails, db_session.get(Form, form["id"]))


# ── the commit is the door's ─────────────────────────────────────────────────


def test_the_contact_page_commits_what_it_stored(client, db_session, mails):
    """Forms' service no longer commits a message itself; the contact page is the
    door of its request and does. A test that reads through the request's own
    session cannot tell a flush from a commit, so the commit itself is watched.

    Proven red: the `db.commit()` of `forms.service.send_message` (the page's door
    service) taken out."""
    from sqlalchemy import event

    _contact_form(db_session, confirmation=True)
    commits: list[int] = []
    event.listen(db_session, "after_commit", lambda session: commits.append(1))

    answer = client.post("/berichten", data={**form_guard_fields(), **MESSAGE})

    assert answer.headers.get("HX-Redirect") == "/?bericht=verzonden"
    assert commits, "the contact page stored a message and never committed it"
