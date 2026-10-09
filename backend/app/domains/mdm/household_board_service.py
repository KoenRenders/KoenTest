"""The board's writes on a household (CR-13 phase 4c, #1251).

The Leden screen of the back office changes a household's persons, their
contact details, their relation, its address and its board member. These
functions write those rows — mdm's rows, so they stand in mdm. Until phase 4c
they stood in `membership/household_service.py` and mdm's own screen reached
them through `membership.api`: a second domain writing master data.

Beside this module: `household_service.py` holds what a MEMBER changes of their
own household and `household_save.py` the one save of Mijn gezin. What the Leden
screen READS — a household with its memberships — is membership's read model and
stays there (`membership.api.get_family`, `list_families`).

Moved as they stood. A refusal is an `HTTPException`, as it was, and each
function commits, as it did: the screen calls one of them per request. What
changed with the move is said in the functions it concerns: nothing is returned
that nobody read, and `add_person_to_family` returns the new person's id.
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domains.mdm.household_board_schemas import (
    AddressUpdate,
    BoardMemberAssign,
    ContactsUpdate,
    PersonAddToFamily,
    PersonUpdate,
)
from app.domains.mdm.models import (
    Address,
    GenderCode,
    MasterDataError,
    Member,
    MemberPerson,
    Person,
    PersonDetailsMissing,
    PostalCode,
    RelationType,
)
from app.domains.mdm.service import new_contact_detail
from app.i18n import _

#: The longest first or last name a person can have: the length of the two
#: columns (`varchar(100)`, both). The rule below refuses a longer one, and the
#: person forms of the Leden screen carry it as their fields' `maxlength`, so
#: the browser stops where the server refuses — one number, read from the column.
PERSON_NAME_MAX: int = Person.__table__.c.last_name.type.length


def board_request(schema, **fields):
    """What a form of the Leden screen sent, as the request of one of the writes
    below. A value that cannot be read — a birth date that is no date, a relation
    that is not of the list — is refused here with words, where it ended the
    request in a 500 until #1251. The form sends neither from a browser (a date
    field, a select list); another client can."""
    words = {
        "date_of_birth": _("Vul een geldige geboortedatum in."),
        "relation_type": _("Kies een relatie uit de lijst."),
    }
    try:
        return schema(**fields)
    except ValidationError as refusal:
        field = refusal.errors()[0]["loc"][0]
        if field not in words:
            raise
        raise HTTPException(status_code=422, detail=words[field]) from refusal


def _require_storable(db: Session, first_name, last_name, gender_code) -> None:
    """What the columns of a person cannot hold is refused before the write, where
    the database refused it after (a 500 until #1251): a name longer than its
    column, and a gender code that is not of the list (`mdm.gender_codes`)."""
    if any(len(name or "") > PERSON_NAME_MAX for name in (first_name, last_name)):
        raise HTTPException(
            status_code=422,
            detail=_("Een naam is ten hoogste %(n)s tekens lang.") % {"n": PERSON_NAME_MAX},
        )
    if gender_code and db.get(GenderCode, gender_code) is None:
        raise HTTPException(status_code=422, detail=_("Kies een geslacht uit de lijst."))


def update_person(db: Session, person_id: int, data: PersonUpdate, admin=None):
    from app.domains.mdm.history import snapshot_person

    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail=_("Person not found"))
    # Enkel snapshotten wat écht wijzigt (#188): een formulier stuurt alle velden mee,
    # maar een onveranderd veld hoort geen history-rij te maken.
    wijzigingen = data.model_dump(exclude_unset=True)
    # #681: toets de UITKOMST, en toets ze vóór het toepassen. Een gedeeltelijke
    # wijziging (enkel de naam) mag niet afketsen op een veld dat niet meegestuurd
    # werd, maar ze mag de persoon evenmin zónder deze twee achterlaten. Vooraf,
    # niet achteraf: een `rollback()` ná het muteren gooit ook al het andere werk
    # in dezelfde sessie weg.
    try:
        MemberPerson.require_details(
            wijzigingen.get("date_of_birth", person.date_of_birth),
            wijzigingen.get("gender_code", person.gender_code),
        )
    except PersonDetailsMissing as fout:
        raise HTTPException(status_code=422, detail=str(fout))
    _require_storable(
        db,
        wijzigingen.get("first_name"),
        wijzigingen.get("last_name"),
        wijzigingen.get("gender_code"),
    )

    changed = False
    # A blank first or last name is refused by the person itself as it is set
    # (`Person._name_not_blank`); answered here like this function's other
    # refusals, where it ended the request in a 500 until #1251.
    try:
        for field, value in wijzigingen.items():
            if getattr(person, field) != value:
                setattr(person, field, value)
                changed = True
    except MasterDataError as refusal:
        raise HTTPException(status_code=422, detail=str(refusal)) from refusal
    if changed:
        snapshot_person(
            db,
            person,
            operation="update",
            action="person_updated",
            source="admin_update",
            actor=admin.email,
        )
    db.commit()


def _require_whole_address(street, house_number, postal_code) -> None:
    """An address has a street, a house number and a postal code — mdm's one rule
    (`require_whole_address`, #1603), which the portal's save always asked. The
    back office's forms mark the three as required, and the server keeps that
    promise here (CR-13 phase 4c, #1251). A 422, as this service's other refusals."""
    from app.domains.mdm.household_service import HouseholdRefused, require_whole_address

    try:
        require_whole_address(
            {"street": street, "house_number": house_number, "postal_code": postal_code}
        )
    except HouseholdRefused as refusal:
        raise HTTPException(status_code=422, detail=str(refusal)) from refusal


def update_family_address(db: Session, family_id: int, data: AddressUpdate, admin=None):
    """The household's one address. It hangs on the main member — on the first
    person where none is marked — and a household without persons has nobody to
    hang it on. That rule stood in the screen until CR-13 phase 4c (#1251)."""
    household = db.query(Member).filter(Member.id == family_id).first()
    if not household:
        raise HTTPException(status_code=404, detail=_("Family not found"))
    links = sorted(household.member_persons, key=MemberPerson.household_position)
    holder = next(
        (link for link in links if link.relation_type == RelationType.PRIMARY_MEMBER),
        links[0] if links else None,
    )
    if holder is None:
        raise HTTPException(status_code=400, detail=_("Gezin zonder personen."))
    update_person_address(db, holder.person_id, data, admin=admin)


def update_person_address(
    db: Session,
    person_id: int,
    data: AddressUpdate,
    admin=None,
):
    from app.domains.mdm.history import snapshot_address

    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail=_("Person not found"))
    address = person.address
    if not address:
        # #1111: a household created in the back office has no address row —
        # `create_member` (gone since CR-13 phase 4b) never made one — so "update" refused every first
        # address with 404 "Address not found", and the screen showed the
        # generic banner. Saving an address on a household without one means
        # creating it; the three required parts must all be there.
        _require_whole_address(data.street, data.house_number, data.postal_code)
        pc = db.query(PostalCode).filter(PostalCode.postal_code == data.postal_code).first()
        if not pc:
            raise HTTPException(
                status_code=422,
                detail=_("Onbekende postcode: %(postal_code)s") % {"postal_code": data.postal_code},
            )
        address = Address(
            person_id=person.id,
            street=data.street,
            house_number=data.house_number,
            bus_number=data.bus_number or None,
            postal_code_id=pc.id,
        )
        db.add(address)
        db.flush()
        snapshot_address(
            db,
            address,
            operation="insert",
            action="address_created",
            source="admin_manual",
            actor=admin.email,
        )
        db.commit()
        return
    if data.postal_code is not None:
        pc = db.query(PostalCode).filter(PostalCode.postal_code == data.postal_code).first()
        if not pc:
            raise HTTPException(
                status_code=422,
                detail=_("Onbekende postcode: %(postal_code)s") % {"postal_code": data.postal_code},
            )
        address.postal_code_id = pc.id
    # What the address would be after this save: a field the form did not send
    # stays, an emptied one does not pass.
    _require_whole_address(
        address.street if data.street is None else data.street,
        address.house_number if data.house_number is None else data.house_number,
        address.postal_code.postal_code if address.postal_code else None,
    )
    for field in ("street", "house_number"):
        value = getattr(data, field)
        if value is not None:
            setattr(address, field, value)
    if data.bus_number is not None or "bus_number" in (data.model_fields_set or set()):
        address.bus_number = data.bus_number or None
    snapshot_address(
        db,
        address,
        operation="update",
        action="address_updated",
        source="admin_update",
        actor=admin.email,
    )
    db.commit()


def update_person_contacts(
    db: Session,
    person_id: int,
    data: ContactsUpdate,
    admin=None,
):

    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail=_("Person not found"))

    # #1174: langs de gedeelde regel, niet langs een eigen binnenfunctie. Die
    # stond hier met exact dezelfde "eerste rij"-fout als de import — dit scherm
    # kon dus een extra e-mailadres overschrijven of, bij een leeggemaakt veld,
    # verwijderen. Dat is precies het adres dat de nieuwsbriefverantwoordelijke
    # net had ingevoerd.
    from app.domains.mdm.service import upsert_primary_contact

    def _upsert_contact(type_code: str, value: Optional[str]):
        upsert_primary_contact(
            db,
            person,
            type_code,
            value,
            action="contacts_updated",
            source="admin_update",
            actor=admin.email,
        )

    # #1219: een veld dat het formulier NIET meegaf, blijft met rust. Sinds de
    # e-mailadressen rijen zijn, draagt het ledenformulier van een bestaande
    # persoon geen `email` meer — en `email=None` betekent hier "verwijder het
    # hoofdadres". Zonder deze grens wist elke opslag het hoofdadres.
    gegeven = data.model_fields_set
    if "email" in gegeven:
        _upsert_contact("EMAIL", data.email)
    if "phone" in gegeven:
        _upsert_contact("PHONE", data.phone)
    if "mobile" in gegeven:
        _upsert_contact("MOBILE", data.mobile)
    db.commit()


def delete_person(db: Session, person_id: int, admin=None):
    """The board deletes a person of a household. The rule is master data's
    (`mdm.delete_person`, CR-22 S7 — #1712): this door only finds the person and
    answers a refusal as a 400."""
    from app.domains.mdm.models import MasterDataError
    from app.domains.mdm.service import delete_person as delete_master_person

    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail=_("Person not found"))
    try:
        delete_master_person(db, person, actor=admin.email)
        db.commit()
    except MasterDataError as refusal:
        raise HTTPException(status_code=400, detail=str(refusal)) from refusal


