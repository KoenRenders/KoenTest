from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, Text, ForeignKey
from sqlalchemy.orm import relationship, object_session
from app.database import Base
from app.soft_delete import SoftDeleteMixin


class ActivitySubRegistration(SoftDeleteMixin, Base):
    """A component (onderdeel) of an activity. Each component can have products."""
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
    team_name_required = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    activity = relationship("Activity", back_populates="sub_registrations")
    products = relationship("ActivityProduct", back_populates="component", cascade="all, delete-orphan", order_by="ActivityProduct.sort_order")

    def _info_asset(self):
        sess = object_session(self)
        if sess is None or self.id is None:
            return None
        from app.models.asset import MediaAsset
        return (
            sess.query(MediaAsset)
            .filter(MediaAsset.kind == "component_info", MediaAsset.component_id == self.id)
            .order_by(MediaAsset.id.desc())
            .first()
        )

    @property
    def info_asset_url(self):
        """Een geüpload info/reglement-bestand primeert op ``info_url`` (#223)."""
        a = self._info_asset()
        return f"/api/v1/media/{a.id}" if a else None

    @property
    def info_asset_is_pdf(self):
        a = self._info_asset()
        return bool(a and a.content_type == "application/pdf")


class ActivityProduct(SoftDeleteMixin, Base):
    """A product (inschrijvingsoptie) within an activity component."""
    __tablename__ = "activity_products"

    id = Column(Integer, primary_key=True, index=True)
    component_id = Column(Integer, ForeignKey("activity_sub_registrations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    price = Column(Numeric(10, 2), nullable=False, default=0)
    member_price = Column(Numeric(10, 2), nullable=True)
    is_free = Column(Boolean, default=True, nullable=False)
    max_participants = Column(Integer, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    component = relationship("ActivitySubRegistration", back_populates="products")
