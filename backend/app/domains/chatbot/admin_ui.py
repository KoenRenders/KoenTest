"""The AI cost screen (#978): what the AI cost this department, and each call.

Reached from /admin/info and behind the same door (`require_admin_ui`) —
Koen, 16 September 2026. The list shows who asked (`actor`), also his
decision; it never shows what was sent (see `chatbot/costs.py`).

The totals and the list come from `cost_per_period` and `list_calls`: the
screen is the first user of the reader CR-10's budget will count with, which
is the test of whether that reader is right.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import require_admin_ui
from app.domains.chatbot.api import (AI_CAPABILITY, AI_PROVIDER, AI_STATUS, AI_SURFACE,
                                     AiCapability, AiProvider, AiStatus, AiSurface,
                                     cost_per_period, list_calls, month_period)
from app.domains.chatbot.viewmodels import (AiCallLine, AiCallListView, AiCostLine,
                                            AiCostView)
from app.i18n import _, current_locale
from app.kernel.clock import belgian_today
from app.kernel.codes import code_label, register_tones, tone
from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id
from app.ui import admin_nav, is_fragment_request, templates

router = APIRouter(include_in_schema=False)

PATH = "/admin/info/ai-kosten"
PER_PAGE = 50

# CR-12 phase 4: the words of surface, capability, status and provider come
# from their label tables; the dictionaries that stood here became their seed.
# The badge tone stays here, next to the screen that draws it (§B4.5): a
# refusal — ours or the provider's — is a warning, not a failure.
register_tones(AI_STATUS.name, {
    AiStatus.OK: "green",
    AiStatus.BLOCKED: "yellow",
    AiStatus.ERROR: "red",
    AiStatus.MODERATED: "yellow",
})


def _what(surface: AiSurface, capability: AiCapability) -> str:
    return (f"{code_label(AI_SURFACE.name, surface)} · "
            f"{code_label(AI_CAPABILITY.name, capability)}")


def _provider(provider: Optional[AiProvider]) -> str:
    return code_label(AI_PROVIDER.name, provider) if provider else "—"


def _number(value: Decimal, places: int) -> str:
    return f"{value:,.{places}f}".replace(",", " ").replace(".", ",")


def _money(amounts: dict[str, Decimal]) -> str:
    """Per currency, never added together. Four decimals: an image costs 0,045."""
    return " + ".join(f"{_number(v, 4)} {c}" for c, v in sorted(amounts.items())) or "—"


def _month(value: str) -> date:
    try:
        jaar, maand = (int(x) for x in value.split("-", 1))
        return date(jaar, maand, 1)
    except (ValueError, TypeError):
        return belgian_today().replace(day=1)


def _shift(d: date, months: int) -> str:
    index = d.year * 12 + d.month - 1 + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _call_lines(db: Session, tenant: int, page: int) -> tuple[list[AiCallLine], bool]:
    from zoneinfo import ZoneInfo

    rows, has_next = list_calls(db, tenant_id=tenant, page=page, per_page=PER_PAGE)
    brussel = ZoneInfo("Europe/Brussels")
    lines = []
    for r in rows:
        if r.cost_amount is not None and r.cost_currency:
            cost = f"{_number(r.cost_amount, 4)} {r.cost_currency}"
        elif r.cost_credits is not None:
            cost = _("%(n)s credits") % {"n": _number(r.cost_credits, 2)}
        else:
            cost = "—"
        lines.append(AiCallLine(
            moment=r.created_at.astimezone(brussel).strftime("%d-%m-%Y %H:%M"),
            what=_what(r.surface, r.capability),
            actor=r.actor or "—",
            model=r.model or "—",
            provider=_provider(r.provider),
            status_label=code_label(AI_STATUS.name, r.status),
            status_tone=tone(AI_STATUS.name, r.status),
            duration=(f"{_number(Decimal(r.duration_ms) / 1000, 1)} s"
                      if r.duration_ms is not None else "—"),
            cost=cost,
        ))
    return lines, has_next


@router.get(PATH, response_class=HTMLResponse)
def ai_costs(request: Request, db: Session = Depends(get_db),
             _email: str = Depends(require_admin_ui), maand: str = "",
             page: int = 1):
    """The month's totals, and below them every call, newest first."""
    from babel.dates import format_date

    tenant = current_tenant_id.get() or DEFAULT_TENANT_ID
    page = max(1, page)
    calls, has_next = _call_lines(db, tenant, page)
    if is_fragment_request(request):
        return templates.TemplateResponse(request, "_ai_kosten_lijst.html", AiCallListView(
            calls=calls, page=page, has_prev=page > 1, has_next=has_next).as_context())

    eerste = _month(maand)
    start, end = month_period(eerste)
    totals = [
        AiCostLine(
            what=code_label(AI_CAPABILITY.name, line.capability),
            provider=_provider(line.provider),
            calls=line.calls,
            tokens=_number(Decimal(line.tokens_prompt + line.tokens_completion), 0),
            credits=(_number(line.cost_credits, 2) if line.cost_credits is not None else "—"),
            amount=_money(line.cost_amounts),
        )
        for line in cost_per_period(db, tenant_id=tenant, start=start, end=end)
    ]
    view = AiCostView(
        calls=calls, page=page, has_prev=page > 1, has_next=has_next,
        month_label=format_date(eerste, "LLLL yyyy", locale=current_locale.get()),
        prev_month=_shift(eerste, -1), next_month=_shift(eerste, 1),
        totals=totals, nav_items=admin_nav("/admin/info"))
    return templates.TemplateResponse(request, "admin_ai_kosten.html", view.as_context())
