"""Masterdata (MDM-component, fase 2 #400 — §5.3/§6): personen, gezinnen,
adressen, contactgegevens, postcodes, externe nummers, organisaties en de
bijbehorende codetabellen + history. Alles in Postgres-schema ``mdm``.

Survivorship (§6): een Person wordt nooit hard verwijderd bij een merge —
``superseded_by_id`` wijst naar de overlever; ``service.resolve()`` slaat de
keten plat (O(1) doordat merges platgeslagen worden bijgehouden).
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base
from app.soft_delete import SoftDeleteMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Member(SoftDeleteMixin, Base):
    """Household grouping — dynamic, can change over time."""
    __tablename__ = "members"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    board_member_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    member_persons = relationship("MemberPerson", back_populates="member", cascade="all, delete-orphan")
    # Bewust GEEN memberships-relatie hier: lidmaatschap is een ander domein
    # (fase 4a). Membership definieert de koppeling via een backref, zodat de
    # masterdata standalone geladen kan worden (§6, soft-ref-richting).
    board_member = relationship("Person", foreign_keys=[board_member_id])


class Person(SoftDeleteMixin, Base):
    """Stable, permanent individual entity."""
    __tablename__ = "persons"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    last_name = Column(String(100), nullable=False)
    first_name = Column(String(100), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender_code = Column(String(10), ForeignKey("mdm.gender_codes.code"), nullable=True)
    # Survivorship (§6): gezet door service.merge_persons(); wijst ALTIJD direct
    # naar de eind-overlever (platgeslagen keten → resolve() is O(1)).
    superseded_by_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    member_persons = relationship("MemberPerson", back_populates="person")
    address = relationship("Address", back_populates="person", uselist=False)
    contact_details = relationship("ContactDetail", back_populates="person", cascade="all, delete-orphan")
    external_numbers = relationship("ExternalNumber", back_populates="person", cascade="all, delete-orphan")
    # Bewust GEEN registrations-relatie: activiteiten zijn een ander domein;
    # Registration definieert de koppeling via een backref (zelfde regel).


class MemberPerson(SoftDeleteMixin, Base):
    """Junction table linking persons to member households."""
    __tablename__ = "member_persons"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("mdm.members.id"), nullable=False)
    # ondelete RESTRICT: een persoon kan niet hard verdwijnen zolang er
    # gezinskoppelingen aan hangen (DB als laatste vangnet, #97 / migr. 058).
    person_id = Column(Integer, ForeignKey("mdm.persons.id", ondelete="RESTRICT"), nullable=False)
    relation_type = Column(String(10), ForeignKey("mdm.relation_type_codes.code"), nullable=False, default="HOOFDLID")
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    member = relationship("Member", back_populates="member_persons")
    person = relationship("Person", back_populates="member_persons")


class Address(SoftDeleteMixin, Base):
    __tablename__ = "addresses"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    # Uniciteit op person_id is partieel (WHERE deleted_at IS NULL) — zie migratie 050.
    person_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=False)
    street = Column(String(255), nullable=False)
    house_number = Column(String(10), nullable=False)
    bus_number = Column(String(10), nullable=True)
    postal_code_id = Column(Integer, ForeignKey("mdm.postal_codes.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    person = relationship("Person", back_populates="address")
    postal_code = relationship("PostalCode")


class ContactDetail(SoftDeleteMixin, Base):
    __tablename__ = "contact_details"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=False)
    contact_type_code = Column(String(10), ForeignKey("mdm.contact_type_codes.code"), nullable=False)
    value = Column(String(255), nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    person = relationship("Person", back_populates="contact_details")


class PostalCode(Base):
    __tablename__ = "postal_codes"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    postal_code = Column(String(4), nullable=False, index=True)
    municipality = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)


class ExternalNumber(SoftDeleteMixin, Base):
    """External identifier for a person from another system.

    Bijvoorbeeld het oude lidnummer uit de vorige ledenadministratie.
    Genormaliseerd zodat één persoon meerdere externe nummers (uit
    verschillende bronsystemen) kan hebben.
    """
    __tablename__ = "external_numbers"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=False, index=True)
    source = Column(String(50), nullable=False, default="ledenadministratie")
    external_id = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    # Uniciteit op (source, external_id) is partieel (WHERE deleted_at IS NULL) — zie migratie 050.

    person = relationship("Person", back_populates="external_numbers")


class Organization(SoftDeleteMixin, Base):
    """Organisatie (§6): ACCOUNT = afdeling/klant (bv. Raak Millegem),
    UNIT = onderdeel daarvan. Zelf-refererend; de tenancy-fase (#406) hangt de
    tenant-kolommen aan dit begrip."""

    __tablename__ = "organizations"
    __table_args__ = {"schema": "mdm"}

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("mdm.organizations.id"), nullable=True)
    # ACCOUNT | UNIT — CHECK in migratie 078.
    org_type = Column(String(10), nullable=False, default="ACCOUNT")
    # Stabiele technische naam (bv. "raakmillegem") — uniek.
    code = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    parent = relationship("Organization", remote_side=[id])


# ── Codetabellen van de masterdata ──────────────────────────────────────────────

class GenderCode(Base):
    __tablename__ = "gender_codes"
    __table_args__ = {"schema": "mdm"}
    code = Column(String(10), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)


class ContactTypeCode(Base):
    __tablename__ = "contact_type_codes"
    __table_args__ = {"schema": "mdm"}
    code = Column(String(10), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)


class RelationTypeCode(Base):
    __tablename__ = "relation_type_codes"
    __table_args__ = {"schema": "mdm"}
    code = Column(String(10), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)


# ── History (append-only; geen FK's — overleeft het verdwijnen van de bron) ────

class HistoryMixin:
    """Gedeelde audit-metadata voor alle history-tabellen."""

    id = Column(Integer, primary_key=True, index=True)
    operation = Column(String(10), nullable=False)   # insert / update / delete
    action = Column(String(40), nullable=False)       # semantische business-actie
    source = Column(String(30), nullable=False)       # system / registration / mollie / ...
    actor = Column(String(255), nullable=True)        # admin-e-mail of None
    recorded_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False, index=True)


class PersonHistory(HistoryMixin, Base):
    __tablename__ = "person_history"
    __table_args__ = {"schema": "mdm"}

    person_id = Column(Integer, nullable=False, index=True)
    last_name = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    gender_code = Column(String(10), nullable=True)


class MemberHistory(HistoryMixin, Base):
    __tablename__ = "member_history"
    __table_args__ = {"schema": "mdm"}

    member_id = Column(Integer, nullable=False, index=True)
    board_member_id = Column(Integer, nullable=True)


class MemberPersonHistory(HistoryMixin, Base):
    __tablename__ = "member_person_history"
    __table_args__ = {"schema": "mdm"}

    member_person_id = Column(Integer, nullable=False, index=True)
    member_id = Column(Integer, nullable=True, index=True)
    person_id = Column(Integer, nullable=True, index=True)
    relation_type = Column(String(10), nullable=True)


class AddressHistory(HistoryMixin, Base):
    __tablename__ = "address_history"
    __table_args__ = {"schema": "mdm"}

    address_id = Column(Integer, nullable=False, index=True)
    person_id = Column(Integer, nullable=True, index=True)
    street = Column(String(255), nullable=True)
    house_number = Column(String(20), nullable=True)
    bus_number = Column(String(10), nullable=True)
    postal_code_id = Column(Integer, nullable=True)


class ContactDetailHistory(HistoryMixin, Base):
    __tablename__ = "contact_detail_history"
    __table_args__ = {"schema": "mdm"}

    contact_detail_id = Column(Integer, nullable=False, index=True)
    person_id = Column(Integer, nullable=True, index=True)
    contact_type_code = Column(String(10), nullable=True)
    value = Column(String(255), nullable=True)
    is_primary = Column(Boolean, nullable=True)
