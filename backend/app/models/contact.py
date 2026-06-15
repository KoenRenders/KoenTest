from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.soft_delete import SoftDeleteMixin


class ContactDetail(SoftDeleteMixin, Base):
    __tablename__ = "contact_details"

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    contact_type_code = Column(String(10), ForeignKey("contact_type_codes.code"), nullable=False)
    value = Column(String(255), nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    person = relationship("Person", back_populates="contact_details")
