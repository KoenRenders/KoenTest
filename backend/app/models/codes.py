from datetime import datetime
from sqlalchemy import Column, String, DateTime
from app.database import Base

class GenderCode(Base):
    __tablename__ = "gender_codes"
    code = Column(String(10), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class ContactTypeCode(Base):
    __tablename__ = "contact_type_codes"
    code = Column(String(10), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class RoleCode(Base):
    __tablename__ = "role_codes"
    code = Column(String(10), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class RegistrationTypeCode(Base):
    __tablename__ = "registration_type_codes"
    code = Column(String(10), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class PaymentStatusCode(Base):
    __tablename__ = "payment_status_codes"
    code = Column(String(10), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
