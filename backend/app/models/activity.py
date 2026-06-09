from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date, Time, ForeignKey, Numeric, Text
from sqlalchemy.orm import relationship
from app.database import Base


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    date = Column(Date, nullable=False, index=True)
    date_end = Column(Date, nullable=True)
    time = Column(Time, nullable=True)
    location = Column(String(255), nullable=True)
    max_participants = Column(Integer, nullable=True)
    registration_type_code = Column(String(10), ForeignKey("registration_type_codes.code"), nullable=False)
    price = Column(Numeric(10, 2), default=0, nullable=False)
    member_price = Column(Numeric(10, 2), nullable=True)
    poster_url = Column(String(500), nullable=True)
    is_archived = Column(Boolean, default=False, nullable=False, index=True)
    members_only = Column(Boolean, default=False, nullable=False)
    is_cancelled = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)
    reg_form_type = Column(String(20), nullable=False, default="NONE")
    age_category_config = Column(Text, nullable=True)
    team_name_required = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    registrations = relationship("Registration", back_populates="activity", cascade="all, delete-orphan")
    sub_registrations = relationship("ActivitySubRegistration", back_populates="activity", cascade="all, delete-orphan", order_by="ActivitySubRegistration.sort_order")


class Registration(Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False, index=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    is_waitlist = Column(Boolean, default=False, nullable=False)
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    registration_type = Column(String(10), ForeignKey("registration_type_codes.code"), nullable=False)

    contact_name = Column(String(200), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(30), nullable=True)
    team_name = Column(String(200), nullable=True)
    group_size = Column(Integer, nullable=True)
    age_categories = Column(Text, nullable=True)
    remarks = Column(Text, nullable=True)
    payment_method = Column(String(20), nullable=True)
    payment_status = Column(String(20), nullable=True)
    sub_registration_id = Column(Integer, ForeignKey("activity_sub_registrations.id"), nullable=True)
    total_amount = Column(Numeric(10, 2), nullable=True)

    activity = relationship("Activity", back_populates="registrations")
    person = relationship("Person", back_populates="registrations")
    items = relationship("RegistrationItem", back_populates="registration", cascade="all, delete-orphan")


class RegistrationItem(Base):
    __tablename__ = "registration_items"

    id = Column(Integer, primary_key=True, index=True)
    registration_id = Column(Integer, ForeignKey("registrations.id"), nullable=False)
    sub_registration_id = Column(Integer, ForeignKey("activity_sub_registrations.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    registration = relationship("Registration", back_populates="items")
    sub_registration = relationship("ActivitySubRegistration")
