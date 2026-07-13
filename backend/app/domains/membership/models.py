"""Lidmaatschappen (membership-component, fase 4a #402 — §5.4).

Schema ``membership``. ``member_id`` is een soft-ref naar mdm.members (§6/§8):
de FK is in migratie 078 gedropt; de ORM-relatie (via backref op Member) blijft
voor intern gemak, maar de DB legt de koppeling niet meer vast.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, ForeignKey
from sqlalchemy.orm import backref, relationship

from app.database import Base
from app.soft_delete import SoftDeleteMixin


class Membership(SoftDeleteMixin, Base):
    """Annual membership record per member household."""
    __tablename__ = "memberships"
    __table_args__ = {"schema": "membership"}

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

    member = relationship("Member", backref=backref("memberships", cascade="all, delete-orphan"))


class HistoryMixin:
    id = Column(Integer, primary_key=True, index=True)
    operation = Column(String(10), nullable=False)
    action = Column(String(40), nullable=False)
    source = Column(String(30), nullable=False)
    actor = Column(String(255), nullable=True)
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)


class MembershipHistory(HistoryMixin, Base):
    __tablename__ = "membership_history"
    __table_args__ = {"schema": "membership"}

    membership_id = Column(Integer, nullable=False, index=True)
    member_id = Column(Integer, nullable=True, index=True)
    year = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)


