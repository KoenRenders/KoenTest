from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date, Time, ForeignKey, Numeric, Enum
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class RegistrationTypeEnum(str, enum.Enum):
    individual = "individual"
    family = "family"


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=True)
    location = Column(String(255), nullable=True)
    max_participants = Column(Integer, nullable=True)
    registration_type = Column(Enum(RegistrationTypeEnum), default=RegistrationTypeEnum.individual, nullable=False)
    price = Column(Numeric(10, 2), default=0, nullable=False)
    member_price = Column(Numeric(10, 2), nullable=True)
    poster_url = Column(String(500), nullable=True)
    is_archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    registrations = relationship("Registration", back_populates="activity", cascade="all, delete-orphan")


class Registration(Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=True)
    family_member_id = Column(Integer, ForeignKey("family_members.id"), nullable=True)
    is_waitlist = Column(Boolean, default=False, nullable=False)
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    registration_type = Column(Enum(RegistrationTypeEnum), nullable=False)

    # Extra contact fields for non-member registrations
    contact_name = Column(String(200), nullable=True)
    contact_email = Column(String(255), nullable=True)

    activity = relationship("Activity", back_populates="registrations")
    family = relationship("Family", back_populates="registrations")
    family_member = relationship("FamilyMember", back_populates="registrations")
