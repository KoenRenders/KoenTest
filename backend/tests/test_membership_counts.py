"""Actueel ledenaantal: vandaag-geldige lidmaatschappen + gekoppelde personen.

Invarianten (#294/#297): tel enkel lidmaatschappen die op de gevraagde dag geldig
zijn (``is_active`` én ``valid_from <= dag <= valid_to``); soft-deleted records
tellen nooit mee. Dezelfde telling voedt zowel de chatbot-context als het
admin-dashboard, dus die mogen elkaar niet tegenspreken.
"""
from datetime import date, timedelta

from app.domains.payment_status.service import current_membership_counts


def _household(db, n_persons=1, *, is_active=True, valid_from=None, valid_to=None):
    from app.models.member import Membership
    from app.domains.mdm.api import Member, Person, MemberPerson

    today = date.today()
    member = Member()
    db.add(member)
    db.flush()
    persons = []
    for i in range(n_persons):
        p = Person(last_name="Lid", first_name=f"P{i}")
        db.add(p)
        db.flush()
        db.add(MemberPerson(member_id=member.id, person_id=p.id, relation_type="HOOFDLID"))
        persons.append(p)
    db.add(Membership(
        member_id=member.id, year=today.year, is_active=is_active,
        valid_from=valid_from or date(today.year, 1, 1),
        valid_to=valid_to or date(today.year, 12, 31),
    ))
    db.flush()
    return member, persons


def test_counts_only_today_valid_memberships(db_session):
    db = db_session
    today = date.today()
    _household(db, 2)  # geldig heel jaar → telt
    _household(db, 1)  # geldig heel jaar → telt
    _household(db, 5, valid_from=today - timedelta(days=60), valid_to=today - timedelta(days=1))  # verlopen
    _household(db, 5, valid_from=today + timedelta(days=1), valid_to=today + timedelta(days=60))  # toekomstig
    _household(db, 5, is_active=False)  # inactief

    households, persons = current_membership_counts(db, today)
    assert households == 2
    assert persons == 3  # 2 + 1


def test_counts_exclude_soft_deleted_person(db_session):
    from app.soft_delete import soft_delete

    db = db_session
    today = date.today()
    _member, persons = _household(db, 2)
    soft_delete(persons[0])
    db.flush()

    households, n = current_membership_counts(db, today)
    assert households == 1
    assert n == 1  # de verwijderde persoon telt niet meer


def test_counts_exclude_soft_deleted_membership(db_session):
    from app.soft_delete import soft_delete
    from app.models.member import Membership

    db = db_session
    today = date.today()
    member, _persons = _household(db, 2)
    ms = db.query(Membership).filter(Membership.member_id == member.id).one()
    soft_delete(ms)
    db.flush()

    households, n = current_membership_counts(db, today)
    assert households == 0
    assert n == 0


def test_counts_boundary_dates_inclusive(db_session):
    """valid_from == vandaag en valid_to == vandaag tellen mee (grenzen inclusief)."""
    db = db_session
    today = date.today()
    _household(db, 1, valid_from=today, valid_to=today)
    households, persons = current_membership_counts(db, today)
    assert households == 1
    assert persons == 1


def test_chatbot_context_reports_member_counts(db_session):
    from app.domains.chatbot.context import build_system_prompt

    db = db_session
    _household(db, 2)
    prompt = build_system_prompt(db)
    assert "## Ledenaantal" in prompt
    assert "1 aangesloten gezin" in prompt
    assert "2 personen" in prompt


def test_admin_stats_includes_member_persons(client, db_session, admin_headers):
    db = db_session
    _household(db, 2)
    _household(db, 1)
    resp = client.get("/api/v1/admin/stats", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_member_households"] == 2
    assert data["active_member_persons"] == 3
