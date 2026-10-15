"""Every outgoing message is built by one function, and what it builds is what it was (#1924).

A message was built in four places (the plain send, the campaign mail, the mail with
attachments, the retry from the log), each with its own MIME structure and each
adding the environment's label to the subject and its line to the body by itself.
`service.build_message` is the one function now; this file holds the proof that the
move changed nothing: the raw message each place hands to SMTP — headers, parts,
base64 attachment — compared byte for byte with the recording made before the move,
on production and on a test environment (HDEV). The boundaries of the multipart are
random, so they are named `<B1>`, `<B2>` in order of appearance.

The gate that keeps it so is `test_one_message_builder_gate_1924.py`.

Broken on purpose (15 October 2026, each put back): `build_message` writing `Cc`
before `To` → the plain send's two recordings differ; the `Reply-To` of the
attachments mail dropped → that recording differs.
"""

import re
from pathlib import Path

import pytest

from app.domains.mail import service as mail
from app.domains.mail.tests.test_env_line_in_the_body_1926 import (  # noqa: F401
    PLACES,
    smtp,
)

SNAPSHOTS = Path(__file__).parent / "snapshots" / "one_builder"

#: The places of #1926's test, and three more that set the optional headers: a Cc, a
#: Reply-To with the unsubscribe headers, a Reply-To on the mail with attachments.
EXTRA = {
    "plain send with a cc": lambda db: mail._send(
        "to@example.com", "Onderwerp", "<p>Hallo</p>", "cc@example.com"
    ),
    "campaign mail with unsubscribe and reply-to": lambda db: mail.send_campaign_mail(
        "to@example.com",
        "Onderwerp",
        "<html><body><p>Brief</p></body></html>",
        email_type="other",
        reply_to="antwoord@example.com",
        unsubscribe_url="https://example.com/uitschrijven/abc",
        body_text="Brief in tekst",
    ),
    "mail with attachments and reply-to": lambda db: mail.send_with_attachments(
        to_emails=["a@example.com"],
        subject="Onderwerp",
        body_html="<p>Notulen</p>",
        attachments=[("a.pdf", "application/pdf", b"%PDF-1"), ("b.bin", "", b"\x00\x01")],
        reply_to="beheer@example.com",
    ),
}
ALL_PLACES = {**PLACES, **EXTRA}
ENVIRONMENTS = ["prod", "hdev"]


def _slug(place: str) -> str:
    return re.sub(r"[^a-z]+", "-", place.lower()).strip("-")


def _named_boundaries(raw: str) -> str:
    found = []
    for boundary in re.findall(r'boundary="([^"]+)"', raw):
        if boundary not in found:
            found.append(boundary)
    for number, boundary in enumerate(found, start=1):
        raw = raw.replace(boundary, f"<B{number}>")
    return raw


def recording(place: str, env: str, db_session, monkeypatch, sent: list[str]) -> str:
    monkeypatch.setattr(mail.settings, "app_env", env)
    ALL_PLACES[place](db_session)
    assert len(sent) == 1, "the mail did not reach SMTP"
    return _named_boundaries(sent[0])


@pytest.mark.parametrize("place", list(ALL_PLACES))
@pytest.mark.parametrize("env", ENVIRONMENTS)
def test_the_message_is_what_it_was_before_the_one_function(
    place, env, request, db_session, monkeypatch
):
    sent = request.getfixturevalue("smtp")  # the fixture of #1926's test, imported above
    path = SNAPSHOTS / f"{_slug(place)}-{env}.eml"
    assert path.exists(), f"no recording for {place} on {env}"
    assert recording(place, env, db_session, monkeypatch, sent) == path.read_text(encoding="utf-8")
