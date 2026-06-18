from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from app.database import Base


class LoginToken(Base):
    __tablename__ = "login_tokens"

    id = Column(Integer, primary_key=True)
    # Eén login-flow voor iedereen: het e-mailadres is de identiteit. Er is geen
    # koppeling naar een account — capabilities worden na login per request
    # afgeleid uit de data.
    email = Column(String(255), nullable=True)
    token = Column(String(128), nullable=False, unique=True, index=True)
    # 6-cijferige code als alternatief voor de magic-link (cross-device login).
    otp_code = Column(String(6), nullable=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, nullable=False, default=False)
    # Pogingteller voor OTP-brute-force-lockout (#268): na MAX_OTP_ATTEMPTS foute
    # codes wordt het token geïnvalideerd (used=True) en moet de gebruiker een
    # nieuwe code aanvragen.
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
