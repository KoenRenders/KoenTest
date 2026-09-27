"""The code lists the mail domain owns (CR-12 phase 4).

Two lists that were module tuples: the e-mail type and the mail status. The
Dutch words are taken literally from the two dictionaries `mail/ui.py` used
until now (§B8.5: the same words as before). Four codes had no word there and
reached the screen raw — `meeting`, `newsletter`, `newsletter_confirmation`
and the status `logged` — so theirs are new: from the §B5.3 catalogue where it
has one, written here where it has none.
"""
from app.domains.mail.models import (
    EmailType,
    EmailTypeCode,
    EmailTypeLabel,
    MailStatus,
    MailStatusCode,
    MailStatusLabel,
)
from app.kernel.codes import CodeList, CodeSeed

EMAIL_TYPE_CODES = (
    CodeSeed(code="membership_confirmation", nl="Lidmaatschap", en="Membership",
             sort_order=10),
    CodeSeed(code="activity_confirmation", nl="Activiteit", en="Activity",
             sort_order=20),
    CodeSeed(code="idea_ack", nl="Idee (bevestiging)", en="Idea (acknowledgement)",
             sort_order=30),
    CodeSeed(code="idea_board", nl="Idee (bestuur)", en="Idea (board)",
             sort_order=40),
    CodeSeed(code="magic_link", nl="Inloglink", en="Login link", sort_order=50),
    CodeSeed(code="member_contact_notice", nl="Contactbericht", en="Contact notice",
             sort_order=60),
    CodeSeed(code="form_confirmation", nl="Formulier (bevestiging)",
             en="Form (confirmation)", sort_order=70),
    CodeSeed(code="meeting", nl="Vergadering", en="Meeting", sort_order=80),
    CodeSeed(code="newsletter", nl="Nieuwsbrief", en="Newsletter", sort_order=90),
    CodeSeed(code="newsletter_confirmation", nl="Nieuwsbrief (bevestiging)",
             en="Newsletter (confirmation)", sort_order=100),
    CodeSeed(code="other", nl="Overig", en="Other", sort_order=110),
)

EMAIL_TYPE = CodeList(
    name="email_type", schema="mail",
    codes=EmailTypeCode, labels=EmailTypeLabel, enum=EmailType,
    fk_from=("mail.email_log.email_type",),
)

MAIL_STATUS_CODES = (
    CodeSeed(code="sent", nl="Verstuurd", en="Sent", sort_order=10),
    CodeSeed(code="failed", nl="Mislukt", en="Failed", sort_order=20),
    CodeSeed(code="skipped", nl="Overgeslagen", en="Skipped", sort_order=30),
    CodeSeed(code="logged", nl="Enkel gelogd", en="Logged only", sort_order=40),
)

MAIL_STATUS = CodeList(
    name="mail_status", schema="mail",
    codes=MailStatusCode, labels=MailStatusLabel, enum=MailStatus,
    fk_from=("mail.email_log.status",),
)
