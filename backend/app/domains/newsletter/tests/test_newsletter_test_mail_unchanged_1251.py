"""The newsletter's test mail is the same mail after it changed hands (CR-13 phase 4d, #1251).

"Testmail naar mezelf" was a function of the newsletter's service that rendered
the letter AND handed it to mail — one domain commanding another from below its
door. Since this cut the newsletter only renders (`render_test`, a read) and the
door hands the result to mail: the door's one command.

Nothing about the mail may change. So this records what mail is asked to send —
to whom, the subject, the HTML, the text, the kind, the headers' input — and what
the screen answers, through the door, for the two versions of a letter: with
non-members in the audience (the unsubscribe line shows) and for members only.
Recorded on the code before the cut; the code after it must send the same.

Nothing is masked: the one address in the mail follows the host of the request
(#860), and that is the test client's on every machine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.newsletter.api import Audience
from app.domains.newsletter.models import Newsletter
from tests._snapshot import compare
from tests.conftest import SEEDED_ADMIN_EMAIL

SNAPSHOTS = Path(__file__).parent / "snapshots" / "newsletter_test_mail"
BEFORE = "the newsletter's test mail before its send moved to the door (#1251)"


@pytest.fixture
def asked(monkeypatch):
    """What mail is asked to send, argument by argument."""
    calls: list[dict] = []

    def fake(to_email, subject, body_html, **more):
        calls.append({"to": to_email, "subject": subject, "body_html": body_html, **more})
        return "sent"

    monkeypatch.setattr("app.domains.mail.api.send_campaign_mail", fake)
    return calls


def _letter(db, audience: Audience) -> Newsletter:
    letter = Newsletter(
        subject="Het najaar bij Raak",
        audience=audience,
        body_html="<div>Beste,</div><div>Tot <strong>zaterdag</strong> in de zaal.</div>",
    )
    db.add(letter)
    db.flush()
    return letter


def _recorded(call: dict, answer) -> str:
    notice = f"Testmail verstuurd naar {SEEDED_ADMIN_EMAIL}."
    parts = [f"status: {answer.status_code}", f"says {notice!r}: {notice in answer.text}"]
    for key in sorted(call):
        parts.append(f"== {key}\n{call[key]}")
    return "\n".join(parts) + "\n"


@pytest.mark.parametrize(
    ("audience", "name"),
    [(Audience.BOTH, "with_non_members"), (Audience.MEMBERS, "members_only")],
)
def test_the_test_mail_is_what_it_was(client, db_session, asked, audience, name):
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    headers = {"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"}
    letter = _letter(db_session, audience)

    answer = client.post(f"/admin/nieuwsbrieven/{letter.id}/testmail", headers=headers)

    assert len(asked) == 1, "mail was not asked exactly once"
    compare(SNAPSHOTS, name, _recorded(asked[0], answer), BEFORE)


def test_a_letter_without_a_subject_sends_nothing_and_says_so(client, db_session, asked):
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    headers = {"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"}
    letter = _letter(db_session, Audience.MEMBERS)
    letter.subject = ""
    db_session.flush()

    answer = client.post(f"/admin/nieuwsbrieven/{letter.id}/testmail", headers=headers)

    assert asked == []
    assert "Geef de nieuwsbrief eerst een onderwerp." in answer.text
