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
    recorded_at = Column(DateTime, default=_now_utc, nullable=False, index=True)


class PersonHistory(HistoryMixin, Base):
    __tablename__ = "person_history"

    person_id = Column(Integer, nullable=False, index=True)
    last_name = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    gender_code = Column(String(10), nullable=True)


class MemberHistory(HistoryMixin, Base):
    __tablename__ = "member_history"

    member_id = Column(Integer, nullable=False, index=True)
    board_member_id = Column(Integer, nullable=True)


class MemberPersonHistory(HistoryMixin, Base):
    __tablename__ = "member_person_history"

    member_person_id = Column(Integer, nullable=False, index=True)
    member_id = Column(Integer, nullable=True, index=True)
    person_id = Column(Integer, nullable=True, index=True)
    relation_type = Column(String(10), nullable=True)


class MembershipHistory(HistoryMixin, Base):
    __tablename__ = "membership_history"

    membership_id = Column(Integer, nullable=False, index=True)
    member_id = Column(Integer, nullable=True, index=True)
    year = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)


class AddressHistory(HistoryMixin, Base):
    __tablename__ = "address_history"

    address_id = Column(Integer, nullable=False, index=True)
    person_id = Column(Integer, nullable=True, index=True)
    street = Column(String(255), nullable=True)
    house_number = Column(String(20), nullable=True)
    bus_number = Column(String(10), nullable=True)
    postal_code_id = Column(Integer, nullable=True)


class ContactDetailHistory(HistoryMixin, Base):
    __tablename__ = "contact_detail_history"

    contact_detail_id = Column(Integer, nullable=False, index=True)
    person_id = Column(Integer, nullable=True, index=True)
    contact_type_code = Column(String(10), nullable=True)
    value = Column(String(255), nullable=True)
    is_primary = Column(Boolean, nullable=True)


class PaymentRecordHistory(HistoryMixin, Base):
    __tablename__ = "payment_record_history"

    payment_record_id = Column(String(36), nullable=False, index=True)
    payable_type = Column(String(50), nullable=True)
    payable_id = Column(Integer, nullable=True)
    amount = Column(Numeric(10, 2), nullable=True)
    amount_paid = Column(Numeric(10, 2), nullable=True)
    method = Column(String(20), nullable=True)
    status = Column(String(20), nullable=True)
    gateway_payment_id = Column(String(36), nullable=True)
    note = Column(String(200), nullable=True)
    paid_at = Column(DateTime, nullable=True)
