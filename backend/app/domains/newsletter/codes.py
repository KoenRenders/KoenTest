"""The code lists the newsletter domain owns (CR-12 fase 3).

Eight lists, all of them module constants until this phase: a tuple with the
valid values in `models.py`, and twenty lines further on in another file a
dictionary with the Dutch words. One shape now, and therefore one place where
a new value is added.
"""
from app.domains.newsletter.models import (
    Audience,
    AudienceCode,
    AudienceLabel,
    DeliveryKind,
    DeliveryKindCode,
    DeliveryKindLabel,
    DeliveryStatus,
    DeliveryStatusCode,
    DeliveryStatusLabel,
    LetterStatus,
    LetterStatusCode,
    LetterStatusLabel,
    MessageRole,
    MessageRoleCode,
    MessageRoleLabel,
    ReplyToMode,
    ReplyToModeCode,
    ReplyToModeLabel,
    SubscriberSource,
    SubscriberSourceCode,
    SubscriberSourceLabel,
    SubscriberStatus,
    SubscriberStatusCode,
    SubscriberStatusLabel,
)
from app.kernel.codes import CodeList, CodeSeed

SUBSCRIBER_STATUS_CODES = (
    CodeSeed(code="pending", nl="Wacht op bevestiging",
             en="Awaiting confirmation", sort_order=10),
    CodeSeed(code="confirmed", nl="Bevestigd", en="Confirmed", sort_order=20),
    CodeSeed(code="unsubscribed", nl="Uitgeschreven", en="Unsubscribed",
             sort_order=30),
)

SUBSCRIBER_STATUS = CodeList(
    name="subscriber_status", schema="newsletter",
    codes=SubscriberStatusCode, labels=SubscriberStatusLabel,
    enum=SubscriberStatus,
    fk_from=("newsletter.subscribers.status",),
)

SUBSCRIBER_SOURCE_CODES = (
    CodeSeed(code="public_form", nl="Formulier", en="Form", sort_order=10),
    CodeSeed(code="import", nl="Import", en="Import", sort_order=20),
    CodeSeed(code="admin", nl="Beheer", en="Admin", sort_order=30),
)

SUBSCRIBER_SOURCE = CodeList(
    name="subscriber_source", schema="newsletter",
    codes=SubscriberSourceCode, labels=SubscriberSourceLabel,
    enum=SubscriberSource,
    fk_from=("newsletter.subscribers.source",),
)

AUDIENCE_CODES = (
    CodeSeed(code="members", nl="Leden", en="Members", sort_order=10),
    CodeSeed(code="non_members", nl="Niet-leden", en="Non-members",
             sort_order=20),
    CodeSeed(code="both", nl="Allebei", en="Both", sort_order=30),
)

AUDIENCE = CodeList(
    name="audience", schema="newsletter",
    codes=AudienceCode, labels=AudienceLabel, enum=Audience,
    fk_from=("newsletter.newsletters.audience",),
)

LETTER_STATUS_CODES = (
    CodeSeed(code="draft", nl="Concept", en="Draft", sort_order=10),
    CodeSeed(code="sending", nl="Wordt verstuurd", en="Sending", sort_order=20),
    CodeSeed(code="sent", nl="Verstuurd", en="Sent", sort_order=30),
)

LETTER_STATUS = CodeList(
    name="letter_status", schema="newsletter",
    codes=LetterStatusCode, labels=LetterStatusLabel, enum=LetterStatus,
    fk_from=("newsletter.newsletters.status",),
)

REPLY_TO_MODE_CODES = (
    CodeSeed(code="association", nl="Vereniging", en="Association",
             sort_order=10),
    CodeSeed(code="sender", nl="Afzender", en="Sender", sort_order=20),
)

REPLY_TO_MODE = CodeList(
    name="reply_to_mode", schema="newsletter",
    codes=ReplyToModeCode, labels=ReplyToModeLabel, enum=ReplyToMode,
    fk_from=("newsletter.newsletters.reply_to_mode",),
)

DELIVERY_KIND_CODES = (
    CodeSeed(code="member", nl="Lid", en="Member", sort_order=10),
    CodeSeed(code="subscriber", nl="Abonnee", en="Subscriber", sort_order=20),
)

DELIVERY_KIND = CodeList(
    name="delivery_kind", schema="newsletter",
    codes=DeliveryKindCode, labels=DeliveryKindLabel, enum=DeliveryKind,
    fk_from=("newsletter.deliveries.kind",),
)

DELIVERY_STATUS_CODES = (
    CodeSeed(code="queued", nl="In de wachtrij", en="Queued", sort_order=10),
    CodeSeed(code="sent", nl="Verstuurd", en="Sent", sort_order=20),
    CodeSeed(code="failed", nl="Mislukt", en="Failed", sort_order=30),
    CodeSeed(code="skipped", nl="Overgeslagen", en="Skipped", sort_order=40),
)

DELIVERY_STATUS = CodeList(
    name="delivery_status", schema="newsletter",
    codes=DeliveryStatusCode, labels=DeliveryStatusLabel, enum=DeliveryStatus,
    fk_from=("newsletter.deliveries.status",),
)

MESSAGE_ROLE_CODES = (
    CodeSeed(code="author", nl="Auteur", en="Author", sort_order=10),
    CodeSeed(code="raakje", nl="Raakje", en="Raakje", sort_order=20),
)

MESSAGE_ROLE = CodeList(
    name="message_role", schema="newsletter",
    codes=MessageRoleCode, labels=MessageRoleLabel, enum=MessageRole,
    fk_from=("newsletter.drafting_messages.role",),
)
