"""#1307 — the member list and the dashboard count the same active households.

Koen, 29 September 2026: the member list showed 110 active households, the
dashboard 109. There were four definitions of "active household", and the
dashboard tile had the odd one: active membership ROWS carrying this year's
number. A household that renews after the turnover date gets next year's
membership, valid from the day it paid — a member today, and missing from the
tile until 1 January. The tile also counted rows, not households.

Now there is one rule, `membership.service.valid_on` (active, and today within the
validity period). The member list's KPI reads it through
`current_membership_counts`; the tile reads the reporting flag
`f_members.is_valid_today`, which repeats it in SQL. These tests hold the two
together on the cases that tell them apart:

- a household that joined today with next year's membership — counted by both;
- a household with two overlapping active memberships — counted once by both;
- and, on the whole seed plus those, the same number both ways.

Proven red against master `8ef1a6e0` (29 September 2026): the first and the third
fail — the tile stayed where it was for households that joined today with next
year's number. The overlap test passes on master too, and says so: there the year
filter hid next year's row, and two rows for one year cannot exist
(`uq_memberships_member_year`). It guards the new count against counting a
household twice, which an EXISTS over its memberships would do if written as a
join.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domains.mdm.api import Member
from app.domains.membership.api import Membership, current_membership_counts
from app.domains.reporting.api import DASHBOARD_TEGELS, dashboard_numbers
from app.domains.reporting.tests.test_reporting_panel_ui import ADMIN_EMAIL
from tests._reporting_seed import TENANT_A, seed

# The tile as the dashboard defines it — derived, so this test reads whatever
# measure the tile shows and not a copy of it.
TILE = [
    (key, measure)
    for _label, key, measure, _href, _money in DASHBOARD_TEGELS
    if key == "dashboard_active_members"
]


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _kpi(db) -> int:
    """The member list's "Actieve gezinnen", with the tenant a request would have."""
    from app.kernel.tenancy import current_tenant_id

    token = current_tenant_id.set(TENANT_A)
    try:
        return current_membership_counts(db)[0]
    finally:
        current_tenant_id.reset(token)


def _tile(db) -> int:
    numbers = dashboard_numbers(db, TILE, tenant_id=TENANT_A, viewer=ADMIN_EMAIL)
    return int(numbers["dashboard_active_members"].value or 0)


def _household(db, *periods: tuple[int, date, date]) -> Member:
    """A household with an active membership per (year, valid_from, valid_to)."""
    member = Member(tenant_id=TENANT_A)
    db.add(member)
    db.flush()
    for year, valid_from, valid_to in periods:
        db.add(
            Membership(
                tenant_id=TENANT_A,
                member_id=member.id,
                year=year,
                is_active=True,
                valid_from=valid_from,
                valid_to=valid_to,
            )
        )
    db.commit()
    return member


def test_a_household_that_joined_after_the_turnover_date_counts_on_both(db_session, situation):
    """Next year's membership, valid from today: a member today."""
    today = date.today()
    kpi, tile = _kpi(db_session), _tile(db_session)

    _household(db_session, (today.year + 1, today, date(today.year + 1, 12, 31)))

    assert _kpi(db_session) == kpi + 1, "the member list misses a household that joined today"
    assert _tile(db_session) == tile + 1, (
        "the dashboard misses a household whose membership carries next year's number"
    )


def test_a_household_with_two_overlapping_memberships_counts_once(db_session, situation):
    today = date.today()
    kpi, tile = _kpi(db_session), _tile(db_session)

    # This year's membership, and next year's already paid — both cover today.
    # (Two rows for one year cannot exist: `uq_memberships_member_year`.)
    _household(
        db_session,
        (today.year, date(today.year, 1, 1), date(today.year, 12, 31)),
        (today.year + 1, today - timedelta(days=1), date(today.year + 1, 12, 31)),
    )

    assert _kpi(db_session) == kpi + 1
    assert _tile(db_session) == tile + 1, "the dashboard counts memberships, not households"


def test_the_member_list_and_the_dashboard_give_the_same_number(db_session, situation):
    today = date.today()
    # Two households that joined today for next year. Two and not one: the seed
    # holds a membership of this year without validity dates, which the old tile
    # counted and the member list does not — one joiner would cancel it out.
    for _ in range(2):
        _household(db_session, (today.year + 1, today, date(today.year + 1, 12, 31)))
    _household(
        db_session,
        (today.year, date(today.year, 1, 1), date(today.year, 12, 31)),
        (today.year + 1, today, date(today.year + 1, 12, 31)),
    )
    # An inactive membership covering today is not a member — on either side.
    inactive = _household(db_session)
    db_session.add(
        Membership(
            tenant_id=TENANT_A,
            member_id=inactive.id,
            year=today.year,
            is_active=False,
            valid_from=date(today.year, 1, 1),
            valid_to=date(today.year, 12, 31),
        )
    )
    db_session.commit()

    kpi, tile = _kpi(db_session), _tile(db_session)
    assert kpi > 0, "nothing counted — the comparison would prove nothing"
    assert tile == kpi, f"member list {kpi}, dashboard {tile}"
