"""A sent letter shows who sent it, or no row when nobody did (#2066).

The page of a sent letter printed the sender raw, so a letter without one — older
data, a scheduled job, a fixture — read "Verstuurd door None". Red before the change:
the row stood there with the Python word. Proven red by the sender-less case below on
the old template.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.newsletter.api import Audience
from app.domains.newsletter.models import LetterStatus, Newsletter
from tests._letter import letter_doc
from tests.conftest import SEEDED_ADMIN_EMAIL

ROW = "Verstuurd door"


def _sent_letter(db, sent_by) -> Newsletter:
    letter = Newsletter(
        subject="Het najaar bij Raak",
        status=LetterStatus.SENT,
        sent_by=sent_by,
        audience=Audience.MEMBERS,
        sent_body_html="<div>Beste,</div>",
        body_document=letter_doc("<div>Beste,</div>"),
    )
    db.add(letter)
    db.flush()
    return letter


def _page(client, letter) -> str:
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    answer = client.get(f"/admin/nieuwsbrieven/{letter.id}")
    assert answer.status_code == 200
    return answer.text


@pytest.mark.parametrize("sender", [None, ""])
def test_a_letter_without_a_sender_has_no_sender_row_and_no_none(client, db_session, sender):
    page = _page(client, _sent_letter(db_session, sender))

    assert "Verstuurd</dt>" in page, "the page did not render the letter's facts"
    assert ROW not in page
    assert "None" not in page


def test_a_letter_with_a_sender_shows_it(client, db_session):
    page = _page(client, _sent_letter(db_session, "secretaris@example.com"))

    assert ROW in page
    assert "secretaris@example.com" in page
