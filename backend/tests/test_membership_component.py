"""Fase 4a (#402): membership-component — hernieuwingsvenster op één plek en
de is_member-facade voor andere componenten."""
from datetime import date

from app.domains.membership.api import is_member, renewal_available, renewal_open
from tests.conftest import create_test_family


def test_renewal_open_follows_configured_window(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "membership_renewal_start_md", "11-01")
    assert renewal_open(date(2026, 10, 31)) is False
    assert renewal_open(date(2026, 11, 1)) is True
    monkeypatch.setattr(settings, "membership_renewal_start_md", None)
    assert renewal_open(date(2026, 12, 31)) is False
    monkeypatch.setattr(settings, "membership_renewal_start_md", "kapot")
    assert renewal_open(date(2026, 12, 31)) is False


def test_renewal_available_rules(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "membership_renewal_start_md", "11-01")
    # Zonder geldig lidmaatschap altijd; mét pas zodra het venster open is.
    assert renewal_available(None, date(2026, 5, 1)) is True
    assert renewal_available(date(2026, 12, 31), date(2026, 5, 1)) is False
    assert renewal_available(date(2026, 12, 31), date(2026, 11, 2)) is True


def test_is_member_facade(db_session, monkeypatch):
    from app.domains.membership.api import Membership
    member, person = create_test_family(db_session, email="lidcheck@example.com")
    assert is_member(db_session, "lidcheck@example.com") is False
    assert is_member(db_session, "onbekend@example.com") is False

    db_session.add(Membership(member_id=member.id, year=date.today().year,
                              is_active=True, valid_from=date(date.today().year, 1, 1),
                              valid_to=date(date.today().year, 12, 31)))
    db_session.flush()
    db_session.expire_all()
    assert is_member(db_session, "lidcheck@example.com") is True
