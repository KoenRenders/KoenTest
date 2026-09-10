"""#792 — the complete first date row at creation time, and the coherence rule.

In #623 the create screen got a single date field: *"name and first date suffice; dates,
components and products you add afterwards"*. Defensible, but Koen noticed in practice
that the first row is almost always complete straight away (9 September 2026), so the
detour through the editor had become the rule instead of the exception. **This
deliberately revises that choice** — do not read it as a regression and do not narrow
the form again.

Nothing was missing to make it possible: `ActivityDate` has the four fields,
`ActivityDateCreate` accepts them, and the editor already filled them in. The create
path threw them away.

**The coherence rule belongs with it, and it sits on the object.** Nothing checked that
an end date falls after the start date — through the editor you could save a row running
from 20 September to 18 September. That hole already existed; this issue puts those
fields on the create path, where EVERY activity passes, so it turns from an edge case
into a main road. Per the placement rule of CR-04 this rule looks at several fields of
the same object, so it belongs on the object: `ActivityDate.validate_coherence`, with
mapper events so that EVERY entrance inherits it.

**The second test below is the proof of that placement**, which is why all entrances are
in it. A check that only sits in the new form leaves the editor with the hole — and then
there are two truths about the same row.

`assert status >= 400` is deliberately NOT used: that also succeeds on a CSRF error or a
missing role, and that is how #680 stayed green while the money brake underneath it had
disappeared. Every refusal is checked against its message.

Broken on purpose to check that these tests can go red: threw the three extra fields
away again in `activiteit_aanmaken` → the first test falls over; removed the mapper event
→ all three entrances of the second test fall over (and THAT is the proof that they do
not each carry their own check).
"""
import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "ADMIN" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _latest_activity(db):
    from app.domains.activities.api import Activity

    return db.query(Activity).order_by(Activity.id.desc()).first()


def test_the_create_screen_shows_all_four_fields(client, db_session):
    _login(client, db_session)

    html = client.get("/admin/activiteiten/nieuw").text

    for field in ('id="start_date"', 'id="end_date"', 'id="start_time"', 'id="end_time"'):
        assert field in html, f"{field} is missing; the first row cannot be filled in fully"


def test_creating_keeps_the_complete_first_row(client, db_session):
    """Red on the code from before this issue: the three extra values were thrown away."""
    from datetime import date, time

    headers = _login(client, db_session)

    resp = client.post("/admin/activiteiten", headers=headers, data={
        "name": "Test activity", "start_date": "2026-09-20",
        "end_date": "2026-09-21", "start_time": "19:30", "end_time": "23:00"})

    assert resp.status_code == 204, resp.text
    row = _latest_activity(db_session).dates[0]
    assert row.start_date == date(2026, 9, 20)
    assert row.end_date == date(2026, 9, 21), "the end date was thrown away"
    assert row.start_time == time(19, 30), "the start time was thrown away"
    assert row.end_time == time(23, 0), "the end time was thrown away"


def test_the_times_may_stay_empty(client, db_session):
    """Only the start date is required, exactly as in the editor."""
    headers = _login(client, db_session)

    resp = client.post("/admin/activiteiten", headers=headers, data={
        "name": "Start date only", "start_date": "2026-09-20",
        "end_date": "", "start_time": "", "end_time": ""})

    assert resp.status_code == 204, resp.text
    row = _latest_activity(db_session).dates[0]
    assert row.end_date is None and row.start_time is None and row.end_time is None


def _create_activity(client, db, headers):
    client.post("/admin/activiteiten", headers=headers,
                data={"name": "To be edited", "start_date": "2026-09-20"})
    return _latest_activity(db)


# The three screen entrances, each as its own test: a rejected write rolls the
# transaction back, and in this suite that transaction is a SAVEPOINT around the whole
# test — so everything created before it disappears along with it. In production every
# request has its own session; this is a quirk of the setup, not behaviour of the
# application.
REVERSED = {"start_date": "2026-09-20", "end_date": "2026-09-18"}


def _post_create(client, db, headers):
    return client.post("/admin/activiteiten", headers=headers,
                       data={"name": "Reversed", **REVERSED})


def _post_add_date(client, db, headers):
    activity = _create_activity(client, db, headers)
    return client.post(f"/admin/activiteiten/{activity.id}/datums",
                       headers=headers, data=REVERSED)


def _post_edit_date(client, db, headers):
    activity = _create_activity(client, db, headers)
    path = f"/admin/activiteiten/{activity.id}/datums/{activity.dates[0].id}"
    return client.post(path, headers=headers, data=REVERSED)


@pytest.mark.parametrize("entrance", [_post_create, _post_add_date, _post_edit_date],
                         ids=["create", "add date", "edit date"])
def test_an_end_date_before_the_start_date_is_refused_everywhere(client, db_session, entrance):
    """The core: the rule sits on the object, so every entrance inherits it.

    Were it in the create form, the first would pass and the other two would fail —
    exactly the "two truths about the same row" this must prevent.
    """
    headers = _login(client, db_session)

    resp = entrance(client, db_session, headers)

    assert resp.status_code == 422, f"{resp.status_code} — {resp.text[:200]}"
    assert "einddatum ligt vóór de begindatum" in resp.text, (
        f"refused for a reason other than the coherence rule: {resp.text[:200]}")


def test_an_end_time_before_the_start_time_on_the_same_day_is_refused(client, db_session):
    headers = _login(client, db_session)

    resp = client.post("/admin/activiteiten", headers=headers, data={
        "name": "Backwards", "start_date": "2026-09-20",
        "start_time": "22:00", "end_time": "19:00"})

    assert resp.status_code == 422, resp.text
    assert "einduur ligt niet na het beginuur" in resp.text


def test_a_night_across_two_days_is_allowed(client, db_session):
    """The counterproof that makes the previous test usable: without it, "refuse anything
    with an earlier end time" would be green too, and that is wrong — a party from 20:00
    to 02:00 simply lasts a night."""
    from datetime import time

    headers = _login(client, db_session)

    resp = client.post("/admin/activiteiten", headers=headers, data={
        "name": "Party", "start_date": "2026-09-20", "end_date": "2026-09-21",
        "start_time": "20:00", "end_time": "02:00"})

    assert resp.status_code == 204, resp.text
    assert _latest_activity(db_session).dates[0].end_time == time(2, 0)


def test_the_json_api_inherits_the_same_rule(client, admin_headers):
    """The fourth entrance. A rule that only knows the screens is not a rule on the
    object — and this route is exactly how #720/#727/#733 came about."""
    resp = client.post("/api/v1/activities", headers=admin_headers, json={
        "name": "Through the API", "dates": [
            {"start_date": "2026-09-20", "end_date": "2026-09-18"}]})

    assert resp.status_code == 422, resp.text
    assert "einddatum ligt vóór de begindatum" in resp.text
