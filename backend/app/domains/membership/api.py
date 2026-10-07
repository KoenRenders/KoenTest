"""Publieke facade van het membership-component (fase 4a, #402).

De geldigheidsregel ("mag deze persoon de ledenprijs?") en het
hernieuwingsvenster leven hier op één plek (§19.3); andere componenten en de
oude wereld gaan uitsluitend via deze module.
"""

# The one rule for the relation of a new person lives with the household
# (`mdm`, #1603); it stays reachable here for the callers that knew it here.
from app.domains.mdm.api import default_relation  # noqa: F401
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
    current_membership_counts,
    has_valid_membership,
    household_payment_state,
    is_member,
    members_valid_on,
    members_with_membership_for_year,
    membership_coverage_until,
    membership_years,
    new_members_between,
    not_renewed_count,
    open_renewal_payment,
    renewal_available,
    renewal_open,
    renewal_terms,
    renewal_years,
    set_relation_type,
    valid_membership_until,
)

__all__ = [
    "Membership",
    "MembershipHistory",
    "has_valid_membership",
    "household_payment_state",
    "is_member",
    "membership_coverage_until",
    "open_renewal_payment",
    "members_valid_on",
    "current_membership_counts",
    "default_relation",
    "members_with_membership_for_year",
    "membership_years",
    "new_members_between",
    "not_renewed_count",
    "renewal_years",
    "renewal_available",
    "renewal_open",
    "renewal_terms",
    "valid_membership_until",
    # Schrijfbewerkingen op gezinnen/personen/lidmaatschappen (#635 H)
    "add_person_to_family",
    "assign_board_member",
    "create_member",
    "create_family_by_admin",
    "create_family_with_members",
    "parse_member_rows",
    "FamilyCreate",
    "FamilyMemberCreate",
    "create_membership_for_family",
    "delete_family",
    "delete_membership",
    "delete_person",
    "family_label",
    "get_family",
    "list_families",
    "update_person",
    "update_person_address",
    "update_person_contacts",
    # Schemas (#444)
    "AddressUpdate",
    "BoardMemberAssign",
    "ContactsUpdate",
    "MemberCreate",
    "MembershipCreate",
    "PersonAddToFamily",
    "PersonCreate",
    "PersonUpdate",
    "PostalCodeResponse",
]


# ── The person block for one person (CR-22 S6a, #1710) ───────────────────────


def person_block(person, *, edit=False):
    """The person block of Mijn gezin for this one person, for a page of their
    own (Mijn gegevens)."""
    from app.domains.membership.household_page import person_block as _impl

    return _impl(person, edit=edit)


# ── The membership card (CR-22 S2, #1705) ────────────────────────────────────
# One view-model for every place that shows how a membership stands.


def membership_card(db, person, *, household=None):
    """The membership card of the household `person` belongs to."""
    from app.domains.membership.membership_card import membership_card as _impl

    return _impl(db, person, household=household)


def renewal_is_running(db, person) -> bool:
    """Does a renewal of this person's household wait for its payment?"""
    from app.domains.membership.membership_card import renewal_is_running as _impl

    return _impl(db, person)


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


def household_add_email(db, person, person_id: int, email: str):
    from app.domains.membership.household_router import household_add_email as _impl

    return _impl(person_id, {"email": email}, person=person, db=db)


def household_apply_email_rows(db, person, person_id: int, formulier):
    from app.domains.membership.household_router import household_apply_email_rows as _impl

    return _impl(person_id, formulier, person=person, db=db)


def household_make_email_primary(db, person, person_id: int, contact_id: int):
    from app.domains.membership.household_router import household_make_email_primary as _impl

    return _impl(person_id, contact_id, person=person, db=db)


def household_remove_email(db, person, person_id: int, contact_id: int):
    from app.domains.membership.household_router import household_remove_email as _impl

    return _impl(person_id, contact_id, person=person, db=db)


def portal_member(request, db):
    """The member logged in on the family portal, with the CSRF check of a mutation;
    a 401 without one. For a door of another domain on the portal (CR-13 phase 3)."""
    from app.domains.membership.ui import _require_member_csrf

    return _require_member_csrf(request, db)


def family_portal_page(request, db, person):
    """The family portal as it stands — what a door of another domain that changed
    something on it answers with (CR-13 phase 3: the person mutations are `mdm`'s,
    the screen stays `membership`'s)."""
    from app.domains.membership.ui import render_family_portal

    return render_family_portal(request, db, person)


def household_renew_membership(db, person, payment_method: str = "online"):
    from app.domains.membership.household_router import renew_membership as _impl

    return _impl(person=person, db=db, payment_method=payment_method)


def register_family(db, data, background_tasks, *, signed_in=None):
    """Publieke gezinsregistratie — de flow blijft in register_router.

    `signed_in` (CR-22 R9, #1713): the person the visitor is signed in as, or
    None. An account that signs up becomes the main member itself."""
    from app.domains.membership.register_router import register_family as _impl

    return _impl(data, background_tasks, db=db, signed_in=signed_in)


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
from app.domains.membership.household_service import (  # noqa: E402, F401 — at the bottom on purpose: audit.service imports MembershipHistory from here at load time (cycle, see above)
    add_person_to_family,
    assign_board_member,
    create_family_by_admin,
    create_family_with_members,
    create_member,
    create_membership_for_family,
    delete_family,
    delete_membership,
    delete_person,
    family_label,
    get_family,
    list_families,
    update_person,
    update_person_address,
    update_person_contacts,
)
from app.domains.membership.schemas_family import (  # noqa: E402, F401 — at the bottom on purpose: audit.service imports MembershipHistory from here at load time (cycle, see above)
    FamilyCreate,
    FamilyMemberCreate,
)
from app.domains.membership.service import (  # noqa: E402, F401 — at the bottom on purpose: audit.service imports MembershipHistory from here at load time (cycle, see above)
    parse_member_rows,
)
