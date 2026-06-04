from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Family(Base):
    __tablename__ = "families"

    id = Column(Integer, primary_key=True, index=True)
    street = Column(String(255), nullable=False)
    house_number = Column(String(20), nullable=False)
    bus_number = Column(String(20), nullable=True)
    postal_code = Column(String(10), nullable=False)
    municipality = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    members = relationship("FamilyMember", back_populates="family", cascade="all, delete-orphan")
    memberships = relationship("Membership", back_populates="family", cascade="all, delete-orphan")
    registrations = relationship("Registration", back_populates="family")
    orders = relationship("Order", back_populates="family")


class FamilyMember(Base):
    __tablename__ = "family_members"

    id = Column(Integer, primary_key=True, index=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    last_name = Column(String(100), nullable=False)
    first_name = Column(String(100), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(30), nullable=True)
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    family = relationship("Family", back_populates="members")
    registrations = relationship("Registration", back_populates="family_member")


class Membership(Base):
    __tablename__ = "memberships"

    id = Column(Integer, primary_key=True, index=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    year = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    family = relationship("Family", back_populates="memberships")
