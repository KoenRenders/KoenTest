"""A test environment mails only the addresses on its list (#2034).

``MAIL_ALLOWED_RECIPIENTS`` (comma-separated, case-insensitive, trimmed) limits who a
mail reaches; any other address is not sent but logged as *logged* with the reason, as
``log_only`` logs, so a sign-in link stays readable in the log. Empty or unset: nothing
changes. The tenant's ``log_only`` wins. Every recipient of one mail is checked on its
own. Three places send (the plain send with Cc, the campaign mail, the mail with
attachments), so each has a test.

Broken on purpose: the ``_hold_back`` call removed from ``send_campaign_mail`` → only
``test_the_campaign_mail_is_held_back`` is red; the ``.lower()`` removed from the
comparison → ``test_a_listed_address_in_another_case_is_sent`` is red.
"""

import smtplib

import pytest

from app.domains.mail import service as mail
from app.domains.mail.models import EmailLog, MailStatus

LISTED = "tester@example.com"
OTHER = "someone-else@example.com"
REASON = "niet op de lijst van toegelaten adressen"


class _Smtp:
    envelopes: list[list[str]] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, *a):
        pass

    def sendmail(self, _from, to, raw):
        _Smtp.envelopes.append(list(to))


@pytest.fixture
def smtp(monkeypatch):
    """The envelope recipients of every mail that reaches SMTP."""
    _Smtp.envelopes = []
    monkeypatch.setattr(mail.settings, "gmail_user", "sender@example.com")
    monkeypatch.setattr(mail.settings, "gmail_app_password", "pw")
    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: _Smtp())
    return _Smtp.envelopes


def _allow(monkeypatch, value):
    monkeypatch.setattr(mail.settings, "mail_allowed_recipients", value)


def _log(db_session, recipient):
    return (
        db_session.query(EmailLog)
        .filter(EmailLog.recipient == recipient)
        .order_by(EmailLog.id.desc())
        .first()
    )


def test_a_listed_address_is_sent(smtp, monkeypatch, db_session):
    _allow(monkeypatch, f"{LISTED}, other-tester@example.com")
    mail._send(LISTED, "Hello", "<p>Hi</p>", email_type="other")

    assert smtp == [[LISTED]]
    assert _log(db_session, LISTED).status is MailStatus.SENT


def test_an_unlisted_address_is_logged_with_the_reason_and_not_sent(smtp, monkeypatch, db_session):
    _allow(monkeypatch, LISTED)
    mail._send(OTHER, "Hello", "<p>Sign in: /x</p>", email_type="magic_link")

    assert smtp == []
    row = _log(db_session, OTHER)
    assert row.status is MailStatus.LOGGED
    assert row.error_message == REASON


def test_a_listed_address_in_another_case_is_sent(smtp, monkeypatch, db_session):
    _allow(monkeypatch, "  Tester@Example.COM ")
    mail._send(LISTED, "Hello", "<p>Hi</p>")

    assert smtp == [[LISTED]]


@pytest.mark.parametrize("value", [None, "", "  ", " , "])
def test_an_empty_list_sends_to_everyone(smtp, monkeypatch, value):
    _allow(monkeypatch, value)
    mail._send(OTHER, "Hello", "<p>Hi</p>")

    assert smtp == [[OTHER]]


def test_log_only_wins_over_the_list(smtp, monkeypatch, db_session):
    _allow(monkeypatch, LISTED)
    monkeypatch.setattr(mail, "_mail_mode", lambda: "log_only")
    mail._send(LISTED, "Hello", "<p>Hi</p>")

    assert smtp == []
    row = _log(db_session, LISTED)
    assert row.status is MailStatus.LOGGED and REASON not in str(row.error_message)


def test_cc_is_checked_on_its_own(smtp, monkeypatch, db_session):
    _allow(monkeypatch, LISTED)
    mail._send(LISTED, "Hello", "<p>Hi</p>", cc=OTHER)

    assert smtp == [[LISTED]]
    assert _log(db_session, OTHER).status is MailStatus.LOGGED
    assert _log(db_session, LISTED).status is MailStatus.SENT


def test_the_campaign_mail_is_held_back(smtp, monkeypatch, db_session):
    _allow(monkeypatch, LISTED)
    assert mail.send_campaign_mail(OTHER, "News", "<p>x</p>", email_type="newsletter") == "logged"
    assert smtp == []
    assert _log(db_session, OTHER).status is MailStatus.LOGGED

    assert mail.send_campaign_mail(LISTED, "News", "<p>x</p>", email_type="newsletter") == "sent"
    assert smtp == [[LISTED]]


def test_the_mail_with_attachments_goes_to_the_listed_addresses_only(smtp, monkeypatch, db_session):
    _allow(monkeypatch, LISTED)
    mail.send_with_attachments(
        to_emails=[LISTED, OTHER], subject="Minutes", body_html="<p>x</p>", email_type="other"
    )

    assert smtp == [[LISTED]]
    assert _log(db_session, LISTED).status is MailStatus.SENT
    assert _log(db_session, OTHER).status is MailStatus.LOGGED

    smtp.clear()
    mail.send_with_attachments(to_emails=[OTHER], subject="Minutes", body_html="<p>x</p>")
    assert smtp == []
