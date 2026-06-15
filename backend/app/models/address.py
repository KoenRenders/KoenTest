from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.soft_delete import SoftDeleteMixin


class Address(SoftDeleteMixin, Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True, index=True)
    # Uniciteit op person_id is partieel (WHERE deleted_at IS NULL) — zie migratie 050.
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    street = Column(String(255), nullable=False)
    house_number = Column(String(10), nullable=False)
    bus_number = Column(String(10), nullable=True)
    postal_code_id = Column(Integer, ForeignKey("postal_codes.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    person = relationship("Person", back_populates="address")
    postal_code = relationship("PostalCode")
