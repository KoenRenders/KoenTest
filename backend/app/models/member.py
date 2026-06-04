from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base


class Member(Base):
    """Household grouping — dynamic, can change over time."""
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    member_persons = relationship("MemberPerson", back_populates="member", cascade="all, delete-orphan")
    memberships = relationship("Membership", back_populates="member", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="member")


class Person(Base):
    """Stable, permanent individual entity."""
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    last_name = Column(String(100), nullable=False)
    first_name = Column(String(100), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender_code = Column(String(10), ForeignKey("gender_codes.code"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    member_persons = relationship("MemberPerson", back_populates="person")
    address = relationship("Address", back_populates="person", uselist=False)
    contact_details = relationship("ContactDetail", back_populates="person", cascade="all, delete-orphan")
    user = relationship("User", back_populates="person", uselist=False)
    registrations = relationship("Registration", back_populates="person")


class MemberPerson(Base):
    """Junction table linking persons to member households."""
    __tablename__ = "member_persons"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    member = relationship("Member", back_populates="member_persons")
    person = relationship("Person", back_populates="member_persons")


class Membership(Base):
    """Annual membership record per member household."""
    __tablename__ = "memberships"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    year = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    member = relationship("Member", back_populates="memberships")
