from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Numeric, cast, func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.config import settings
from app.database import get_db
from app.models.activity import Activity, ActivityDate
from app.models.business_event import BusinessEvent
from app.models.member import Member, Membership
from app.models.idea import Idea
from app.models.user import User
from app.domains.payment_status.models import PaymentRecord

router = APIRouter(tags=["admin"])


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    today = date.today()
    return {
        "members": db.query(func.count(Member.id)).scalar(),
        "active_members": db.query(func.count(Membership.id))
            .filter(Membership.year == today.year, Membership.is_active == True)
            .scalar(),
        "upcoming_activities": db.query(func.count(func.distinct(ActivityDate.activity_id)))
            .filter(func.coalesce(ActivityDate.end_date, ActivityDate.start_date) >= today)
            .scalar(),
        "open_ideas": db.query(func.count(Idea.id))
            .filter(Idea.is_reviewed == False)
            .scalar(),
        "outstanding_balance": float(
            db.query(func.coalesce(func.sum(PaymentRecord.amount), 0))
            .filter(PaymentRecord.status.notin_(["paid", "cancelled", "failed"]))
            .scalar() or 0
        ),
    }


@router.get("/business-events")
def get_business_event_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Geaggregeerd rapport over de first-party business-events (#152, laag 2):
    tellingen per event-type (alle tijd + laatste 30 dagen) en de omzet uit
    bevestigde betalingen. Bevat GEEN PII — enkel geaggregeerde, niet-
    identificerende cijfers afgeleid uit de event-payloads."""
    since_30d = datetime.now(timezone.utc) - timedelta(days=30)

    def _counts(query):
        return {et: c for et, c in query.group_by(BusinessEvent.event_type).all()}

    totals = _counts(db.query(BusinessEvent.event_type, func.count(BusinessEvent.id)))
    totals_30d = _counts(
        db.query(BusinessEvent.event_type, func.count(BusinessEvent.id))
        .filter(BusinessEvent.occurred_at >= since_30d)
    )

    # Omzet = som van payload->>'amount' over bevestigde betalingen. De cast naar
    # Numeric gebeurt in SQL; ontbrekende/lege bedragen tellen als NULL (genegeerd).
    def _revenue(query):
        return float(query.scalar() or 0)

    amount_expr = func.sum(cast(BusinessEvent.payload["amount"].astext, Numeric))
    revenue = _revenue(
        db.query(func.coalesce(amount_expr, 0))
        .filter(BusinessEvent.event_type == "betaling_succes")
    )
    revenue_30d = _revenue(
        db.query(func.coalesce(amount_expr, 0))
        .filter(BusinessEvent.event_type == "betaling_succes",
                BusinessEvent.occurred_at >= since_30d)
    )

    return {
        "period_days": 30,
        "totals": totals,
        "totals_30d": totals_30d,
        "revenue_paid_eur": revenue,
        "revenue_paid_eur_30d": revenue_30d,
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


# ── Ledendata-wijzigingen sinds datum (#82) ───────────────────────────────────

@router.get("/member-changes")
def list_member_changes(
    since: date = Query(..., description="Toon wijzigingen vanaf deze datum (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Alle ledendata-wijzigingen sinds `since`, voor manuele overname in Raak
    Nationaal. Admin-only; bevat persoonsdata."""
    from app.services.member_changes import member_changes_since
    return member_changes_since(db, since)


@router.get("/member-changes/export")
def export_member_changes(
    since: date = Query(..., description="Toon wijzigingen vanaf deze datum (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Dezelfde wijzigingen als .xlsx-download."""
    from app.services.member_changes import member_changes_since, build_member_changes_xlsx
    content = build_member_changes_xlsx(member_changes_since(db, since))
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="ledenwijzigingen-vanaf-{since}.xlsx"'},
    )
