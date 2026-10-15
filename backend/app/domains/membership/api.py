"""Publieke facade van het membership-component (fase 4a, #402).

De geldigheidsregel ("mag deze persoon de ledenprijs?") en het
hernieuwingsvenster leven hier op één plek (§19.3); andere componenten en de
oude wereld gaan uitsluitend via deze module.
"""

# The one rule for the relation of a new person lives with the household
# (`mdm`, #1603); it stays reachable here for the callers that knew it here.
from app.domains.mdm.api import default_relation  # noqa: F401
from app.domains.membership.history import snapshot_membership
from app.domains.membership.models import Membership, MembershipHistory  # noqa: F401
from app.domains.membership.payables import membership_describer  # noqa: E402, F401
from app.domains.membership.schemas_member import (  # noqa: F401
    MembershipCreate,
    PostalCodeResponse,
)
from app.domains.membership.service import (  # noqa: F401
    current_membership_counts,
    has_membership_for_year,
    has_valid_membership,
    household_payment_state,
    is_first_membership,
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
    valid_membership_until,
)

# The two ways to pay a membership, for a screen that reads the choice (#1899).
from app.domains.membership.signup_form import PAYMENT_METHODS  # noqa: F401

__all__ = [
    "snapshot_membership",
    "membership_describer",
    "Membership",
    "MembershipHistory",
    "has_valid_membership",
    "household_payment_state",
    "is_member",
    "membership_coverage_until",
    "has_membership_for_year",
    "is_first_membership",
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
    "create_family_by_admin",
    "create_family_with_members",
    "FamilyCreate",
    "FamilyMemberCreate",
    "create_membership_for_family",
    "delete_membership",
    "remove_memberships",
    "board_household_group",
    "new_household_group",
    "new_household_from_form",
    "household_view_by_id",
    "family_label",
    "get_family",
    "list_families",
    # Schemas (#444)
    "MembershipCreate",
    "PostalCodeResponse",
]


# ── The person block for one person (CR-22 S6a, #1710) ───────────────────────


def person_block(person, codes, *, short_date, edit=False):
    """The person block of Mijn gezin for this one person, for a page of their
    own (Mijn gegevens)."""
    from app.domains.membership.household_page import person_block as _impl

    return _impl(person, codes, short_date=short_date, edit=edit)


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
# De implementaties staan in `portal_service.py`: net als bij de
# activiteiteninschrijving roept het scherm één domeinbewerking aan en doet het
# zelf niets. Alleen de weg ernaartoe loopt nu via de facade (#635 I).


def new_household_group(codes: dict):
    """An empty household to fill in, as Word lid shows it — for the board's
    Nieuw lid (#1899): the main member's card, the address, a card per person."""
    from app.domains.membership.household_page import signup_group

    return signup_group(codes)


def new_household_from_form(form):
    """The household the board's Nieuw lid asks to create, or what stands in its
    way — Word lid's reader, without the payment choice."""
    from app.domains.membership.signup_form import signup_from_form

    return signup_from_form(form, payment=False)


def board_household_group(db, household_id: int, codes: dict, *, short_date, edit: bool = False):
    """The household as the board's record shows it (#1899): the same group of
    person cards as Mijn gezin, for a reader who is no person of it — every
    other person may go, and a waiting address offers no code."""
    from app.domains.membership.household_page import household_group

    return household_group(
        household_view_by_id(db, household_id),
        codes,
        me=None,
        short_date=short_date,
        edit=edit,
        own_codes=False,
    )


def household_view_by_id(db, household_id: int):
    """The household with this id, as the portal shows it — for the board's record."""
    from app.domains.membership.portal_service import get_household_by_id as _impl

    return _impl(db, household_id)


def household_view(db, person):
    """Het gezin van de ingelogde persoon, zoals het portaal het toont."""
    from app.domains.membership.portal_service import get_household as _impl

    return _impl(person=person, db=db)


def household_member_for(db, person):
    """Het gezin waar deze persoon toe behoort, of een fout als dat er niet is."""
    from app.domains.membership.portal_service import _member_for

    return _member_for(person, db)


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


def board_membership_card(db, household_id: int):
    """The membership card of the household with this id, for the board's record
    (#1899): is a renewal available, and does one run. None when the household
    has no main member — a renewal runs for the main member."""
    from app.domains.membership.portal_service import main_person_of

    person = main_person_of(db, household_id)
    return membership_card(db, person) if person is not None else None


