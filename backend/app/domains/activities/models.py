from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date, Time, ForeignKey, Numeric, Text
from sqlalchemy.orm import relationship, object_session
from app.database import Base
from app.kernel.tenancy import TenantMixin
from app.soft_delete import SoftDeleteMixin


def _single_asset(obj, kind, fk_attr):
    """De (max. één) MediaAsset van een bepaald ``kind`` die aan dit object hangt.

    Via de live sessie opgehaald i.p.v. een mapper-relationship met constante in de
    join (eenvoudiger, geen overlap-config). MediaAsset is niet soft-deletable, dus
    de globale filter raakt deze query niet."""
    sess = object_session(obj)
    if sess is None or obj.id is None:
        return None
    from app.domains.media.api import MediaAsset
    return (
        sess.query(MediaAsset)
        .filter(MediaAsset.kind == kind, getattr(MediaAsset, fk_attr) == obj.id)
        .order_by(MediaAsset.id.desc())
        .first()
    )


class ActivityDate(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "activity_dates"
    __table_args__ = {"schema": "activities"}

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.activities.id", ondelete="CASCADE"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)

    activity = relationship("Activity", back_populates="dates")


class Activity(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "activities"
    __table_args__ = {"schema": "activities"}

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


class Registration(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "registrations"
    __table_args__ = {"schema": "activities"}

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.activities.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("mdm.persons.id"), nullable=True)
    registered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    registration_type = Column(String(10), nullable=False)  # idem: geen cross-schema FK (§8)

    contact_name = Column(String(200), nullable=True)
    contact_email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    team_name = Column(String(200), nullable=True)
    payment_method = Column(String(20), nullable=True)
    component_id = Column(Integer, ForeignKey("activities.activity_sub_registrations.id", ondelete="SET NULL"), nullable=True)
    remarks = Column(Text, nullable=True)

    activity = relationship("Activity", back_populates="registrations")
    person = relationship("Person", backref="registrations")
    items = relationship("RegistrationItem", back_populates="registration", cascade="all, delete-orphan")


class RegistrationItem(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "registration_items"
    __table_args__ = {"schema": "activities"}

    id = Column(Integer, primary_key=True, index=True)
    registration_id = Column(Integer, ForeignKey("activities.registrations.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("activities.activity_products.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)

    registration = relationship("Registration", back_populates="items")
    product = relationship("ActivityProduct")


class ActivitySubRegistration(TenantMixin, SoftDeleteMixin, Base):
    """A component (onderdeel) of an activity. Each component can have products."""
    __tablename__ = "activity_sub_registrations"
    __table_args__ = {"schema": "activities"}

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.activities.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    external_register_url = Column(String(500), nullable=True)
    external_registrations_url = Column(String(500), nullable=True)
    info_url = Column(String(500), nullable=True)
    registration_type_code = Column(String(10), nullable=False, default="INDIVIDUAL")  # code gevalideerd in de router-schema's (§8: geen cross-schema FK)
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
        from app.domains.media.api import MediaAsset
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


class ActivityProduct(TenantMixin, SoftDeleteMixin, Base):
    """A product (inschrijvingsoptie) within an activity component."""
    __tablename__ = "activity_products"
    __table_args__ = {"schema": "activities"}

    id = Column(Integer, primary_key=True, index=True)
    component_id = Column(Integer, ForeignKey("activities.activity_sub_registrations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    price = Column(Numeric(10, 2), nullable=False, default=0)
    member_price = Column(Numeric(10, 2), nullable=True)
    is_free = Column(Boolean, default=True, nullable=False)
    # Ter plaatse / op eigen budget te betalen (#373): inschrijven verplicht, maar
    # NIET via het portaal afrekenen. Telt — net als is_free — niet mee in het
    # Mollie-totaal. Sluit is_free uit (een product is betalend, gratis óf ter plaatse).
    pay_on_site = Column(Boolean, default=False, nullable=False, server_default="false")
    max_participants = Column(Integer, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    component = relationship("ActivitySubRegistration", back_populates="products")


class HistoryMixin:
    """Gedeelde audit-metadata voor de history-tabellen van dit component."""

    id = Column(Integer, primary_key=True, index=True)
    operation = Column(String(10), nullable=False)
    action = Column(String(40), nullable=False)
    source = Column(String(30), nullable=False)
    actor = Column(String(255), nullable=True)
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)


class RegistrationItemHistory(TenantMixin, HistoryMixin, Base):
    """Append-only audit van bestelregels (#84): elke insert/update/delete van een
    RegistrationItem, zodat wijzigingen aan een bestelling ná betaling traceerbaar
    zijn (bv. product wisselen naar een helper-variant, of een regel verwijderen)."""
    __tablename__ = "registration_item_history"
    __table_args__ = {"schema": "activities"}

    registration_item_id = Column(Integer, nullable=False, index=True)
    registration_id = Column(Integer, nullable=True, index=True)
    product_id = Column(Integer, nullable=True)
    quantity = Column(Integer, nullable=True)


class ActivityHistory(TenantMixin, HistoryMixin, Base):
    """Append-only audit van activiteiten (#189), incl. soft-delete."""
    __tablename__ = "activity_history"
    __table_args__ = {"schema": "activities"}

    activity_id = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=True)


class ActivityDateHistory(TenantMixin, HistoryMixin, Base):
    """Append-only audit van activiteitdatums (#189)."""
    __tablename__ = "activity_date_history"
    __table_args__ = {"schema": "activities"}

    activity_date_id = Column(Integer, nullable=False, index=True)
    activity_id = Column(Integer, nullable=True, index=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)


class ComponentHistory(TenantMixin, HistoryMixin, Base):
    """Append-only audit van onderdelen (activity_sub_registration) (#189)."""
    __tablename__ = "component_history"
    __table_args__ = {"schema": "activities"}

    component_id = Column(Integer, nullable=False, index=True)
    activity_id = Column(Integer, nullable=True, index=True)
    name = Column(String(255), nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    member_price = Column(Numeric(10, 2), nullable=True)


class ProductHistory(TenantMixin, HistoryMixin, Base):
    """Append-only audit van producten (activity_product) (#189)."""
    __tablename__ = "product_history"
    __table_args__ = {"schema": "activities"}

    product_id = Column(Integer, nullable=False, index=True)
    component_id = Column(Integer, nullable=True, index=True)
    name = Column(String(255), nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    member_price = Column(Numeric(10, 2), nullable=True)


class RegistrationTypeCode(Base):
    """Codetabel (verhuisd uit app/models/codes.py, #444). Public schema."""

    __tablename__ = "registration_type_codes"
    code = Column(String(10), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