def add_person_to_family(
    db: Session,
    family_id: int,
    data: PersonAddToFamily,
    admin=None,
) -> int:
    from app.domains.mdm.history import (
        snapshot_contact_detail,
        snapshot_member_person,
        snapshot_person,
    )

    member = db.query(Member).filter(Member.id == family_id).first()
    if not member:
        raise HTTPException(status_code=404, detail=_("Family not found"))

    try:
        MemberPerson.require_details(data.date_of_birth, data.gender_code)
    except PersonDetailsMissing as fout:
        raise HTTPException(status_code=422, detail=str(fout))
    _require_storable(db, data.first_name, data.last_name, data.gender_code)

    # A blank first or last name is refused by the person itself (#1251: it
    # ended the request in a 500).
    try:
        person = Person(
            last_name=data.last_name,
            first_name=data.first_name,
            date_of_birth=data.date_of_birth,
            gender_code=data.gender_code,
        )
    except MasterDataError as refusal:
        raise HTTPException(status_code=422, detail=str(refusal)) from refusal
    db.add(person)
    db.flush()
    snapshot_person(
        db,
        person,
        operation="insert",
        action="person_added_to_family",
        source="admin_manual",
        actor=admin.email,
    )

    mp = MemberPerson(member_id=family_id, person_id=person.id, relation_type=data.relation_type)
    db.add(mp)
    db.flush()
    snapshot_member_person(
        db,
        mp,
        operation="insert",
        action="person_added_to_family",
        source="admin_manual",
        actor=admin.email,
    )

    # Geen adres voor extra gezinsleden: het adres hoort enkel bij het hoofdlid (#125).

    for type_code, value in (("EMAIL", data.email), ("PHONE", data.phone), ("MOBILE", data.mobile)):
        if value:
            contact = new_contact_detail(db, person, type_code, value, is_primary=True)
            db.add(contact)
            db.flush()
            snapshot_contact_detail(
                db,
                contact,
                operation="insert",
                action="person_added_to_family",
                source="admin_manual",
                actor=admin.email,
            )

    db.commit()
    return person.id


