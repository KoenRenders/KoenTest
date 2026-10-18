"""The AI cost screen (#978): what the AI cost this department, and each call.

Reached from /admin/info and behind the same right (`settings.view`) —
Koen, 16 September 2026. The list shows who asked (`actor`), also his
decision; it never shows what was sent (see `chatbot/costs.py`).

The totals and the list come from `cost_per_period` and `list_calls`: the
screen is the first user of the reader CR-10's budget will count with, which
is the test of whether that reader is right.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import Right, require_right
from app.domains.chatbot.api import (
    AI_CAPABILITY,
    AI_PROVIDER,
    AI_STATUS,
    AI_SURFACE,
    AiCapability,
    AiProvider,
    AiStatus,
    AiSurface,
    cost_per_period,
    list_calls,
    month_period,
)
from app.domains.chatbot.viewmodels import AiCallLine, AiCostLine, AiCostView
from app.i18n import _, current_locale, short_datetime
from app.kernel.clock import belgian_today
from app.kernel.codes import code_label, code_labels, register_tones, tone
from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id
from app.ui import (
    PER_PAGE_OPTIONS,
    admin_nav,
    filterparams,
    per_page_from,
    templates,
)

router = APIRouter(include_in_schema=False)

PATH = "/admin/info/ai-kosten"

# CR-12 phase 4: the words of surface, capability, status and provider come
# from their label tables; the dictionaries that stood here became their seed.
# The badge tone stays here, next to the screen that draws it (§B4.5): a
# refusal — ours or the provider's — is a warning, not a failure.
register_tones(
    AI_STATUS.name,
    {
        AiStatus.OK: "green",
        AiStatus.BLOCKED: "yellow",
        AiStatus.ERROR: "red",
        AiStatus.MODERATED: "yellow",
    },
)


def _what(surface: AiSurface, capability: AiCapability) -> str:
    return f"{code_label(AI_SURFACE.name, surface)} · {code_label(AI_CAPABILITY.name, capability)}"


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


def _state(request: Request) -> dict[str, Any]:
    """The list's state from the URL: the month, the filters, the sort, the page."""
    stand = filterparams(request)
    try:
        page = max(1, int(stand.get("page") or 1))
    except ValueError:
        page = 1
    capability = (stand.get("capability") or "").strip()
    provider = (stand.get("provider") or "").strip()
    return {
        "month": _month(stand.get("maand") or ""),
        "capability": capability if capability in {m.value for m in AiCapability} else "",
        "provider": provider if provider in {m.value for m in AiProvider} else "",
        "sort": "datum" if (stand.get("sort") or "") == "datum" else "",
        "page": page,
        "per_page": per_page_from(stand.get("per_page")),
    }


def _columns(state: dict[str, Any], filters: dict[str, str]) -> list[dict[str, Any]]:
    """The list's columns on the kit's table (#1925). Eight values in seven places:
    the model and its provider share one optional column that stands on a wide
    screen only, so the duration keeps the other (Koen, 16 October 2026, "a").
    The date is the one sortable column (§5.1): newest first, or oldest first."""
    query = urlencode(
        {
            **filters,
            "sort": "" if state["sort"] == "datum" else "datum",
            "per_page": state["per_page"],
        }
    )
    return [
        {"key": "wat", "label": _("Onderdeel"), "cell": "name"},
        {"key": "wie", "label": _("Wie"), "cell": "context"},
        {"key": "status", "label": _("Status"), "cell": "status"},
        {"key": "model", "label": _("Model"), "cell": "extra", "priority": 1},
        {"key": "duur", "label": _("Duur"), "cell": "extra", "priority": 2},
        {"key": "kost", "label": _("Kost"), "cell": "amount", "num": True},
        {
            "key": "datum",
            "label": _("Datum"),
            "cell": "moment",
            "sort_url": f"{PATH}?{query}",
            "sort_page_url": f"{PATH}?{query}",
            "sorted": ("asc" if state["sort"] == "datum" else "desc"),
        },
    ]


