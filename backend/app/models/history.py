"""History-tabellen (append-only) voor betalingen en gezins-/persoonsmasterdata.

Elke history-rij is een volledige momentopname van een bron-rij op het moment
van een wijziging, aangevuld met audit-metadata:

  operation    mechanisch DB-effect: "insert" / "update" / "delete"
  action       semantische business-actie, bv. "family_registered"
  source       herkomst: "system" / "registration" / "mollie" / "admin_manual" / ...
  actor        e-mail van de admin, of None bij systeem/Mollie
  recorded_at  tijdstip van de wijziging

Bewust GEEN ForeignKey naar de brontabel en GEEN cascade: de history overleeft
het verwijderen van de bron-rij (de delete wordt eerst als snapshot vastgelegd).
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, Numeric
from app.database import Base


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class HistoryMixin:
    """Gedeelde audit-metadata voor alle history-tabellen."""

    id = Column(Integer, primary_key=True, index=True)
    operation = Column(String(10), nullable=False)   # insert / update / delete
    action = Column(String(40), nullable=False)       # semantische business-actie
    source = Column(String(30), nullable=False)       # system / registration / mollie / ...
    actor = Column(String(255), nullable=True)        # admin-e-mail of None
    recorded_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False, index=True)


class MembershipHistory(HistoryMixin, Base):
    __tablename__ = "membership_history"

    membership_id = Column(Integer, nullable=False, index=True)
    member_id = Column(Integer, nullable=True, index=True)
    year = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)


class RegistrationItemHistory(HistoryMixin, Base):
    """Append-only audit van bestelregels (#84): elke insert/update/delete van een
    RegistrationItem, zodat wijzigingen aan een bestelling ná betaling traceerbaar
    zijn (bv. product wisselen naar een helper-variant, of een regel verwijderen)."""
    __tablename__ = "registration_item_history"

    registration_item_id = Column(Integer, nullable=False, index=True)
    registration_id = Column(Integer, nullable=True, index=True)
    product_id = Column(Integer, nullable=True)
    quantity = Column(Integer, nullable=True)


class PaymentRecordHistory(HistoryMixin, Base):
    __tablename__ = "payment_record_history"

    payment_record_id = Column(String(36), nullable=False, index=True)
    payable_type = Column(String(50), nullable=True)
    payable_id = Column(Integer, nullable=True)
    amount = Column(Numeric(10, 2), nullable=True)
    amount_paid = Column(Numeric(10, 2), nullable=True)
    method = Column(String(20), nullable=True)
    status = Column(String(20), nullable=True)
    type = Column(String(10), nullable=True)          # charge / refund (#83)
    refund_of_id = Column(String(36), nullable=True)  # charge die deze refund terugdraait (#83)
    gateway_payment_id = Column(String(36), nullable=True)
    note = Column(String(200), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)


class ActivityHistory(HistoryMixin, Base):
    """Append-only audit van activiteiten (#189), incl. soft-delete."""
    __tablename__ = "activity_history"

    activity_id = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=True)


class ActivityDateHistory(HistoryMixin, Base):
    """Append-only audit van activiteitdatums (#189)."""
    __tablename__ = "activity_date_history"

    activity_date_id = Column(Integer, nullable=False, index=True)
    activity_id = Column(Integer, nullable=True, index=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)


class ComponentHistory(HistoryMixin, Base):
    """Append-only audit van onderdelen (activity_sub_registration) (#189)."""
    __tablename__ = "component_history"

    component_id = Column(Integer, nullable=False, index=True)
    activity_id = Column(Integer, nullable=True, index=True)
    name = Column(String(255), nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    member_price = Column(Numeric(10, 2), nullable=True)


class ProductHistory(HistoryMixin, Base):
    """Append-only audit van producten (activity_product) (#189)."""
    __tablename__ = "product_history"

    product_id = Column(Integer, nullable=False, index=True)
    component_id = Column(Integer, nullable=True, index=True)
    name = Column(String(255), nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    member_price = Column(Numeric(10, 2), nullable=True)
