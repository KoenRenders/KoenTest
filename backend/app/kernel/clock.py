"""What day it is for a tenant (#974, #2156).

`date.today()` answers in the container's time zone, and a container is free to run
on UTC. For most of the codebase that is harmless. For a deadline it is not: a
registration that "closes on 1 October" would, on a UTC host in summer, stay open
until 02:00 Brussels time on the 2nd — and a board member who promised the caterer
a count at midnight would get two more hours of registrations.

So a rule about a DAY that a person typed is evaluated in the time zone that person
means. Moments are stored in UTC; **the day is the tenant's** (#2156, Koen, 19 October
2026: "een tijdzone per tenant"): `mdm.tenants.time_zone`, an IANA name, `Europe/Brussels`
for every tenant now. The zone is the one of the CURRENT tenant (`current_tenant_id`, set
by the request and by a job's loop over tenants; the default tenant outside both), read
once for every tenant and kept, like the tenant codes (`forget_time_zones()` clears it
with them). SQL asks the same setting through `mdm.tenant_today()` and
`mdm.tenant_day()`: the day is decided in two languages from one fact.

The names `belgian_*` stay (a rename touches every caller for no behaviour); what they
answer is the tenant's day, Brussels for every tenant that exists today.

**`now` is a parameter** so a test can pin the instant. A test that can only go red
at 00:30 in summer is not a test.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError

from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id

#: Brussels, for a test that builds an instant and for a place that means Brussels
#: whatever the tenant (the platform's own cost month, `chatbot/costs.py`). What the
#: tenant's day is comes from `time_zone()`, never from this.
BELGIUM = ZoneInfo("Europe/Brussels")

#: tenant id → IANA name, for every tenant, from one query; None until first asked.
_zones: dict[int, str] | None = None
_warned: set[int] = set()
log = logging.getLogger(__name__)


def forget_time_zones() -> None:
    """Clear the zones read so far (a tenant was changed, `invalidate_tenant_codes`)."""
    global _zones
    _zones = None


def _load_zones() -> dict[int, str]:
    """Every tenant's zone, in one query, over a connection of its own that is closed at
    once (`NullPool`): the clock is asked at import time here and there — a test module's
    constant, a limiter — before a test worker has bound the application to its own
    database, and a pooled connection left behind then points at the wrong one."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    from app.database import engine

    one_off = create_engine(engine.url, poolclass=NullPool)
    try:
        with one_off.connect() as connection:
            return {
                tenant_id: name
                for tenant_id, name in connection.execute(
                    text("SELECT id, time_zone FROM mdm.tenants")
                )
            }
    finally:
        one_off.dispose()


def time_zone(tenant_id: int | None = None) -> ZoneInfo:
    """The time zone of a tenant, by default the current one (#2156).

    Two nets, both for a table that cannot answer, and neither silent:

    - the table cannot be read at all (no database yet at an import, a database not
      migrated to this release): the answer is `BELGIUM`, the zone every tenant has
      today, and nothing is cached, so the next call asks again. Request resolution
      must never break on an infrastructure hiccup (the rule of
      `tenant_lookup.tenant_codes`);
    - the tenant is not in the table the clock can see (a tenant made in a transaction
      that is not committed yet, as a test does): `BELGIUM`, with a warning in the log
      once per tenant. In production a tenant is committed before it is served.
    """
    global _zones
    tenant = tenant_id or current_tenant_id.get() or DEFAULT_TENANT_ID
    if _zones is None or tenant not in _zones:
        try:
            _zones = _load_zones()
        except SQLAlchemyError:
            return BELGIUM
    name = _zones.get(tenant)
    if name is None:
        if tenant not in _warned:
            _warned.add(tenant)
            log.warning("tenant %s is not in mdm.tenants as the clock sees it; Brussels", tenant)
        return BELGIUM
    return ZoneInfo(name)


def belgian_now(now: datetime | None = None) -> datetime:
    """This moment in the tenant's time zone, timezone-aware (#1976): what a screen that says
    "as of" shows, and whose `.date()` is the tenant's today."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("belgian_now() needs a timezone-aware datetime")
    return moment.astimezone(time_zone())


def belgian_day(moment: datetime) -> date:
    """The tenant's day a moment belongs to (#2065, #2156): the one place that decides
    which day a payment or a registration falls on. A naive moment is refused."""
    if moment.tzinfo is None:
        raise ValueError("belgian_day() needs a timezone-aware datetime")
    return moment.astimezone(time_zone()).date()


def belgian_today(now: datetime | None = None) -> date:
    """Today's date for the current tenant: its day, not the server's.

    `now` must be timezone-aware when given; a naive datetime is refused rather
    than guessed at, because guessing is exactly the bug this module exists for.
    """
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("belgian_today() needs a timezone-aware datetime")
    return moment.astimezone(time_zone()).date()


def belgian_day_start(day: date) -> datetime:
    """The moment the tenant's day begins (#2091), timezone-aware: what a filter "since
    this day" compares a stored moment with. Midnight in Brussels is 22:00 or 23:00 UTC
    the evening before, so a change made at 00:30 Brussels belongs to the new day."""
    return datetime.combine(day, time.min, tzinfo=time_zone())
