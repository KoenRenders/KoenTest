"""Admin-API-composer: dashboard-stats + systeeminfo (#444, §21).

Composer-module naast changes_ui/system_ui: leest cross-domain via de facades
(dashboard-tellers) en de gecureerde settings-whitelist (systeeminfo — nooit
secrets). (verhuisd uit app/routers/admin.py, #444)
"""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.domains.auth.api import User, get_current_admin


def _open_tasks(db):
    """Open werkbank-taken (#398) — vervangt de oude 'ongelezen ideeën'-teller."""
    from app.domains.workflow.api import open_count

    return open_count(db, ["ADMIN", "FINANCE"])


from app.domains.activities.api import ActivityDate
from app.domains.membership.api import Membership
from app.domains.mdm.api import Member
from app.domains.payment.api import PaymentRecord
from app.domains.payment.api import current_membership_counts

router = APIRouter(tags=["admin"])


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    today = date.today()
    # Vandaag-geldige lidmaatschappen → gezinnen + personen (#297), zelfde telling
    # als de chatbot (#294), zodat dashboard en Raakje nooit tegenspreken.
    active_member_households, active_member_persons = current_membership_counts(db, today)
    return {
        "members": db.query(func.count(Member.id)).scalar(),
        "active_members": db.query(func.count(Membership.id))
            .filter(Membership.year == today.year, Membership.is_active == True)
            .scalar(),
        "active_member_households": active_member_households,
        "active_member_persons": active_member_persons,
        "upcoming_activities": db.query(func.count(func.distinct(ActivityDate.activity_id)))
            .filter(func.coalesce(ActivityDate.end_date, ActivityDate.start_date) >= today)
            .scalar(),
        "open_tasks": _open_tasks(db),
        "outstanding_balance": float(
            db.query(func.coalesce(func.sum(PaymentRecord.amount), 0))
            .filter(PaymentRecord.status.notin_(["paid", "cancelled", "failed"]))
            .scalar() or 0
        ),
    }


def _mollie_mode(api_key: str | None) -> str:
    """Leid de Mollie-modus af uit het key-prefix — NOOIT de sleutel zelf."""
    if not api_key:
        return "niet geconfigureerd"
    if api_key.startswith("live_"):
        return "live"
    if api_key.startswith("test_"):
        return "test"
    return "onbekend"


@router.get("/system-info")
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
