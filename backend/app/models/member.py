from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.soft_delete import SoftDeleteMixin


class Membership(SoftDeleteMixin, Base):
    """Annual membership record per member household."""
    __tablename__ = "memberships"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("mdm.members.id"), nullable=False)
    year = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    # Geldigheidsperiode: gezet zodra de betaling bevestigd is.
    # valid_from = betaaldatum; valid_to = 31 dec dit of volgend jaar (zie service).
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    member = relationship("Member", back_populates="memberships")
