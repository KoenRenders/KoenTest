"""The attributes of the `newsletter` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="newsletter.delivery.email",
        columns=("newsletter.deliveries.email",),
        label=None,
        name_en="Email",
        help="The email of the delivery.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="newsletter.delivery.kind",
        columns=("newsletter.deliveries.kind",),
        label=None,
        name_en="Kind",
        help="The kind of the delivery, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="newsletter.delivery.status",
        columns=("newsletter.deliveries.status",),
        label=None,
        name_en="Status",
        help="The status of the delivery, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="newsletter.delivery.sent_at",
        columns=("newsletter.deliveries.sent_at",),
        label=None,
        name_en="Sent at",
        help="The sent at of the delivery.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="newsletter.delivery.error",
        columns=("newsletter.deliveries.error",),
        label=None,
        name_en="Error",
        help="The error of the delivery.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="newsletter.drafting_message.role",
        columns=("newsletter.drafting_messages.role",),
        label=None,
        name_en="Role",
        help="The role of the drafting message, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="newsletter.drafting_message.text",
        columns=("newsletter.drafting_messages.text",),
        label=None,
        name_en="Text",
        help="The text of the drafting message.",
        ai_exposure=AiExposure.INTERNAL,  # K7
    ),
    Attribute(
        key="newsletter.drafting_message.proposal",
        columns=("newsletter.drafting_messages.proposal",),
        label=None,
        name_en="Proposal",
        help="The proposal of the drafting message.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="newsletter.newsletter.subject",
        columns=("newsletter.newsletters.subject",),
        label=None,
        name_en="Subject",
        help="The subject of the newsletter.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="newsletter.newsletter.preview_text",
        columns=("newsletter.newsletters.preview_text",),
        label=None,
        name_en="Preview text",
        help="The preview text of the newsletter.",
        ai_exposure=AiExposure.INTERNAL,  # K7
    ),
    Attribute(
        key="newsletter.newsletter.body_document",
        columns=("newsletter.newsletters.body_document",),
        label=None,
        name_en="Body",
        help="The text of the newsletter, as a document of the page editor.",
        ai_exposure=AiExposure.INTERNAL,  # K7
    ),
    Attribute(
        key="newsletter.newsletter.audience",
        columns=("newsletter.newsletters.audience",),
        label=None,
        name_en="Audience",
        help="The audience of the newsletter, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="newsletter.newsletter.status",
        columns=("newsletter.newsletters.status",),
        label=None,
        name_en="Status",
        help="The status of the newsletter, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="newsletter.newsletter.created_by",
        columns=("newsletter.newsletters.created_by",),
        label=None,
        name_en="Created by",
        help="The created by of the newsletter.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="newsletter.newsletter.draft_activity_ids",
        columns=("newsletter.newsletters.draft_activity_ids",),
        label=None,
        name_en="Draft activity ids",
        help="The draft activity ids of the newsletter.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="newsletter.newsletter.draft_meeting_ids",
        columns=("newsletter.newsletters.draft_meeting_ids",),
        label=None,
        name_en="Draft meeting ids",
        help="The draft meeting ids of the newsletter.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="newsletter.newsletter.reply_to_mode",
        columns=("newsletter.newsletters.reply_to_mode",),
        label=None,
        name_en="Reply to mode",
        help="The reply to mode of the newsletter, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="newsletter.newsletter.reply_to_address",
        columns=("newsletter.newsletters.reply_to_address",),
        label=None,
        name_en="Reply to address",
        help="The reply to address of the newsletter.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="newsletter.newsletter.link_base",
        columns=("newsletter.newsletters.link_base",),
        label=None,
        name_en="Link base",
        help="The link base of the newsletter.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="newsletter.newsletter.sent_by",
        columns=("newsletter.newsletters.sent_by",),
        label=None,
        name_en="Sent by",
        help="The sent by of the newsletter.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="newsletter.newsletter.send_started_at",
        columns=("newsletter.newsletters.send_started_at",),
        label=None,
        name_en="Send started at",
        help="The send started at of the newsletter.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="newsletter.newsletter.send_finished_at",
        columns=("newsletter.newsletters.send_finished_at",),
        label=None,
        name_en="Send finished at",
        help="The send finished at of the newsletter.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="newsletter.newsletter.paused_until",
        columns=("newsletter.newsletters.paused_until",),
        label=None,
        name_en="Paused until",
        help="The paused until of the newsletter.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="newsletter.subscriber.email",
        columns=("newsletter.subscribers.email",),
        label=None,
        name_en="Email",
        help="The email of the subscriber.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="newsletter.subscriber.first_name",
        columns=("newsletter.subscribers.first_name",),
        label=None,
        name_en="First name",
        help="The first name of the subscriber.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="newsletter.subscriber.status",
        columns=("newsletter.subscribers.status",),
        label=None,
        name_en="Status",
        help="The status of the subscriber, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="newsletter.subscriber.source",
        columns=("newsletter.subscribers.source",),
        label=None,
        name_en="Source",
        help="The source of the subscriber, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="newsletter.subscriber.consented_at",
        columns=("newsletter.subscribers.consented_at",),
        label=None,
        name_en="Consented at",
        help="The consented at of the subscriber.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="newsletter.subscriber.confirmed_at",
        columns=("newsletter.subscribers.confirmed_at",),
        label=None,
        name_en="Confirmed at",
        help="The confirmed at of the subscriber.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="newsletter.subscriber.unsubscribed_at",
        columns=("newsletter.subscribers.unsubscribed_at",),
        label=None,
        name_en="Unsubscribed at",
        help="The unsubscribed at of the subscriber.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="newsletter.subscriber.imported_at",
        columns=("newsletter.subscribers.imported_at",),
        label=None,
        name_en="Imported at",
        help="The imported at of the subscriber.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="newsletter.subscriber.confirm_sent_at",
        columns=("newsletter.subscribers.confirm_sent_at",),
        label=None,
        name_en="Confirm sent at",
        help="The confirm sent at of the subscriber.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="newsletter.subscriber.confirm_token",
        columns=("newsletter.subscribers.confirm_token",),
        label=None,
        name_en="Confirm token",
        help="The confirm token of the subscriber.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="newsletter.subscriber.unsubscribe_token",
        columns=("newsletter.subscribers.unsubscribe_token",),
        label=None,
        name_en="Unsubscribe token",
        help="The unsubscribe token of the subscriber.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="newsletter.subscriber.person_id",
        columns=("newsletter.subscribers.person_id",),
        label=None,
        name_en="Person id",
        help="The person id of the subscriber.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
)
