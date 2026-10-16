"""What day it is in Belgium (#974).

`date.today()` answers in the container's time zone, and a container is free to run
on UTC. For most of the codebase that is harmless. For a deadline it is not: a
registration that "closes on 1 October" would, on a UTC host in summer, stay open
until 02:00 Brussels time on the 2nd — and a board member who promised the caterer
a count at midnight would get two more hours of registrations.

So a rule about a DAY that a person typed is evaluated in the time zone that person
means. This platform serves Belgian associations; there is no per-tenant time zone
and no need for one yet — the day it is needed, this is the one function that
changes.

**`now` is a parameter** so a test can pin the instant. A test that can only go red
at 00:30 in summer is not a test.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

BELGIUM = ZoneInfo("Europe/Brussels")


def belgian_now(now: datetime | None = None) -> datetime:
    """This moment in Brussels, timezone-aware (#1976): what a screen that says
    "as of" shows, and whose `.date()` is today in Brussels."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("belgian_now() needs a timezone-aware datetime")
    return moment.astimezone(BELGIUM)


def belgian_day(moment: datetime) -> date:
    """The Brussels day a moment belongs to (#2065): the one place that decides
    which day a payment or a registration falls on. A naive moment is refused."""
    if moment.tzinfo is None:
        raise ValueError("belgian_day() needs a timezone-aware datetime")
    return moment.astimezone(BELGIUM).date()


def belgian_today(now: datetime | None = None) -> date:
    """Today's date in Brussels.

    `now` must be timezone-aware when given; a naive datetime is refused rather
    than guessed at, because guessing is exactly the bug this module exists for.
    """
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("belgian_today() needs a timezone-aware datetime")
    return moment.astimezone(BELGIUM).date()
