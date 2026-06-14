from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Member(Base):
    """Household grouping — dynamic, can change over time."""
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    board_member_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    member_persons = relationship("MemberPerson", back_populates="member", cascade="all, delete-orphan")
    memberships = relationship("Membership", back_populates="member", cascade="all, delete-orphan")
    board_member = relationship("Person", foreign_keys=[board_member_id])


class Person(Base):
    """Stable, permanent individual entity."""
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    last_name = Column(String(100), nullable=False)
    first_name = Column(String(100), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender_code = Column(String(10), ForeignKey("gender_codes.code"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    member_persons = relationship("MemberPerson", back_populates="person")
    address = relationship("Address", back_populates="person", uselist=False)
    contact_details = relationship("ContactDetail", back_populates="person", cascade="all, delete-orphan")
    external_numbers = relationship("ExternalNumber", back_populates="person", cascade="all, delete-orphan")
    registrations = relationship("Registration", back_populates="person")


class MemberPerson(Base):
    """Junction table linking persons to member households."""
    __tablename__ = "member_persons"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    relation_type = Column(String(10), ForeignKey("relation_type_codes.code"), nullable=False, default="HOOFDLID")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    member = relationship("Member", back_populates="member_persons")
    person = relationship("Person", back_populates="member_persons")


class Membership(Base):
    """Annual membership record per member household."""
    __tablename__ = "memberships"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    year = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    # Geldigheidsperiode: gezet zodra de betaling bevestigd is.
    # valid_from = betaaldatum; valid_to = 31 dec dit of volgend jaar (zie service).
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    member = relationship("Member", back_populates="memberships")