def renewal_is_mailed(db, household_id: int) -> bool:
    """Does the confirmation of a renewal reach this household (#1903)? False
    when its main member has no confirmed e-mail address: the board's record
    says so beside a running renewal."""
    from app.domains.membership.portal_service import renewal_mail_address

    return renewal_mail_address(db, household_id) is not None


def board_renewal_page(db, household_id: int, codes: dict):
    """The renewal page as the board sees it for this household (#1899): the
    page of the public renewal, speaking of the household. None when there is
    nothing to start — no main member, no renewal available, or one that runs:
    the record says which."""
    from datetime import date

    from app.domains.membership.household_page import RenewPage, Terms, household_summary
    from app.domains.membership.portal_service import main_person_of

    person = main_person_of(db, household_id)
    if person is None or renewal_is_running(db, person):
        return None
    valid_until = membership_coverage_until(person)
    if not renewal_available(valid_until, date.today()):
        return None
    _from, until, amount = renewal_terms(db, person)
    summary, address_line = household_summary(household_view(db, person), codes)
    record = f"/admin/leden/gezin/{household_id}"
    return RenewPage(
        valid_until=valid_until,
        renewal_available=True,
        terms=Terms(amount=amount, valid_to=until),
        summary=summary,
        address_line=address_line,
        board=True,
        post_url=f"{record}/vernieuwen",
        household_href=record,
    )


def board_renew_membership(db, household_id: int, payment_method: str, *, by: str):
    """The board renews this household's membership (#1899): the one renewal of
    `household_renew_membership`, for the main member, with the board member in
    the history and the household's record as the place the provider returns
    to. Refused (409) for a household without a main member."""
    from fastapi import HTTPException

    from app.domains.membership.portal_service import main_person_of
    from app.domains.membership.portal_service import renew_membership as _impl
    from app.i18n import _

    person = main_person_of(db, household_id)
    if person is None:
        raise HTTPException(
            status_code=409, detail=_("Dit gezin heeft geen hoofdlid: vernieuwen kan niet.")
        )
    return _impl(
        person=person,
        db=db,
        payment_method=payment_method,
        by=by,
        return_path=f"/admin/leden/gezin/{household_id}",
    )


def household_renew_membership(db, person, payment_method: str = "online"):
    from app.domains.membership.portal_service import renew_membership as _impl

    return _impl(person=person, db=db, payment_method=payment_method)


def register_family(db, data, background_tasks, *, proof, signed_in=None):
    """Publieke gezinsregistratie — de flow staat in signup_service.

    `signed_in` (CR-22 R9, #1713): the person the visitor is signed in as, or
    None. An account that signs up becomes the main member itself.

    `proof` (#2039): the guard's proof of the visitor's form; see `signup_service`."""
    from app.domains.membership.signup_service import register_family as _impl

    return _impl(data, background_tasks, db=db, signed_in=signed_in, proof=proof)


# ── Onderaan, en dat is opzet ────────────────────────────────────────────────
# These imports were put at the bottom when `audit/service.py` imported
# `MembershipHistory` from this facade at module level: at the top the name was
# not bound yet when that chain came back ("partially initialized module").
# Since CR-13 phase 4c (#1251) `audit/service.py` imports no facade at module
# level, so that reason is gone; the imports stand where they stood — moving
# them up was not part of that change and has not been tried.
# Sinds #635 H expliciet, niet meer via een lazy `__getattr__`-proxy naar
# register_router. Die proxy gaf routerfuncties door als "servicelaag" — HTTP-
# handlers met `Depends` in hun signatuur — en bestond om een importcyclus te
# vermijden. De cyclus is weg nu de implementatie in household_service woont, dat
# zelf geen router importeert.
from app.domains.membership.household_service import (  # noqa: E402, F401 — at the bottom on purpose: audit.service imports MembershipHistory from here at load time (cycle, see above)
    create_family_by_admin,
    create_family_with_members,
    create_membership_for_family,
    delete_membership,
    family_label,
    get_family,
    list_families,
    remove_memberships,
)
from app.domains.membership.schemas_family import (  # noqa: E402, F401 — at the bottom on purpose: audit.service imports MembershipHistory from here at load time (cycle, see above)
    FamilyCreate,
    FamilyMemberCreate,
)
