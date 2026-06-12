from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class ExternalNumber(Base):
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_external_numbers_source_external_id"),
    )

    person = relationship("Person", back_populates="external_numbers")
