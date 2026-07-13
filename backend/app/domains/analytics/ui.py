"""Server-rendered analyse-dashboard (fase 4c-3, #404 — §5.8/§23):
event-tellingen en omzet met server-gerenderde SVG (geen JS-eiland — de
architect-beslissing bij het dashboard).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import require_admin_ui
from app.domains.analytics.models import BusinessEvent
from app.ui import admin_nav, templates

router = APIRouter(include_in_schema=False)


def _weekly_counts(db: Session, weeks: int = 12) -> list[dict]:
    """Events per week (alle types samen) voor de SVG-staafgrafiek."""
    since = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    rows = (db.query(func.date_trunc("week", BusinessEvent.occurred_at),
                     func.count(BusinessEvent.id))
            .filter(BusinessEvent.occurred_at >= since)
            .group_by(func.date_trunc("week", BusinessEvent.occurred_at))
            .order_by(func.date_trunc("week", BusinessEvent.occurred_at))
            .all())
    by_week = {week.date(): count for week, count in rows}
    # Vul lege weken op zodat de as compleet is.
    first = datetime.now(timezone.utc) - timedelta(weeks=weeks - 1)
    start = (first - timedelta(days=first.weekday())).date()
    out = []
    for i in range(weeks):
        week = start + timedelta(weeks=i)
        out.append({"week": week, "count": by_week.get(week, 0)})
    return out


def _bars_svg(data: list[dict], width: int = 720, height: int = 180) -> str:
    """Kale, server-gerenderde SVG-staafgrafiek (§23-patroon: geen chart-lib)."""
    if not data:
        return ""
    max_count = max((d["count"] for d in data), default=0) or 1
    pad = 24
    bar_w = (width - 2 * pad) / len(data)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="Events per week" class="w-full h-auto">']
    for i, d in enumerate(data):
        h = (height - 2 * pad) * d["count"] / max_count
        x = pad + i * bar_w
        y = height - pad - h
        parts.append(
            f'<rect x="{x + 2:.1f}" y="{y:.1f}" width="{bar_w - 4:.1f}" '
            f'height="{h:.1f}" rx="3" fill="#1d4ed8">'
            f'<title>{d["week"].strftime("%d-%m")}: {d["count"]}</title></rect>')
        if i % 2 == 0:
            parts.append(
                f'<text x="{x + bar_w / 2:.1f}" y="{height - 6}" font-size="10" '
                f'text-anchor="middle" fill="#6b7280">{d["week"].strftime("%d-%m")}</text>')
    parts.append("</svg>")
    return "".join(parts)


@router.get("/admin/analyse", response_class=HTMLResponse)
def analyse_page(request: Request, db: Session = Depends(get_db),
                 email: str = Depends(require_admin_ui)):
    from app.routers.admin import get_business_event_stats

    stats = get_business_event_stats(db=db, _admin=None)  # type: ignore[arg-type]
    weekly = _weekly_counts(db)
    nav = admin_nav("/admin/analyse")
    return templates.TemplateResponse(request, "analyse.html", {
        "nav_items": nav, "stats": stats, "chart_svg": _bars_svg(weekly),
    })
