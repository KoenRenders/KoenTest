from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class ActivitySubRegistration(Base):
    """A registration form linked to an activity. One activity can have multiple."""
    __tablename__ = "activity_sub_registrations"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    external_register_url = Column(String(500), nullable=True)
    external_registrations_url = Column(String(500), nullable=True)
    info_url = Column(String(500), nullable=True)
    registration_type_code = Column(String(10), ForeignKey("registration_type_codes.code"), nullable=False, default="INDIVIDUAL")
    max_participants = Column(Integer, nullable=True)
    price = Column(Numeric(10, 2), nullable=False, default=0)
    member_price = Column(Numeric(10, 2), nullable=True)
    is_free = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    activity = relationship("Activity", back_populates="sub_registrations")
