"""System info for the system screen (#444, §21): the curated whitelist of
settings — never a secret.

This was `app/ui/admin_api.py`, the JSON composer under `/api/v1/admin`. Its
two routes went with CR-13 phase 4b (#1251); what the system screen reads
stayed, and the file is named after it since phase 4c.
"""

from datetime import datetime, timezone

from app.config import settings


def _mollie_mode(api_key: str | None) -> str:
    """Leid de Mollie-modus af uit het key-prefix — NOOIT de sleutel zelf."""
    if not api_key:
        return "niet geconfigureerd"
    if api_key.startswith("live_"):
        return "live"
    if api_key.startswith("test_"):
        return "test"
    return "onbekend"


def system_info() -> dict:
    """Gecureerde runtime/config-info voor het systeemscherm (dat zelf admin-only is). Bewust opgebouwd uit een
    expliciete whitelist (geen model_dump) zodat secrets nooit kunnen lekken:
    SECRET_KEY, DATABASE_URL, MOLLIE_API_KEY en GMAIL_APP_PASSWORD blijven eruit."""
    return {
        "version": settings.app_version,
        "commit": settings.git_sha,
        "environment": settings.app_env,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "timezone": "UTC",
        "flags": {
            "log_level": settings.log_level,
            "debug": settings.debug,
            "sql_echo": settings.sql_echo,
        },
        "limits": {
            "max_item_quantity": settings.max_item_quantity,
            "max_registrations_per_email": settings.max_registrations_per_email,
        },
        "membership": {
            "price_full": str(settings.membership_price_full),
            "price_half": str(settings.membership_price_half),
            "half_price_start_md": settings.membership_half_price_start_md,
            "half_price_end_md": settings.membership_half_price_end_md,
            "next_year_from_md": settings.membership_next_year_from_md,
            "renewal_start_md": settings.membership_renewal_start_md,
        },
        "urls": {
            "frontend_url": settings.frontend_url,
            "public_url": settings.public_url,
        },
        "mollie_mode": _mollie_mode(settings.mollie_api_key),
    }
