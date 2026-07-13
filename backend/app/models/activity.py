from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date, Time, ForeignKey, Numeric, Text
from sqlalchemy.orm import relationship, object_session
from app.database import Base
from app.soft_delete import SoftDeleteMixin


def _single_asset(obj, kind, fk_attr):
    """De (max. één) MediaAsset van een bepaald ``kind`` die aan dit object hangt.

    Via de live sessie opgehaald i.p.v. een mapper-relationship met constante in de
    join (eenvoudiger, geen overlap-config). MediaAsset is niet soft-deletable, dus
    de globale filter raakt deze query niet."""
    sess = object_session(obj)
    if sess is None or obj.id is None:
        return None
    from app.models.asset import MediaAsset
    return (
        sess.query(MediaAsset)
        .filter(MediaAsset.kind == kind, getattr(MediaAsset, fk_attr) == obj.id)
        .order_by(MediaAsset.id.desc())
        .first()
    )


class ActivityDate(SoftDeleteMixin, Base):
    __tablename__ = "activity_dates"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="CASCADE"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)

    activity = relationship("Activity", back_populates="dates")


class Activity(SoftDeleteMixin, Base):
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

    @property
    def poster_asset_url(self):
        """Een geüploade poster primeert op ``poster_url`` (#223)."""
        a = _single_asset(self, "activity_poster", "activity_id")
        return f"/api/v1/media/{a.id}" if a else None

    @property
    def poster_asset_is_pdf(self):
        a = _single_asset(self, "activity_poster", "activity_id")
        return bool(a and a.content_type == "application/pdf")


class Registration(SoftDeleteMixin, Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=True)
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


class RegistrationItem(SoftDeleteMixin, Base):
    __tablename__ = "registration_items"

    id = Column(Integer, primary_key=True, index=True)
    registration_id = Column(Integer, ForeignKey("registrations.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("activity_products.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)

    registration = relationship("Registration", back_populates="items")
    product = relationship("ActivityProduct")
