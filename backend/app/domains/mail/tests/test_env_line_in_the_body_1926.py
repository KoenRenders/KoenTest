"""A mail from a test environment opens with its environment's line (#1926).

The label stood in the subject only; a mail program that shows the subject
differently hid it (a sign-in mail from HDEV, read as if it had no label). Now the
body says it too, at the top of the HTML part of every mail, and of the plain part
where one exists today — no plain part is added.

A mail is built in four places, each with its own structure, so each gets its own
test (the one build function is #1924's): the plain send, the campaign mail (plain
optional), the mail with attachments, and the retry from the log.

Per place, on a test environment the line stands once and above everything else;
on production the parts are what they were, byte for byte, and the subject has no
label. Broken on purpose: the call removed from one place → that place's test is
red and no other.
"""

import email
import re
import smtplib

import pytest

from app.domains.mail import handlers
from app.domains.mail import service as mail
from app.domains.mail.models import EmailLog

TEST_ENVIRONMENTS = [("dev", "DEV"), ("hdev", "HDEV"), ("uat", "UAT")]
PRODUCTION = ["prod", ""]
LINE = "Dit bericht komt van de testomgeving {label}."


class _Smtp:
    sent: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, *a):
        pass

    def sendmail(self, _from, _to, raw):
        _Smtp.sent.append(raw)


@pytest.fixture
def smtp(monkeypatch):
    """The messages that reach SMTP, as the raw strings the server would get."""
    _Smtp.sent = []
    monkeypatch.setattr(mail.settings, "gmail_user", "sender@example.com")
    monkeypatch.setattr(mail.settings, "gmail_app_password", "pw")
    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: _Smtp())
    return _Smtp.sent


def _parts(raw: str) -> tuple[str, dict[str, str]]:
    """The subject and the text of every leaf part by content type; an
    attachment is left out."""
    message = email.message_from_string(raw)
    parts = {
        part.get_content_type(): part.get_payload(decode=True).decode()
        for part in message.walk()
        if part.get_content_maintype() == "text" and part.get_filename() is None
    }
    return message["Subject"], parts


def _without_the_line(shown: str) -> str:
    """The HTML part with the environment's paragraph taken out again."""
    start = shown.index("<p style")
    return shown[:start] + shown[shown.index("</p>", start) + 4 :]


def _send_plain():
    mail._send("to@example.com", "Onderwerp", "<p>Hallo</p>")
    return "<p>Hallo</p>", None


def _send_campaign():
    html = "<html><body><p>Brief</p></body></html>"
    mail.send_campaign_mail(
        "to@example.com", "Onderwerp", html, email_type="other", body_text="Brief in tekst"
    )
    return html, "Brief in tekst"


def _send_campaign_without_text():
    mail.send_campaign_mail("to@example.com", "Onderwerp", "<p>Brief</p>", email_type="other")
    return "<p>Brief</p>", None


def _send_attachments():
    mail.send_with_attachments(
        to_emails=["a@example.com", "b@example.com"],
        subject="Onderwerp",
        body_html="<p>Notulen</p>",
        attachments=[("notulen.txt", "text/plain", b"bijlage")],
    )
    return "<p>Notulen</p>", None


def _retry_from_the_log(db_session):
    row = EmailLog(
        recipient="to@example.com",
        subject="Onderwerp",
        email_type="other",
        status="failed",
        body="<p>Eerder</p>",
    )
    db_session.add(row)
    db_session.flush()
    handlers.retry_mail(db_session, {"email_log_id": row.id})
    return "<p>Eerder</p>", None


PLACES = {
    "plain send": lambda db: _send_plain(),
    "campaign mail with a text part": lambda db: _send_campaign(),
    "campaign mail without one": lambda db: _send_campaign_without_text(),
    "mail with attachments": lambda db: _send_attachments(),
    "retry from the log": _retry_from_the_log,
}


@pytest.mark.parametrize("place", list(PLACES))
@pytest.mark.parametrize("env, label", TEST_ENVIRONMENTS)
def test_on_a_test_environment_the_line_stands_once_above_everything(
    place, env, label, smtp, db_session, monkeypatch
):
    monkeypatch.setattr(mail.settings, "app_env", env)
    html, text = PLACES[place](db_session)

    assert len(smtp) == 1, "the mail did not reach SMTP"
    subject, parts = _parts(smtp[0])
    line = LINE.format(label=label)
    assert subject == f"[{label}] Onderwerp"
    shown = parts["text/html"]
    assert shown.count(line) == 1, "the line stands once in the HTML part"
    own = re.search(r"<p>(\w+)</p>", html).group(1)
    assert shown.index(line) < shown.index(own), "the line stands above the mail's own text"
    assert _without_the_line(shown) == html, "the mail's own HTML is untouched"
    if text is None:
        assert "text/plain" not in parts, "a plain part was added where there was none"
    else:
        assert parts["text/plain"] == f"{line}\n\n{text}", "the line is the first of the text"


@pytest.mark.parametrize("place", list(PLACES))
@pytest.mark.parametrize("env", PRODUCTION)
def test_on_production_every_part_is_what_it_was(place, env, smtp, db_session, monkeypatch):
    """Broken on purpose: `_env_line` made to return a sentence whatever the
    environment → every part differs and this fails."""
    monkeypatch.setattr(mail.settings, "app_env", env)
    html, text = PLACES[place](db_session)

    subject, parts = _parts(smtp[0])
    assert subject == "Onderwerp"
    assert parts["text/html"] == html, "the HTML part is not byte for byte what it was"
    if text is None:
        assert "text/plain" not in parts
    else:
        assert parts["text/plain"] == text, "the plain part is not byte for byte what it was"
    assert "testomgeving" not in smtp[0]


def test_a_whole_document_gets_the_line_inside_its_body(monkeypatch):
    """A newsletter is a whole document: the line stands right after `<body>`, so
    the browser and the mail program read it as the first of the page."""
    monkeypatch.setattr(mail.settings, "app_env", "uat")
    document = '<!DOCTYPE html><html><head><title>t</title></head><BODY class="x"><p>Brief</p></BODY></html>'
    shown = mail.with_env_line_html(document)

    line = LINE.format(label="UAT")
    assert shown.count(line) == 1
    assert shown.index('<BODY class="x">') + len('<BODY class="x">') < shown.index(line)
    assert shown.index(line) < shown.index("<p>Brief</p>")
    assert shown.startswith("<!DOCTYPE html><html><head>")
    assert _without_the_line(shown) == document


def test_the_line_and_the_subject_prefix_come_from_one_label(monkeypatch):
    for env, label in TEST_ENVIRONMENTS:
        monkeypatch.setattr(mail.settings, "app_env", env)
        assert mail._env_prefix() == f"[{label}] "
        assert label in mail._env_line()
    monkeypatch.setattr(mail.settings, "app_env", "prod")
    assert mail._env_prefix() == "" and mail._env_line() == ""