def _call_lines(db: Session, tenant: int, state: dict[str, Any]) -> tuple[list[AiCallLine], int]:
    start, end = month_period(state["month"])
    rows, total = list_calls(
        db,
        tenant_id=tenant,
        page=state["page"],
        per_page=state["per_page"],
        start=start,
        end=end,
        capability=AiCapability(state["capability"]) if state["capability"] else None,
        provider=AiProvider(state["provider"]) if state["provider"] else None,
        oldest_first=state["sort"] == "datum",
    )
    lines = []
    for r in rows:
        if r.cost_amount is not None and r.cost_currency:
            cost = f"{_number(r.cost_amount, 4)} {r.cost_currency}"
        elif r.cost_credits is not None:
            cost = _("%(n)s credits") % {"n": _number(r.cost_credits, 2)}
        else:
            cost = "—"
        lines.append(
            AiCallLine(
                moment=short_datetime(r.created_at),
                what=_what(r.surface, r.capability),
                actor=r.actor or "—",
                engine=" · ".join(x for x in (r.model, _provider(r.provider)) if x and x != "—")
                or "—",
                status_label=code_label(AI_STATUS.name, r.status),
                status_tone=tone(AI_STATUS.name, r.status),
                duration=(
                    f"{_number(Decimal(r.duration_ms) / 1000, 1)} s"
                    if r.duration_ms is not None
                    else "—"
                ),
                cost=cost,
            )
        )
    return lines, total


def _view(request: Request, db: Session, **extra: Any) -> AiCostView:
    from babel.dates import format_date

    tenant = current_tenant_id.get() or DEFAULT_TENANT_ID
    state = _state(request)
    eerste = state["month"]
    calls, total = _call_lines(db, tenant, state)
    filters = {k: state[k] for k in ("capability", "provider") if state[k]}
    month = f"{eerste.year:04d}-{eerste.month:02d}"
    carried = {"maand": month, **filters, "sort": state["sort"], "per_page": state["per_page"]}
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

    def month_url(shift: int) -> str:
        return f"{PATH}?{urlencode({**filters, 'maand': _shift(eerste, shift)})}"

    return AiCostView(
        calls=calls,
        columns=_columns(state, {"maand": month, **filters}),
        page=state["page"],
        per_page=state["per_page"],
        total=total,
        month=month,
        month_label=format_date(eerste, "LLLL yyyy", locale=current_locale.get()),
        prev_month_url=month_url(-1),
        next_month_url=month_url(1),
        totals=totals,
        totals_columns=[
            {"key": "wat", "label": _("Onderdeel"), "cell": "name"},
            {"key": "provider", "label": _("Provider"), "cell": "context"},
            {"key": "calls", "label": _("Oproepen"), "cell": "extra", "num": True},
            {"key": "tokens", "label": _("Tokens"), "cell": "extra", "priority": 1, "num": True},
            {"key": "credits", "label": _("Credits"), "cell": "extra", "priority": 2, "num": True},
            {"key": "kost", "label": _("Kost"), "cell": "amount", "num": True},
        ],
        capability=state["capability"],
        provider=state["provider"],
        sort=state["sort"],
        sort_options=[("", _("Recentste eerst")), ("datum", _("Oudste eerst"))],
        capability_options=code_labels(AI_CAPABILITY.name, db=db),
        provider_options=code_labels(AI_PROVIDER.name, db=db),
        page_sizes=list(PER_PAGE_OPTIONS),
        pager_url=f"{PATH}?{urlencode(carried)}",
        empty_reason=_("Geen AI-oproepen voor deze filter in deze maand.")
        if filters
        else _("Geen AI-oproepen in deze maand."),
        **extra,
    )


@router.get(PATH, response_class=HTMLResponse)
def ai_costs(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SETTINGS_VIEW)),
):
    """The month's totals, and below them the month's calls on the kit's list."""
    view = _view(request, db, nav_items=admin_nav("/admin/info", request))
    return templates.TemplateResponse(request, "admin_ai_kosten.html", view.as_context())


@router.get(PATH + "/lijst", response_class=HTMLResponse)
def ai_calls_list(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.SETTINGS_VIEW)),
):
    """The list alone: the toolbar swaps this fragment, so a filter is not replaced
    under the fingers."""
    return templates.TemplateResponse(
        request, "_ai_kosten_lijst.html", _view(request, db, oob=True).as_context()
    )
