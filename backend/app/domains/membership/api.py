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
    MemberCreate,
    MembershipCreate,
    PersonAddToFamily,
    PersonCreate,
    PersonUpdate,
    PostalCodeResponse,
)
from app.domains.membership.service import (  # noqa: F401
    has_valid_membership,
    members_valid_on,
    members_with_membership_for_year,
    not_renewed_count,
    renewal_years,
    is_member,
    membership_coverage_until,
    open_renewal_payment,
    renewal_available,
    renewal_open,
    set_relation_type,
    valid_membership_until,
)



__all__ = [
    "Membership", "MembershipHistory",
    "has_valid_membership", "is_member", "membership_coverage_until",
    "open_renewal_payment",
    "members_valid_on", "members_with_membership_for_year",
    "not_renewed_count", "renewal_years",
    "renewal_available", "renewal_open", "valid_membership_until",
    # Schrijfbewerkingen op gezinnen/personen/lidmaatschappen (#635 H)
    "add_person_to_family", "assign_board_member", "create_member",
    "create_membership_for_family", "delete_family", "delete_membership", "delete_person", "get_family",
    "list_families", "update_person", "update_person_address",
    "update_person_contacts",
    # Schemas (#444)
    "AddressUpdate", "BoardMemberAssign", "ContactsUpdate", "MemberCreate",
    "MembershipCreate", "PersonAddToFamily", "PersonCreate", "PersonUpdate",
    "PostalCodeResponse",
]


# ── Onderaan, en dat is opzet ────────────────────────────────────────────────
# `audit/service.py` importeert op modulniveau `MembershipHistory` uit déze
# facade. Staat de import hieronder bovenaan, dan is die naam nog niet gebonden
# wanneer die keten terugkomt en klapt het op een "partially initialized module".
# Onderaan is `MembershipHistory` er wél. Zo lost de cyclus zichzelf op, zonder de
# lazy proxy die #635 H juist wegneemt.
# Sinds #635 H expliciet, niet meer via een lazy `__getattr__`-proxy naar
# register_router. Die proxy gaf routerfuncties door als "servicelaag" — HTTP-
# handlers met `Depends` in hun signatuur — en bestond om een importcyclus te
# vermijden. De cyclus is weg nu de implementatie in household_service woont, dat
# zelf geen router importeert.
from app.domains.membership.household_service import (  # noqa: F401
    add_person_to_family,
    assign_board_member,
    create_member,
    create_membership_for_family,
    delete_family,
    delete_membership,
    delete_person,
    get_family,
    list_families,
    update_person,
    update_person_address,
    update_person_contacts,
)
