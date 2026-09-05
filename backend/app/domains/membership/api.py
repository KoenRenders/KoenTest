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
    membership_years,
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
    "membership_years", "not_renewed_count", "renewal_years",
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


# ── Doorgangen naar het gezinsportaal ────────────────────────────────────────
# De implementaties blijven in `household_router.py`: net als bij de
# activiteiteninschrijving roept het scherm één domeinbewerking aan en doet het
# zelf niets. Alleen de weg ernaartoe loopt nu via de facade (#635 I).

def household_view(db, person):
    """Het gezin van de ingelogde persoon, zoals het portaal het toont."""
    from app.domains.membership.household_router import get_household as _impl

    return _impl(person=person, db=db)


def household_member_for(db, person):
    """Het gezin waar deze persoon toe behoort, of een fout als dat er niet is."""
    from app.domains.membership.household_router import _member_for

    return _member_for(person, db)


def household_update_person(db, person, person_id: int, data):
    from app.domains.membership.household_router import update_person as _impl

    return _impl(person_id, data, person=person, db=db)


def household_add_person(db, person, data):
    from app.domains.membership.household_router import add_person as _impl

    return _impl(data, person=person, db=db)


def household_remove_person(db, person, person_id: int):
    from app.domains.membership.household_router import remove_person as _impl

    return _impl(person_id, person=person, db=db)


def household_renew_membership(db, person, payment_method: str = "online"):
    from app.domains.membership.household_router import renew_membership as _impl

    return _impl(person=person, db=db, payment_method=payment_method)


def register_family(db, data, background_tasks):
    """Publieke gezinsregistratie — de flow blijft in register_router."""
    from app.domains.membership.register_router import register_family as _impl

    return _impl(data, background_tasks, db=db)


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
