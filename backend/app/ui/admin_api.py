"""System info for the system screen (#444, §21): the curated whitelist of
settings — never a secret.

No JSON route is left in this file (CR-13 phase 4b, #1251): `/admin/system-info`
and `/admin/stats` had no caller but tests. `get_system_info` stays because
`system_ui.py` calls it in process; it moves in phase 4c. The stats handler is
gone as a whole — no screen read it.
"""

from datetime import datetime, timezone

from fastapi import Depends

from app.config import settings
from app.domains.auth.api import User, get_current_admin


def _mollie_mode(api_key: str | None) -> str:
    """Leid de Mollie-modus af uit het key-prefix — NOOIT de sleutel zelf."""
    if not api_key:
        return "niet geconfigureerd"
    if api_key.startswith("live_"):
        return "live"
    if api_key.startswith("test_"):
        return "test"
    return "onbekend"


def get_system_info(_admin: User = Depends(get_current_admin)):
    """Gecureerde, admin-only runtime/config-info. Bewust opgebouwd uit een
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
