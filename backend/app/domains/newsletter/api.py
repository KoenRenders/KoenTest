"""Public facade of the newsletter component (CR-05, #984).

Other components import newsletter functionality only through this module
(boundary test: cross-domain only via ``.api``).
"""
from app.domains.newsletter.models import (  # noqa: F401
    AUDIENCE_BOTH,
    AUDIENCE_MEMBERS,
    AUDIENCE_NON_MEMBERS,
    AUDIENCES,
    Delivery,
    DraftingMessage,
    Newsletter,
    Subscriber,
)
from app.domains.newsletter.service import (  # noqa: F401
    NewsletterError,
    audience_counts,
    member_addresses,
    recipients_for,
)

__all__ = [
    "AUDIENCE_BOTH", "AUDIENCE_MEMBERS", "AUDIENCE_NON_MEMBERS", "AUDIENCES",
    "Delivery", "DraftingMessage", "Newsletter", "Subscriber",
    "NewsletterError", "audience_counts", "member_addresses", "recipients_for",
]
