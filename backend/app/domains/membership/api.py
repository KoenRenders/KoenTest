"""Publieke facade van het membership-component (fase 4a, #402).

De geldigheidsregel ("mag deze persoon de ledenprijs?") en het
hernieuwingsvenster leven hier op één plek (§19.3); andere componenten en de
oude wereld gaan uitsluitend via deze module.
"""
from app.domains.membership.models import Membership, MembershipHistory  # noqa: F401
from app.domains.membership.service import (  # noqa: F401
    has_valid_membership,
    is_member,
    renewal_available,
    renewal_open,
    valid_membership_until,
)

__all__ = [
    "Membership", "MembershipHistory",
    "has_valid_membership", "is_member", "renewal_available", "renewal_open",
    "valid_membership_until",
]
