"""Events die het MDM-component publiceert (contract, zie mdm/CONTRACT.md)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.kernel.events import KernelEvent
from app.kernel.ports import Port


@dataclass(frozen=True)
class EntityMerged(KernelEvent):
    """Twee masterdata-entiteiten zijn samengevoegd (synchroon, in-transactie).
    Consumenten die id's cachen kunnen hun verwijzing omleggen; soft-refs die
    via ``mdm.api.resolve()`` lezen hoeven niets te doen."""

    entity_type: str  # bv. "person"
    source_id: int  # de opgeslokte entiteit (blijft bestaan, superseded)
    target_id: int  # de overlever


@dataclass(frozen=True)
class TenantCreated(KernelEvent):
    """A tenant was created (CR-19, #1478). Published by `create_tenant` in
    its transaction, after the organisation and its modules are flushed. `cms`
    subscribes and seeds the two site blocks a new site starts with; a
    subscriber that raises undoes the creation."""

    tenant_id: int
    name: str


@dataclass(frozen=True)
class EmailAddressAdded(KernelEvent):
    """An e-mail address a person typed himself waits for its code (CR-22 R15,
    F6; #1711).

    Published by `mdm` in the transaction that stores the row, after its
    flush — the row has its id — and again when its code is asked a second
    time. `auth` subscribes, issues a code with the purpose CONFIRM_ADDRESS and
    asks `mail` for the mail; the mail is a job of that same transaction, so it
    leaves only once the row is committed. Publishing into silence would store
    an address that can never be confirmed, so the publisher checks that
    somebody listens.

    `replaces_id` / `replaces_email`: the confirmed row this address takes the
    place of once its code is entered — the old address stays, and keeps
    signing in, until then (Koen, 8 October 2026). None for an address that is
    simply added, and for a second code: the subscriber then keeps what the
    first code of this row said.

    `make_primary`: the person marked this new address as the primary one in
    the save that added it. A waiting address cannot be that, so the wish
    waits with it and is carried out at the code.
    """

    contact_id: int
    email: str
    replaces_id: Optional[int] = None
    replaces_email: str = ""
    make_primary: bool = False


@dataclass(frozen=True)
class BoardMemberReported(KernelEvent):
    """The member report names this address as a board member's, and the import
    is applied (CR-13 phase 4c, #1251).

    Published by the member import for a board member who has an e-mail address
    and no login yet. `auth` subscribes and gives that address a login with the
    role ADMIN — only a new one; a login that exists is never touched. Until
    phase 4c the import wrote auth's rows itself. Not optional: the import
    refuses to publish when nothing subscribes.
    """

    email: str


@dataclass(frozen=True)
class MembershipReported(KernelEvent):
    """The member report lists this household as a member for this year, and the
    import is applied (CR-13 phase 4c, #1251).

    Published by the member import for a household that has no membership for
    the year. `membership` subscribes and adds it — active, valid for the whole
    year — with its history row; a household that has one keeps it. Until phase
    4c the import wrote membership's rows itself. Not optional: the import
    refuses to publish when nothing subscribes.
    """

    household_id: int
    year: int
    #: What the history row says of where the membership comes from.
    source: str
    actor: Optional[str] = None


@dataclass(frozen=True)
class HouseholdPerson:
    """One person of a household that is created, as the form gave him."""

    first_name: str
    last_name: str
    #: mdm's stored code of his place in the household (`HOOFDLID`, `PARTNER`, `KIND`).
    relation_type: str
    date_of_birth: Optional[date] = None
    gender_code: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    #: His e-mail addresses in the order they were typed; the first is the primary one.
    emails: tuple[str, ...] = ()


@dataclass(frozen=True)
class HouseholdCreated:
    """The outcome of `CreateHousehold`: the household and its persons, in the
    order they were given."""

    household_id: int
    person_ids: tuple[int, ...]


@dataclass(frozen=True)
class CreateHousehold(Port):
    """Create a household with its persons, their place in it, its address and
    their contact details — every row with its history row, in the caller's
    transaction (CR-13 phase 4c, #1251).

    Asked by `membership`, for the board's "Nieuw lid" and for the public
    sign-up; it adds the one row that is its own, the membership. The address
    hangs on the main member.

    Refused with mdm's `HouseholdRefused` — a postal code that is not known, an
    address without a street, a house number or a postal code — and with
    `PersonDetailsMissing` for a person without a birth date or a gender;
    nothing is written then.

    `main_person_id`: a person who exists already and becomes the main member
    instead of a new one — an account that signs up (CR-22 R9). He gets the
    name, the birth date and the gender the form says; the contact details he
    holds stay and what the form adds is added beside them.
    """

    street: str
    house_number: str
    postal_code: str
    persons: tuple[HouseholdPerson, ...]
    #: Who did it and where it comes from, for the history rows.
    source: str
    actor: Optional[str] = None
    bus_number: Optional[str] = None
    main_person_id: Optional[int] = None


@dataclass(frozen=True)
class HouseholdDeleted(KernelEvent):
    """A household is deleted, with its persons, their address and their contact
    details (CR-13 phase 4c, #1251).

    Published by `mdm` in the transaction of the deletion, AFTER its own rows
    are soft-deleted and flushed: an event says what happened. `membership`
    subscribes and deletes the household's memberships — each with its history
    row, and each said in turn (`MembershipDeleted`) so the money follows. A
    subscriber reads its OWN rows by `household_id`; the household itself is
    gone by then. Not optional: mdm refuses to publish when nothing subscribes.
    """

    household_id: int
    actor: Optional[str] = None
