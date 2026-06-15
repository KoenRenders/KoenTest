from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.soft_delete import SoftDeleteMixin


class ExternalNumber(SoftDeleteMixin, Base):
    """External identifier for a person from another system.

    Bijvoorbeeld het oude lidnummer uit de vorige ledenadministratie.
    Genormaliseerd zodat één persoon meerdere externe nummers (uit
    verschillende bronsystemen) kan hebben.
    """
    __tablename__ = "external_numbers"

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False, index=True)
    source = Column(String(50), nullable=False, default="ledenadministratie")
    external_id = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Uniciteit op (source, external_id) is partieel (WHERE deleted_at IS NULL) — zie migratie 050.

    person = relationship("Person", back_populates="external_numbers")
