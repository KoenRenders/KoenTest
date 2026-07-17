"""Publieke facade van het membership-component (fase 4a, #402).

De geldigheidsregel ("mag deze persoon de ledenprijs?") en het
hernieuwingsvenster leven hier op één plek (§19.3); andere componenten en de
oude wereld gaan uitsluitend via deze module.
"""
from app.domains.membership.models import Membership, MembershipHistory  # noqa: F401
from app.domains.membership.schemas_member import (  # noqa: F401
    AddressUpdate,
    BoardMemberAssign,
    ContactsUpdate,
    MembershipCreate,
    PersonAddToFamily,
    PersonUpdate,
    PostalCodeResponse,
)
from app.domains.membership.service import (  # noqa: F401
    has_valid_membership,
    is_member,
    membership_coverage_until,
    renewal_available,
    renewal_open,
    valid_membership_until,
)

_ROUTER_FUNCS = (
    "add_person_to_family", "assign_board_member", "create_membership_for_family",
    "delete_family", "delete_membership", "delete_person", "get_family",
    "list_families", "update_person", "update_person_address",
    "update_person_contacts",
)


def __getattr__(name: str):
    # Lazy om een importcyclus te vermijden: register_router importeert
    # payment.api, dat via payment.service weer deze facade importeert (#444).
    if name in _ROUTER_FUNCS:
        from app.domains.membership import register_router
        return getattr(register_router, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Membership", "MembershipHistory",
    "has_valid_membership", "is_member", "membership_coverage_until",
    "renewal_available", "renewal_open", "valid_membership_until",
    # Router-functies hergebruikt als servicelaag door mdm-schermen (#444)
    "add_person_to_family", "assign_board_member", "create_membership_for_family",
    "delete_family", "delete_membership", "delete_person", "get_family",
    "list_families", "update_person", "update_person_address",
    "update_person_contacts",
    # Schemas (#444)
    "AddressUpdate", "BoardMemberAssign", "ContactsUpdate", "MembershipCreate",
    "PersonAddToFamily", "PersonUpdate", "PostalCodeResponse",
]
