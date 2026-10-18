"""The public assistant answers about an activity with what the public page
shows (#2055): only the products a visitor may pick, and a cancelled activity
as cancelled.

Found by the reader of PR #2053 (CR-33 phase 2) and proven with a probe on
master: `get_activity_detail` handed the public assistant an inactive product
— the board's guest list, "a product no visitor may pick" — with its name and
price, and its price could be the activity's `price_from`. The tools read the
public form's own selection now (`publicly_bookable_products`).

A cancelled activity: the public list shows it, with the status
"Geannuleerd"; the tools answered about it as if it took place (the detail)
or left it out (the list). Koen, 16 October 2026, "1a": `is_cancelled` is
public in the register, and both tools carry `cancelled`.

Broken on purpose (16 October 2026): `sub.products` back in the detail →
the detail test red on the guest list; back in `_price_from` → both price
tests red on 1.00; `cancelled` taken out of the detail → the cancelled
detail test red; the list's filter on `is_cancelled` back → the cancelled
list test red.
"""

import json
from datetime import timedelta

from app.domains.activities.api import Activity, ActivityDate
from app.domains.activities.models import ActivityProduct, ActivitySubRegistration
from app.domains.chatbot.tools import execute_tool
from app.kernel.clock import belgian_today


def _activity(db) -> Activity:
    """A published activity with one product a visitor may pick (4.00) and one
    the board keeps for itself (1.00, inactive)."""
    a = Activity(name="Kaartavond 2055", location="De Zaal", description="Kaarten.")
    db.add(a)
    db.flush()
    db.add(ActivityDate(activity_id=a.id, start_date=belgian_today() + timedelta(days=9)))
    component = ActivitySubRegistration(activity_id=a.id, name="Deelname", is_free=True)
    db.add(component)
    db.flush()
    db.add_all(
        [
            ActivityProduct(component_id=component.id, name="Toegang", price=4, is_free=False),
            ActivityProduct(
                component_id=component.id,
                name="Gastenlijst",
                price=1,
                is_free=False,
                is_active=False,
            ),
        ]
    )
    db.flush()
    db.expire_all()
    return a


def test_the_detail_leaves_out_an_inactive_product(db_session):
    a = _activity(db_session)
    out = json.loads(execute_tool("get_activity_detail", {"activity_id": a.id}, db_session))
    names = [p["name"] for c in out["components"] for p in c["products"]]
    assert names == ["Toegang"], f"the assistant was handed {names}"
    assert out["price_from"] == "4.00", "the guest list's price is no price a visitor pays"


def test_the_list_prices_from_what_a_visitor_may_pick(db_session):
    a = _activity(db_session)
    out = json.loads(execute_tool("get_activities", {}, db_session))
    mine = [x for x in out["activities"] if x["id"] == a.id]
    assert mine, "the activity is in the list — is the test looking?"
    assert mine[0]["price_from"] == "4.00"


def test_a_cancelled_activity_is_answered_as_cancelled(db_session):
    a = _activity(db_session)
    a.is_cancelled = True
    db_session.flush()

    detail = json.loads(execute_tool("get_activity_detail", {"activity_id": a.id}, db_session))
    assert detail["cancelled"] is True, "the detail says it is cancelled, as the page does"

    listed = json.loads(execute_tool("get_activities", {}, db_session))
    mine = [x for x in listed["activities"] if x["id"] == a.id]
    assert mine and mine[0]["cancelled"] is True, (
        "the list carries it, marked cancelled, as the public list shows it"
    )


def test_an_activity_that_goes_ahead_is_not_cancelled(db_session):
    a = _activity(db_session)
    detail = json.loads(execute_tool("get_activity_detail", {"activity_id": a.id}, db_session))
    assert detail["cancelled"] is False
