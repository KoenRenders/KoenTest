"""Registering closes: a deadline, and a cancelled activity (#974).

Two things close an activity for NEW registrations and both are decided in one
place, `activities.service.registration_state`. The route asks it, the public card
asks it, and the modal asks it. Until #974 the route and the card each had their
own idea of "open", which is exactly how a deadline would have ended up in one of
them and not the other.

**The clock is pinned in these tests, and in two places.** The deadline is a DAY in
Belgian time; the container may run on UTC. So each test pins one instant and
makes both views of it consistent: the Belgian clock (`app.kernel.clock`) and the
naive `date.today()` a UTC container would report. That is what makes the
summer-midnight test able to go red: put `date.today()` back in the service and it
reads the UTC date, which is still the deadline day, and lets the registration in.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domains.activities.api import (Activity, ActivityDate, ActivityProduct,
                                        ActivitySubRegistration, Registration)

DEADLINE = date(2027, 7, 15)          # zomer: Brussel = UTC+2


def _pin(monkeypatch, instant_utc: datetime) -> None:
    """Freeze "now" at one instant, seen consistently by both clocks."""
    import app.kernel.clock as clock
    from app.domains.activities import service

    class _Klok(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant_utc if tz is None else instant_utc.astimezone(tz)

    class _Datum(date):
        @classmethod
        def today(cls):
            # What a container on UTC would say: the UTC date of the instant.
            return instant_utc.date()

    monkeypatch.setattr(clock, "datetime", _Klok)
    monkeypatch.setattr(service, "date", _Datum)


def _activity(db, *, closes_on=DEADLINE, cancelled=False, external_url=None):
    """An activity well after the deadline, with one free product.

    Its date is fixed relative to DEADLINE and not to the real today, so the pinned
    clock is the only thing that decides whether it is open.
    """
    a = Activity(name="Bowling", registration_closes_on=closes_on,
                 is_cancelled=cancelled)
    db.add(a)
    db.flush()
    db.add(ActivityDate(activity_id=a.id, start_date=DEADLINE + timedelta(days=30)))
    comp = ActivitySubRegistration(
        activity_id=a.id, name="Deelname", registration_type_code="INDIVIDUAL",
        price=Decimal("0"), is_free=True, external_register_url=external_url)
    db.add(comp)
    db.flush()
    product = ActivityProduct(component_id=comp.id, name="Plaats",
                              price=Decimal("0"), is_free=True)
    db.add(product)
    db.flush()
    return a, comp, product


def _inschrijven(client, a, comp, product, naam="Fee"):
    return client.post(f"/activiteiten/{a.id}/inschrijven/{comp.id}",
                       data={"contact_name": naam,
                             "contact_email": f"{naam.lower()}@example.org",
                             "phone": "0470000000", f"product_{product.id}": "1"})


def _aantal(db, a) -> int:
    return db.query(Registration).filter(Registration.activity_id == a.id).count()


# ── De deadline, rond middernacht ────────────────────────────────────────────

def test_half_past_eleven_on_the_deadline_day_is_still_accepted(client, db_session,
                                                                 monkeypatch):
    """Inclusive: the deadline day counts, until midnight in Brussels."""
    a, comp, product = _activity(db_session)
    _pin(monkeypatch, datetime(2027, 7, 15, 21, 30, tzinfo=timezone.utc))  # 23:30 BE

    resp = _inschrijven(client, a, comp, product)

    assert "Bedankt, Fee" in resp.text, resp.text[:300]
    assert _aantal(db_session, a) == 1


def test_half_past_midnight_the_day_after_is_refused_although_utc_still_says_the_deadline_day(
        client, db_session, monkeypatch):
    """The test that matters (#974): Belgian date, not the container's.

    At 00:30 in Brussels on the 16th it is 22:30 UTC on the 15th. A service that
    asks `date.today()` on a UTC host still sees the deadline day and lets the
    registration in — two hours late, every summer night.

    Broken to see it red: `today or belgian_today()` replaced by
    `today or date.today()` in `registration_state`. The registration is then
    accepted and both assertions fall over.
    """
    a, comp, product = _activity(db_session)
    _pin(monkeypatch, datetime(2027, 7, 15, 22, 30, tzinfo=timezone.utc))  # 00:30 BE

    resp = _inschrijven(client, a, comp, product)

    assert "afgesloten sinds" in resp.text, resp.text[:300]
    assert _aantal(db_session, a) == 0


def test_without_a_deadline_nothing_changes(client, db_session, monkeypatch):
    a, comp, product = _activity(db_session, closes_on=None)
    _pin(monkeypatch, datetime(2027, 8, 1, 10, 0, tzinfo=timezone.utc))

    resp = _inschrijven(client, a, comp, product)

    assert "Bedankt, Fee" in resp.text
    assert _aantal(db_session, a) == 1


def test_an_activity_whose_dates_have_passed_is_still_refused(client, db_session,
                                                              monkeypatch):
    """The old rule, now asked of the service instead of written in the route."""
    a, comp, product = _activity(db_session, closes_on=None)
    _pin(monkeypatch, datetime(2027, 9, 1, 10, 0, tzinfo=timezone.utc))  # na de datum

    resp = _inschrijven(client, a, comp, product)

    assert "no longer open" in resp.text.lower() or "niet meer" in resp.text.lower()
    assert _aantal(db_session, a) == 0


# ── Geannuleerd ──────────────────────────────────────────────────────────────

def test_a_cancelled_activity_is_refused_on_the_public_form(client, db_session,
                                                            monkeypatch):
    """Future date, no deadline — the cancellation is the ONLY reason to refuse.

    Until #974 only the card knew: it hid the button, and a form posted from a tab
    that was still open went straight through.

    Broken to see it red: the `if activity.is_cancelled` branch removed from
    `registration_state`. The registration is then accepted.
    """
    a, comp, product = _activity(db_session, closes_on=None, cancelled=True)
    _pin(monkeypatch, datetime(2027, 7, 1, 10, 0, tzinfo=timezone.utc))

    resp = _inschrijven(client, a, comp, product)

    assert "geannuleerd" in resp.text, resp.text[:300]
    assert _aantal(db_session, a) == 0


def test_a_cancelled_activity_is_refused_on_the_json_api(client, db_session,
                                                         monkeypatch):
    """The same refusal on the other door — both reach `register_for_activity`."""
    a, comp, product = _activity(db_session, closes_on=None, cancelled=True)
    _pin(monkeypatch, datetime(2027, 7, 1, 10, 0, tzinfo=timezone.utc))

    resp = client.post(f"/api/v1/activities/{a.id}/register", json={
        "contact_name": "Api", "contact_email": "api@example.org",
        "phone": "0470000000", "component_id": comp.id,
        "items": [{"product_id": product.id, "quantity": 1}]})

    assert resp.status_code == 400
    assert "geannuleerd" in resp.json()["detail"]
    assert _aantal(db_session, a) == 0


# ── Wat een bezoeker ziet ────────────────────────────────────────────────────

def test_after_the_deadline_the_card_shows_closed_and_offers_no_way_in(
        client, db_session, monkeypatch):
    """No button, and no external link either — that one is easy to forget.

    It sits in another branch of the card than the regular button. The form behind
    it cannot be closed from here, but the card no longer has to point at it.

    Broken to see it red: the `registration_state == "closed"` branch removed from
    `_activiteiten_cards.html` — the external link is back.
    """
    a, _comp, _product = _activity(db_session,
                                   external_url="https://extern.example/inschrijven")
    _pin(monkeypatch, datetime(2027, 7, 16, 10, 0, tzinfo=timezone.utc))

    html = client.get("/activiteiten").text
    start = html.index("Bowling")
    kaart = html[start:start + 6000]

    assert "Inschrijvingen afgesloten" in kaart
    assert "https://extern.example/inschrijven" not in kaart
    assert f"/activiteiten/{a.id}/inschrijven/" not in kaart


def test_before_the_deadline_the_card_says_until_when(client, db_session,
                                                      monkeypatch):
    _activity(db_session)
    _pin(monkeypatch, datetime(2027, 7, 1, 10, 0, tzinfo=timezone.utc))

    html = client.get("/activiteiten").text
    start = html.index("Bowling")
    kaart = html[start:start + 6000]

    assert "Inschrijven kan tot" in kaart
    assert "Inschrijvingen afgesloten" not in kaart


def test_a_modal_opened_after_the_deadline_says_why(client, db_session, monkeypatch):
    """An old link or a tab left open: the reason shows before anyone types."""
    a, comp, _product = _activity(db_session)
    _pin(monkeypatch, datetime(2027, 7, 16, 10, 0, tzinfo=timezone.utc))

    html = client.get(f"/activiteiten/{a.id}/inschrijven/{comp.id}").text

    assert "afgesloten sinds" in html


# ── Beheer mag nog corrigeren ────────────────────────────────────────────────

def test_the_board_can_still_correct_an_existing_registration(client, db_session,
                                                              monkeypatch,
                                                              admin_headers):
    """A correction is not a new registration (#974).

    Registered before the deadline, corrected after it. And the same for a
    cancelled activity: that is precisely when registrations need a refund or an
    update. The service refuses where a registration is CREATED, nowhere else.

    Broken to see it red: `registration_refusal` called at the top of
    `update_order_line` in the service — the correction is then refused.
    """
    a, comp, product = _activity(db_session)
    _pin(monkeypatch, datetime(2027, 7, 1, 10, 0, tzinfo=timezone.utc))
    _inschrijven(client, a, comp, product)
    reg = (db_session.query(Registration)
           .filter(Registration.activity_id == a.id).one())
    item = reg.items[0]

    _pin(monkeypatch, datetime(2027, 7, 20, 10, 0, tzinfo=timezone.utc))
    a.is_cancelled = True
    db_session.flush()

    resp = client.patch(
        f"/api/v1/activities/{a.id}/registrations/{reg.id}/items/{item.id}",
        json={"quantity": 2}, headers=admin_headers)

    assert resp.status_code == 200, resp.text[:300]
    db_session.refresh(item)
    assert item.quantity == 2


# ── Beheer: het veld ─────────────────────────────────────────────────────────

def test_the_deadline_can_be_set_and_cleared_in_the_admin(client, db_session):
    """Clearing is a valid choice, so an empty field must remove the deadline."""
    from tests.conftest import SEEDED_ADMIN_EMAIL
    from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                      make_session_value)

    a, _comp, _product = _activity(db_session, closes_on=None)
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    kop = {"X-CSRF-Token": csrf_token_for(value)}

    client.post(f"/admin/activiteiten/{a.id}",
                data={"name": "Bowling", "registration_closes_on": "2027-07-15"},
                headers=kop)
    db_session.refresh(a)
    assert a.registration_closes_on == DEADLINE

    html = client.get(f"/admin/activiteiten/{a.id}").text
    assert 'value="2027-07-15"' in html

    client.post(f"/admin/activiteiten/{a.id}",
                data={"name": "Bowling", "registration_closes_on": ""},
                headers=kop)
    db_session.refresh(a)
    assert a.registration_closes_on is None
