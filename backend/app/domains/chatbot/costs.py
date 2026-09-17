"""Reading the AI log: what did the AI cost a department (#978).

One place that answers the cost question, so the screen on /admin/info and
CR-10's budget per department count the same rows the same way.

A period is half-open, `[start, end)`, in aware datetimes. `month_period`
gives the calendar month in Belgian time: a call at 00:30 on the first of the
month belongs to that month, although it is still the previous day in UTC.

The list never carries `payload`. That is what left for the model, and it is
shown per answer in the "Wat zag Mistral?" fold-out; a screen that lists every
payload of a department is a different screen with a different access question.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import AiCallLog

BELGIUM = ZoneInfo("Europe/Brussels")


def month_period(day: date) -> tuple[datetime, datetime]:
    """The calendar month around `day`, as `[first, first of next)` in Belgian time."""
    start = datetime(day.year, day.month, 1, tzinfo=BELGIUM)
    volgende = (datetime(day.year + 1, 1, 1, tzinfo=BELGIUM) if day.month == 12
                else datetime(day.year, day.month + 1, 1, tzinfo=BELGIUM))
    return start, volgende


@dataclass(frozen=True)
class CostLine:
    """The calls of one provider and capability in a period."""

    provider: str
    capability: str
    calls: int
    tokens_prompt: int
    tokens_completion: int
    cost_credits: Optional[Decimal]
    #: Money per currency, e.g. {"USD": Decimal("0.045")}. Never summed across
    #: currencies: that would need an exchange rate nobody has agreed on.
    cost_amounts: dict[str, Decimal]


def cost_per_period(db: Session, *, tenant_id: int, start: datetime,
                    end: datetime) -> list[CostLine]:
    """The cost of one department in `[start, end)`, per provider and capability."""
    rows = (
        db.query(
            AiCallLog.provider, AiCallLog.capability, AiCallLog.cost_currency,
            func.count(AiCallLog.id),
            func.coalesce(func.sum(AiCallLog.tokens_prompt), 0),
            func.coalesce(func.sum(AiCallLog.tokens_completion), 0),
            func.sum(AiCallLog.cost_credits),
            func.sum(AiCallLog.cost_amount),
        )
        .filter(AiCallLog.tenant_id == tenant_id,
                AiCallLog.created_at >= start, AiCallLog.created_at < end)
        .group_by(AiCallLog.provider, AiCallLog.capability, AiCallLog.cost_currency)
        .all()
    )
    lines: dict[tuple[str, str], dict] = {}
    for provider, capability, currency, calls, prompt, completion, credits, amount in rows:
        line = lines.setdefault((provider, capability), {
            "calls": 0, "prompt": 0, "completion": 0, "credits": None, "amounts": {}})
        line["calls"] += calls
        line["prompt"] += int(prompt)
        line["completion"] += int(completion)
        if credits is not None:
            line["credits"] = (line["credits"] or Decimal(0)) + credits
        if currency and amount is not None:
            line["amounts"][currency] = line["amounts"].get(currency, Decimal(0)) + amount
    return [
        CostLine(provider=provider, capability=capability, calls=v["calls"],
                 tokens_prompt=v["prompt"], tokens_completion=v["completion"],
                 cost_credits=v["credits"], cost_amounts=v["amounts"])
        for (provider, capability), v in sorted(lines.items())
    ]


@dataclass(frozen=True)
class CallRow:
    """One call as the list shows it — everything but the payload."""

    id: int
    created_at: datetime
    surface: str
    capability: str
    actor: str
    model: str
    provider: str
    endpoint: str
    status: str
    duration_ms: Optional[int]
    tokens_prompt: Optional[int]
    tokens_completion: Optional[int]
    cost_credits: Optional[Decimal]
    cost_amount: Optional[Decimal]
    cost_currency: Optional[str]


def list_calls(db: Session, *, tenant_id: int, page: int = 1,
               per_page: int = 50) -> tuple[list[CallRow], bool]:
    """Newest first. Returns the rows and whether there is a next page.

    One row extra instead of a COUNT, like the e-mail log: the list grows with
    every question and a count per page view buys a number nobody reads.
    """
    page = max(1, page)
    kolommen = [getattr(AiCallLog, f) for f in CallRow.__dataclass_fields__]
    rows = (
        db.query(*kolommen)
        .filter(AiCallLog.tenant_id == tenant_id)
        .order_by(AiCallLog.created_at.desc(), AiCallLog.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page + 1)
        .all()
    )
    return [CallRow(*r) for r in rows[:per_page]], len(rows) > per_page
