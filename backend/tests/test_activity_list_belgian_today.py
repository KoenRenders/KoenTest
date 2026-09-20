"""The activity list uses the Belgian date, and the label follows the rule (#977).

Leftover from #974. The registration rule counted in Belgian time; the LIST — which
activities are upcoming and which are archived — still used the server's
`date.today()`. On a UTC container that is two hours behind in summer, so around
midnight an activity could already be over for the rule and still upcoming for the
list.

Underneath sat a second duplication: the router worked out the status label
(past / cancelled / open) itself, next to `registration_state`. The label is now a
lookup on that state, and the last test here walks every state so a new reason to
close cannot be missing from the label.

**Both clocks are pinned** — the Belgian one and the naive `date.today()` a UTC
container reports — for the same reason as the 00:30 test of #974: otherwise the
counterproof with `date.today()` depends on the real date of the machine running
the suite.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domains.activities.api import (Activity, ActivityDate,
                                        ActivitySubRegistration)

LAST_DAY = date(2027, 7, 15)            # zomer: Brussel = UTC+2
# 00:30 in Brussels on the 16th = 22:30 UTC on the 15th.
AFTER_MIDNIGHT = datetime(2027, 7, 15, 22, 30, tzinfo=timezone.utc)


def _pin(monkeypatch, instant_utc: datetime) -> None:
    import app.kernel.clock as clock
    from app.domains.activities import router, service, ui

    class _Klok(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant_utc if tz is None else instant_utc.astimezone(tz)

    class _Datum(date):
        @classmethod
        def today(cls):
            return instant_utc.date()      # wat een UTC-container zegt

    monkeypatch.setattr(clock, "datetime", _Klok)
    for module in (router, service, ui):
        monkeypatch.setattr(module, "date", _Datum, raising=False)


def _activity(db, name, *, last_day=LAST_DAY, closes_on=None, cancelled=False):
    a = Activity(name=name, registration_closes_on=closes_on, is_cancelled=cancelled)
    db.add(a)
    db.flush()
    db.add(ActivityDate(activity_id=a.id, start_date=last_day))
    db.add(ActivitySubRegistration(activity_id=a.id, name="Deelname",
                                   registration_type_code="INDIVIDUAL",
                                   price=Decimal("0"), is_free=True))
    db.flush()
    return a


def test_after_midnight_the_activity_is_in_the_archive_although_utc_says_otherwise(
        client, db_session, monkeypatch):
    """The test that matters (#977).

    Broken to see it red: `today = belgian_today()` in `list_activities` put back
    on `date.today()`. The UTC date is still the last day, so the activity stays in
    the upcoming list and both assertions fall over.
    """
    _activity(db_session, "Zomerbowling")
    _pin(monkeypatch, AFTER_MIDNIGHT)

    komend = client.get("/activiteiten").text
    archief = client.get("/activiteiten/archief").text

    assert "Zomerbowling" not in komend
    assert "Zomerbowling" in archief


def test_a_shared_link_after_midnight_goes_to_the_archive(client, db_session,
                                                          monkeypatch):
    """Sinds golf 12 rendert het deeladres de pagina zelf; de Belgische
    middernachtblik (#977) bepaalt nu de terug-link en de scope."""
    a = _activity(db_session, "Zomerbowling")
    _pin(monkeypatch, AFTER_MIDNIGHT)

    resp = client.get(f"/activiteiten/{a.id}")

    assert resp.status_code == 200 and "Zomerbowling" in resp.text
    assert 'href="/activiteiten/archief"' in resp.text


def test_a_passed_deadline_reads_afgesloten_and_not_open(client, db_session,
                                                         monkeypatch):
    """Koen, 16 September 2026: an activity that takes no more registrations is not
    "Open", even though it has not taken place yet.

    Before #977 this card read "Open" in its title next to "Inschrijvingen
    afgesloten" at its component — the contradiction this issue removes.
    """
    _activity(db_session, "Wijndomein", last_day=LAST_DAY + timedelta(days=30),
              closes_on=LAST_DAY)
    _pin(monkeypatch, datetime(2027, 7, 20, 10, 0, tzinfo=timezone.utc))

    html = client.get("/activiteiten").text
    start = html.index("Wijndomein")
    kop = html[start:start + 400]

    assert "Afgesloten" in kop
    assert ">Open<" not in kop.replace(" ", "")


def test_the_admin_does_not_count_a_closed_activity_as_open(db_session, monkeypatch):
    from app.domains.activities.admin_ui import _kpi
    from app.domains.activities.router import list_activities

    _activity(db_session, "Open ding", last_day=LAST_DAY + timedelta(days=30))
    _activity(db_session, "Dicht ding", last_day=LAST_DAY + timedelta(days=30),
              closes_on=LAST_DAY)
    _pin(monkeypatch, datetime(2027, 7, 20, 10, 0, tzinfo=timezone.utc))

    lijst = [a for a in list_activities(scope="all", db=db_session)
             if a.name in ("Open ding", "Dicht ding")]

    assert _kpi(lijst)["kpi_open"] == 1


@pytest.mark.parametrize("instant, closes_on, cancelled, last_day", [
    (datetime(2027, 7, 1, 10, 0, tzinfo=timezone.utc), None, False, LAST_DAY),
    (datetime(2027, 7, 20, 10, 0, tzinfo=timezone.utc), LAST_DAY, False,
     LAST_DAY + timedelta(days=30)),
    (datetime(2027, 7, 1, 10, 0, tzinfo=timezone.utc), None, True, LAST_DAY),
    (AFTER_MIDNIGHT, None, False, LAST_DAY),
], ids=["open", "afgesloten", "geannuleerd", "voorbij-na-middernacht"])
def test_the_label_and_the_registration_rule_never_disagree(
        db_session, monkeypatch, instant, closes_on, cancelled, last_day):
    """Same activity, same moment: the label and the rule give one answer.

    Walked over every state, so a new reason to close that is added to
    `registration_state` without a label fails here instead of rendering a
    blank badge — `STATUS_LABELS[...]` would raise, and this test is where that
    shows.

    Broken to see it red: `compute_activity_status` given back its own
    past/cancelled/open calculation — the "afgesloten" case then reads "Open".
    """
    from app.domains.activities.router import compute_activity_status
    from app.domains.activities.service import (STATUS_LABELS, RegistrationState,
                                                registration_state)

    a = _activity(db_session, "Proef", last_day=last_day, closes_on=closes_on,
                  cancelled=cancelled)
    _pin(monkeypatch, instant)

    toestand = registration_state(a)
    assert compute_activity_status(a, 0)["status"] == STATUS_LABELS[toestand]
    # En elke toestand heeft een label — anders valt dit al bij het opzoeken om.
    assert set(STATUS_LABELS) == set(RegistrationState)