def assign_board_member(
    db: Session,
    family_id: int,
    data: BoardMemberAssign,
    admin=None,
):
    from app.domains.mdm.history import snapshot_member

    member = db.query(Member).filter(Member.id == family_id).first()
    if not member:
        raise HTTPException(status_code=404, detail=_("Family not found"))
    if data.person_id is not None:
        person = db.query(Person).filter(Person.id == data.person_id).first()
        if not person:
            raise HTTPException(status_code=404, detail=_("Person not found"))
    member.board_member_id = data.person_id
    snapshot_member(
        db,
        member,
        operation="update",
        action="board_member_assigned",
        source="admin_update",
        actor=admin.email,
    )
    db.commit()


def set_relation_type(db, family_id: int, person_id: int, relation_type: str) -> bool:
    """Wijzig de rol van een persoon binnen zijn gezin (#635 F).

    Twee regels, en ze golden alleen zolang dit scherm ze onthield: je kan iemand
    niet tot HOOFDLID promoveren via dit pad, en een bestaand HOOFDLID wordt nooit
    overschreven. Dat laatste is de belangrijke: het hoofdlid is de drager van het
    adres, het lidmaatschap en de betaalcommunicatie — hem stil degraderen laat een
    gezin zonder aanspreekpunt achter.

    De regel stond in `mdm/ui.py`, met een rauwe query erbij, en was daardoor niet
    los testbaar (#498). Commit zelf, net als de andere gezinsbewerkingen: de
    transactiegrens ligt in de service (#635 regel 2).

    Geeft terug of er iets gewijzigd is.
    """
    # CR-12 phase 2: this used to apply `(x or "").strip().upper()` on both
    # sides — a normalisation that was needed because the column accepted any
    # spelling. The code list does that now: a value that is not in it does
    # not get in, and `RelationType(...)` already refuses it here with the
    # name of the list.

    try:
        gevraagd = RelationType((relation_type or "").strip())
    except ValueError:
        return False
    if gevraagd is RelationType.PRIMARY_MEMBER:
        return False

    koppeling = (
        db.query(MemberPerson)
        .filter(MemberPerson.member_id == family_id, MemberPerson.person_id == person_id)
        .first()
    )
    if koppeling is None or koppeling.relation_type is RelationType.PRIMARY_MEMBER:
        return False

    koppeling.relation_type = gevraagd
    db.commit()
    return True
