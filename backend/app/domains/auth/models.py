from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.kernel.codes import CodeEnum, EnumColumn
from app.soft_delete import SoftDeleteMixin


class Role(CodeEnum):
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
    #: CR-24 (#1722): master data, and the three roles the webshop needs
    #: (CR-21). In the enum in the same change as the migration that adds the
    #: codes: a stored code that is no member raises on read (F9).
    MASTERDATA = "MASTERDATA"
    PRICING = "PRICING"
    SALES = "SALES"
    STOCK = "STOCK"
    #: Retired since CR-12 phase 2. They existed since migration 001, were
    #: filtered out on every screen, and nobody holds them. The member stays,
    #: because a retired code keeps its member (§B4.3) — otherwise an old row
    #: would read back as a bare string.
    MEMBER = "MEMBER"
    USER = "USER"


class Right(CodeEnum):
    """What a gate asks for (CR-24 §B1, #1722): a right, never a role's name.

    Per kind of object two rights (D1): `<object>.view` for a route that only
    reads, `<object>.manage` for one that changes — for master data
    `party.masterdata` and `product.masterdata`. `assistant.use` and
    `workbench.use` have no changing counterpart. A role is a bundle of these,
    kept as rows in `auth.role_rights`; who holds what is data, and this enum
    only says which rights exist.
    """

    ACTIVITY_VIEW = "activity.view"
    ACTIVITY_MANAGE = "activity.manage"
    FORM_VIEW = "form.view"
    FORM_MANAGE = "form.manage"
    PAGE_VIEW = "page.view"
    PAGE_MANAGE = "page.manage"
    MEDIA_VIEW = "media.view"
    MEDIA_MANAGE = "media.manage"
    DESIGN_VIEW = "design.view"
    DESIGN_MANAGE = "design.manage"
    NEWSLETTER_VIEW = "newsletter.view"
    NEWSLETTER_MANAGE = "newsletter.manage"
    MEETING_VIEW = "meeting.view"
    MEETING_MANAGE = "meeting.manage"
    REPORT_VIEW = "report.view"
    REPORT_MANAGE = "report.manage"
    ASSISTANT_USE = "assistant.use"
    PARTY_VIEW = "party.view"
    PARTY_MASTERDATA = "party.masterdata"
    PRODUCT_VIEW = "product.view"
    PRODUCT_MASTERDATA = "product.masterdata"
    PRICE_VIEW = "price.view"
    PRICE_MANAGE = "price.manage"
    SALES_VIEW = "sales.view"
    SALES_MANAGE = "sales.manage"
    STOCK_VIEW = "stock.view"
    STOCK_MANAGE = "stock.manage"
    PAYMENT_VIEW = "payment.view"
    PAYMENT_MANAGE = "payment.manage"
    WORKBENCH_USE = "workbench.use"
    USER_VIEW = "user.view"
    USER_MANAGE = "user.manage"
    SETTINGS_VIEW = "settings.view"
    SETTINGS_MANAGE = "settings.manage"
    PLATFORM_VIEW = "platform.view"
    PLATFORM_MANAGE = "platform.manage"


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
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

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
        EnumColumn(Role, length=20), ForeignKey("auth.role_codes.code"), nullable=False
    )
    tenant_id = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user = relationship("User", back_populates="roles")


class LoginPurpose(CodeEnum):
    """What a code sent by mail is for (CR-22 §B1 D2, #1704).

    One code mechanism for all three: the fifteen minutes, the hashed code,
    the five attempts and the one live token per address (#268, #395) hold
    whatever the purpose. A second token table would have to repeat them, and
    would drift.

    No standard names this (CR-22 §B3a); a code list as every list here.
    """

    SIGN_IN = "SIGN_IN"
    #: The person and its confirmed address are made when this code is
    #: entered; the four fields wait in the token's `payload` until then.
    CREATE_ACCOUNT = "CREATE_ACCOUNT"
    #: A new or changed address counts once this code is entered.
    CONFIRM_ADDRESS = "CONFIRM_ADDRESS"


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
    otp_code = Column(
        String(64), nullable=True, index=True
    )  # SHA-256-hash (#395), nooit de code zelf
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, nullable=False, default=False)
    # Pogingteller voor OTP-brute-force-lockout (#268): na MAX_OTP_ATTEMPTS foute
    # codes wordt het token geïnvalideerd (used=True) en moet de gebruiker een
    # nieuwe code aanvragen.
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # CR-22 (#1704): what entering this code does. Every token written before
    # the column existed was a sign-in, hence the default on both sides.
    purpose: Mapped[LoginPurpose] = mapped_column(
        EnumColumn(LoginPurpose, length=20),
        ForeignKey("auth.login_purpose_codes.code"),
        nullable=False,
        default=LoginPurpose.SIGN_IN,
        server_default="SIGN_IN",
    )
    # What the purpose needs to do its work: the four fields of an account
    # that does not exist yet, or the id of the contact detail to confirm. The
    # token has no tenant and no person of its own (CR-22 §C1), so this is
    # where they travel. NULL for a sign-in.
    payload = Column(JSON, nullable=True)


class LoginPurposeCode(Base):
    """Which purposes exist — the target of the foreign key (CR-22, #1704)."""

    __tablename__ = "login_purpose_codes"
    __table_args__ = {"schema": "auth"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class LoginPurposeLabel(Base):
    """The word for a purpose, per language (CR-22, #1704)."""

    __tablename__ = "login_purpose_labels"
    __table_args__ = {"schema": "auth"}

    code = Column(String(20), ForeignKey("auth.login_purpose_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


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
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class RoleLabel(Base):
    """The word a screen shows for a role, per language."""

    __tablename__ = "role_labels"
    __table_args__ = {"schema": "auth"}

    code = Column(String(20), ForeignKey("auth.role_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class RightCode(Base):
    """Which rights exist — the target of the foreign key (CR-24, #1722)."""

    __tablename__ = "right_codes"
    __table_args__ = {"schema": "auth"}

    code = Column(String(50), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class RightLabel(Base):
    """The word for a right, per language (CR-24, #1722)."""

    __tablename__ = "right_labels"
    __table_args__ = {"schema": "auth"}

    code = Column(String(50), ForeignKey("auth.right_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class RoleRight(Base):
    """One right in one role's bundle (CR-24 §B1 D2, #1722).

    A role is a bundle of rights and the bundle is these rows: written by a
    migration, the same in every workspace — hence no tenant column, and
    deliberately no tenant mixin. No screen composes them (R14); one that
    later does edits these same rows.
    """

    __tablename__ = "role_rights"
    __table_args__ = {"schema": "auth"}

    role_code: Mapped[Role] = mapped_column(
        EnumColumn(Role, length=20), ForeignKey("auth.role_codes.code"), primary_key=True
    )
    right_code: Mapped[Right] = mapped_column(
        EnumColumn(Right, length=50), ForeignKey("auth.right_codes.code"), primary_key=True
    )
