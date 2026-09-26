from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.kernel.codes import EnumColumn
from app.soft_delete import SoftDeleteMixin


class Role(Enum):
    """Wie wat mag (CR-12 fase 2).

    **In `auth` en niet in `mdm`** (§B4.1, verfijning van Koen op 25 september
    2026): masterdata beschrijft de wereld, en beveiligingsvocabulaire doet dat
    niet. Rollen — en later rechten, identiteitsleveranciers, de afbeelding van
    een externe groep op een interne rol — horen bij het domein waar Keycloak
    of een SAML-directory aan vast komt te hangen. Daarmee is `auth` het tweede
    fundamentdomein: het hangt alleen van `mdm` af, en andere schema's mogen
    een foreign key naar zijn codetabellen leggen.

    **Deze enum beslist niets.** `require_admin_ui` en `require_finance_ui`
    blijven bepalen wie wat mag; wat hier verandert is uitsluitend de vórm
    waarin de codes bestaan. Wie welke rol nodig heeft staat in
    `docs/rollen-en-rechten.md`, en dat document is bij deze wijziging
    ongewijzigd gebleven.
    """

    ADMIN = "ADMIN"
    FINANCE = "FINANCE"
    OPERATOR = "OPERATOR"
    ACCOUNT_ADMIN = "ACCOUNT_ADMIN"
    #: Ingetrokken sinds CR-12 fase 2. Bestonden sinds migratie 001, werden op
    #: elk scherm weggefilterd en niemand draagt ze. Het lid blijft, want een
    #: ingetrokken code houdt haar lid (§B4.3) — anders leest een oude rij
    #: terug als een kale string.
    MEMBER = "MEMBER"
    USER = "USER"



class User(SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    # Een User is een backoffice-account (rollen via user_roles). Lid-zijn staat
    # hier volledig los van: dat wordt afgeleid uit ContactDetail (e-mail ->
    # Person). Er is daarom bewust GEEN koppeling naar Person op dit model.
    id = Column(Integer, primary_key=True, index=True)
    # Uniciteit + lookup op email via een partiële unieke index
    # (WHERE deleted_at IS NULL) — zie migratie 051.
    email = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")


class UserRole(Base):
    """Eén roltoekenning, sinds #963 per werkruimte: ``tenant_id`` wijst de
    werkruimte aan; NULL betekent platformbreed (vandaag alleen OPERATOR).
    Surrogaat-PK omdat NULL niet in een samengestelde sleutel kan; de twee
    partiële unieke indexen van migratie 127 bewaken de uniciteit. Bewust
    GEEN tenant-mixin: rollen worden expliciet gefilterd (NULL ∪ actieve
    werkruimte), nooit stil door de tenant-listener."""
    __tablename__ = "user_roles"
    __table_args__ = {"schema": "auth"}

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("auth.users.id"), nullable=False)
    # CR-12 fase 2: wél een FK, want `auth.role_codes` staat sinds deze fase in
    # hetzelfde schema. De opmerking hierboven klopte voor de oude ligging in
    # `public`; de geldigheid zat toen alleen in de servicelaag, en dat is één
    # laag te hoog voor iets waar een rechtencontrole op steunt.
    role_code: Mapped[Role] = mapped_column(
        EnumColumn(Role, length=20), ForeignKey("auth.role_codes.code"),
        nullable=False)
    tenant_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="roles")


class ApiKey(Base):
    """Statische API-key per machine-consument (§19.3, fase 1b #399).

    Browser = HttpOnly-sessie; machine = API-key in de X-API-Key-header. De key
    zelf wordt nooit opgeslagen — enkel een SHA-256-hash met SECRET_KEY-pepper
    (zelfde recept als de OTP-hashing, #395). Intrekken = is_active op False."""

    __tablename__ = "api_keys"
    __table_args__ = {"schema": "auth"}

    id = Column(Integer, primary_key=True)
    # Wie/wat is de consument — puur beschrijvend (bv. "n8n-automations").
    name = Column(String(100), nullable=False, unique=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)


class LoginToken(Base):
    __tablename__ = "login_tokens"
    __table_args__ = {"schema": "auth"}

    id = Column(Integer, primary_key=True)
    # Eén login-flow voor iedereen: het e-mailadres is de identiteit. Er is geen
    # koppeling naar een account — capabilities worden na login per request
    # afgeleid uit de data.
    email = Column(String(255), nullable=True)
    token = Column(String(128), nullable=False, unique=True, index=True)
    # 6-cijferige code als alternatief voor de magic-link (cross-device login).
    otp_code = Column(String(64), nullable=True, index=True)  # SHA-256-hash (#395), nooit de code zelf
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, nullable=False, default=False)
    # Pogingteller voor OTP-brute-force-lockout (#268): na MAX_OTP_ATTEMPTS foute
    # codes wordt het token geïnvalideerd (used=True) en moet de gebruiker een
    # nieuwe code aanvragen.
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RoleCode(Base):
    """Welke rollen bestaan — het doel van de foreign keys (CR-12 fase 2).

    Verhuisd uit `public` naar `auth`. De oude tabel sleutelde op
    (code, taal) met een uniciteit op de code alleen, en liet dus precies één
    taal toe (#929).
    """

    __tablename__ = "role_codes"
    __table_args__ = {"schema": "auth"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc), nullable=False)


class RoleLabel(Base):
    """Het woord dat een scherm toont voor een rol, per taal."""

    __tablename__ = "role_labels"
    __table_args__ = {"schema": "auth"}

    code = Column(String(20), ForeignKey("auth.role_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)
