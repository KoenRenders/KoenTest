from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base

class PostalCode(Base):
    __tablename__ = "postal_codes"
    id = Column(Integer, primary_key=True, index=True)
    postal_code = Column(String(4), nullable=False, index=True)
    municipality = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
