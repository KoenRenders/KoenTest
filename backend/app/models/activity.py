from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date, Time, ForeignKey, Numeric, Text
from sqlalchemy.orm import relationship
from app.database import Base


class ActivityDate(Base):
    __tablename__ = "activity_dates"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="CASCADE"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)

    activity = relationship("Activity", back_populates="dates")


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    poster_url = Column(Text, nullable=True)
    is_cancelled = Column(Boolean, default=False, nullable=False)
    members_only = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    dates = relationship("ActivityDate", back_populates="activity", cascade="all, delete-orphan")
    registrations = relationship("Registration", back_populates="activity", cascade="all, delete-orphan")
    sub_registrations = relationship("ActivitySubRegistration", back_populates="activity", cascade="all, delete-orphan", order_by="ActivitySubRegistration.sort_order")


class Registration(Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    is_waitlist = Column(Boolean, default=False, nullable=False)
    registered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    registration_type = Column(String(10), ForeignKey("registration_type_codes.code"), nullable=False)

    contact_name = Column(String(200), nullable=True)
    contact_email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    team_name = Column(String(200), nullable=True)
    payment_method = Column(String(20), nullable=True)
    component_id = Column(Integer, ForeignKey("activity_sub_registrations.id", ondelete="SET NULL"), nullable=True)
    remarks = Column(Text, nullable=True)

    activity = relationship("Activity", back_populates="registrations")
    person = relationship("Person", back_populates="registrations")
    items = relationship("RegistrationItem", back_populates="registration", cascade="all, delete-orphan")


class RegistrationItem(Base):
    __tablename__ = "registration_items"

    id = Column(Integer, primary_key=True, index=True)
    registration_id = Column(Integer, ForeignKey("registrations.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("activity_products.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)

    registration = relationship("Registration", back_populates="items")
    product = relationship("ActivityProduct")
