"""Per-tenant config + secrets in de DB (§7, fase 5b #406).

Config die per tenant verschilt (afzendnaam, canonieke base-URL, taal,
Mollie-key, mail-modus) leeft DB-beheerd in ``kernel_tenant_settings``;
de ``.env``-settings blijven de default zolang een sleutel niet gezet is.
Secrets (Mollie-key) worden **versleuteld** opgeslagen (Fernet, sleutel
afgeleid van ``SECRET_KEY``). Infra-secrets (DB-wachtwoord, SECRET_KEY zelf)
blijven in ``.env`` — die zijn niet tenant-gebonden.

Bekende sleutels:
- ``display_name``   — afzend-/merknaam (default "Raak Millegem")
- ``base_url``       — canonieke publieke origin voor links in mails/redirects
- ``mollie_api_key`` — (secret) per-tenant Mollie-key; default env-key
- ``mail_mode``      — "send" (default) of "log_only" (demo-tenant: mails
                       worden enkel gelogd, nooit echt verstuurd)
- ``noindex``        — "1" = robots-noindex voor deze tenant (demo)
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Session

from app.database import Base
from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id


class TenantSetting(Base):
    """Eén config-sleutel voor één tenant. Secrets staan in ``value_encrypted``
    (Fernet); gewone config in ``value``. Bewust géén TenantMixin: deze tabel
    is platform-plumbing en wordt altijd expliciet op tenant_id bevraagd."""

    __tablename__ = "kernel_tenant_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_tenant_setting"),)

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    key = Column(String(100), nullable=False)
    value = Column(Text, nullable=True)
    value_encrypted = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)


def _fernet() -> Fernet:
    from app.config import settings

    # Deterministische afleiding uit SECRET_KEY: geen extra key-management,
    # zelfde sleutel op alle replica's van dezelfde omgeving.
    digest = hashlib.sha256(f"tenant-config:{settings.secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _actieve_tenant(tenant_id: int | None) -> int:
    return tenant_id or current_tenant_id.get() or DEFAULT_TENANT_ID


def get_setting(db: Session, key: str, default: str | None = None,
                tenant_id: int | None = None) -> str | None:
    row = (db.query(TenantSetting)
           .filter(TenantSetting.tenant_id == _actieve_tenant(tenant_id),
                   TenantSetting.key == key).first())
    if row is None:
        return default
    if row.value_encrypted is not None:
        return _fernet().decrypt(row.value_encrypted.encode()).decode()
    return row.value if row.value is not None else default


def set_setting(db: Session, key: str, value: str | None, *, secret: bool = False,
                tenant_id: int | None = None) -> None:
    tenant = _actieve_tenant(tenant_id)
    row = (db.query(TenantSetting)
           .filter(TenantSetting.tenant_id == tenant, TenantSetting.key == key).first())
    if row is None:
        row = TenantSetting(tenant_id=tenant, key=key)
        db.add(row)
    if value is None:
        row.value = None
        row.value_encrypted = None
    elif secret:
        row.value = None
        row.value_encrypted = _fernet().encrypt(value.encode()).decode()
    else:
        row.value = value
        row.value_encrypted = None


# ── Afgeleide helpers (met .env als default) ───────────────────────────────────

def tenant_base_url(db: Session, tenant_id: int | None = None) -> str:
    """Canonieke publieke origin van de actieve tenant, voor absolute URL's in
    mails, Mollie-redirects en SEO. Default: de globale FRONTEND_URL."""
    from app.config import settings

    return (get_setting(db, "base_url", tenant_id=tenant_id)
            or settings.frontend_url).rstrip("/")


def tenant_display_name(db: Session, tenant_id: int | None = None) -> str:
    return get_setting(db, "display_name", tenant_id=tenant_id) or "Raak Millegem"


def tenant_mollie_key(db: Session, tenant_id: int | None = None) -> str | None:
    from app.config import settings

    return get_setting(db, "mollie_api_key", tenant_id=tenant_id) or settings.mollie_api_key


def tenant_mail_mode(db: Session, tenant_id: int | None = None) -> str:
    return get_setting(db, "mail_mode", tenant_id=tenant_id) or "send"


def tenant_language(db: Session, tenant_id: int | None = None) -> str:
    """Taal van de tenant (#407-T) — default nl_BE; voorbereiding meertaligheid."""
    return get_setting(db, "language", tenant_id=tenant_id) or "nl_BE"


def _int_setting(db: Session, key: str, fallback: int,
                 tenant_id: int | None = None) -> int:
    value = get_setting(db, key, tenant_id=tenant_id)
    try:
        return int(value) if value not in (None, "") else fallback
    except (TypeError, ValueError):
        return fallback


# ── Per-tenant e-mail-, betaal-, limiet- en analytics-config (#451). DB-sleutel
#    wint, de .env-setting blijft de fallback (net als tenant_mollie_key). ──────

def tenant_gmail_user(db: Session, tenant_id: int | None = None) -> str | None:
    from app.config import settings
    return get_setting(db, "gmail_user", tenant_id=tenant_id) or settings.gmail_user


def tenant_gmail_app_password(db: Session, tenant_id: int | None = None) -> str | None:
    from app.config import settings
    return (get_setting(db, "gmail_app_password", tenant_id=tenant_id)
            or settings.gmail_app_password)


def tenant_gmail_from(db: Session, tenant_id: int | None = None) -> str | None:
    from app.config import settings
    return get_setting(db, "gmail_from", tenant_id=tenant_id) or settings.gmail_from


def tenant_payment_iban(db: Session, tenant_id: int | None = None) -> str | None:
    from app.config import settings
    return get_setting(db, "payment_iban", tenant_id=tenant_id) or settings.payment_iban


def tenant_payment_beneficiary(db: Session, tenant_id: int | None = None) -> str | None:
    from app.config import settings
    return (get_setting(db, "payment_beneficiary", tenant_id=tenant_id)
            or settings.payment_beneficiary)


def tenant_payment_term_days(db: Session, tenant_id: int | None = None) -> int:
    from app.config import settings
    return _int_setting(db, "payment_term_days", settings.payment_term_days, tenant_id)


def tenant_max_item_quantity(db: Session, tenant_id: int | None = None) -> int:
    from app.config import settings
    return _int_setting(db, "max_item_quantity", settings.max_item_quantity, tenant_id)


def tenant_max_registrations_per_email(db: Session, tenant_id: int | None = None) -> int:
    from app.config import settings
    return _int_setting(db, "max_registrations_per_email",
                        settings.max_registrations_per_email, tenant_id)


def tenant_umami_src(db: Session, tenant_id: int | None = None) -> str:
    from app.config import settings
    return get_setting(db, "umami_src", tenant_id=tenant_id) or settings.umami_src


def tenant_umami_website_id(db: Session, tenant_id: int | None = None) -> str:
    from app.config import settings
    return (get_setting(db, "umami_website_id", tenant_id=tenant_id)
            or settings.umami_website_id)


def tenant_membership_config(db: Session | None = None,
                             tenant_id: int | None = None) -> dict:
    """Lidmaatschapsprijzen en -datumgrenzen van de actieve tenant (branding-
    slice #407): DB-sleutels winnen, de .env-settings blijven de default.
    Zonder meegegeven sessie wordt een eigen SessionLocal geopend, zodat ook
    servicefuncties zonder db-parameter tenant-bewust zijn."""
    from decimal import Decimal

    from app.config import settings

    eigen_sessie = db is None
    if eigen_sessie:
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        def _s(key: str, default):
            waarde = get_setting(db, key, tenant_id=tenant_id)
            return waarde if waarde is not None else default

        return {
            "price_full": Decimal(str(_s("membership_price_full", settings.membership_price_full))),
            "price_half": Decimal(str(_s("membership_price_half", settings.membership_price_half))),
            "half_start_md": _s("membership_half_price_start_md", settings.membership_half_price_start_md),
            "half_end_md": _s("membership_half_price_end_md", settings.membership_half_price_end_md),
            "next_year_from_md": _s("membership_next_year_from_md", settings.membership_next_year_from_md),
            "renewal_start_md": _s("membership_renewal_start_md", settings.membership_renewal_start_md),
        }
    finally:
        if eigen_sessie and db is not None:
            db.close()
