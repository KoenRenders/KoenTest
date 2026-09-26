from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.kernel.codes import EnumColumn
from app.soft_delete import SoftDeleteMixin


class Role(Enum):
    """Who may do what (CR-12 phase 2).

    **In `auth` and not in `mdm`** (§B4.1, Koen's refinement of 25 September
    2026): master data describes the world, and security vocabulary does not.
    Roles — and later permissions, identity providers, the mapping of an
    external group onto an internal role — belong to the domain that Keycloak
    or a SAML directory will attach to. That makes `auth` the second
    foundation domain: it depends on `mdm` only, and other schemas may put a
    foreign key to its code tables.

    **This enum decides nothing.** `require_admin_ui` and `require_finance_ui`
    still determine who may do what; the only thing that changes here is the
    *form* in which the codes exist. Which role is needed for what is in
    `docs/rollen-en-rechten.md`, and that document was left unchanged by this
    change.
    """

    ADMIN = "ADMIN"
    FINANCE = "FINANCE"
    OPERATOR = "OPERATOR"
    ACCOUNT_ADMIN = "ACCOUNT_ADMIN"
    #: Retired since CR-12 phase 2. They existed since migration 001, were
    #: filtered out on every screen, and nobody holds them. The member stays,
    #: because a retired code keeps its member (§B4.3) — otherwise an old row
    #: would read back as a bare string.
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
    # CR-12 phase 2: a FK after all, because since this phase `auth.role_codes`
    # lives in the same schema. The comment that used to stand here was right
    # for the old location in `public`; validity was then enforced only in the
    # service layer, and that is one layer too high for something a
    # permission check relies on.
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
    """Which roles exist — the target of the foreign keys (CR-12 phase 2).

    Moved from `public` to `auth`. The old table was keyed on
    (code, language) with a uniqueness constraint on the code alone, and so
    allowed exactly one language (#929).
    """

    __tablename__ = "role_codes"
    __table_args__ = {"schema": "auth"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc), nullable=False)


class RoleLabel(Base):
    """The word a screen shows for a role, per language."""

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
