"""Pariteitsronde 2 (#476): publieke restpunten.
- '(enkel leden)'-badge op activiteitenkaarten.
- Inschrijfformulier voorinvullen (e-mail + mobiel) voor een ingelogd lid.
- Gezin-toevoegformulier met geslacht/mobiel/telefoon-velden.
"""
from datetime import date, timedelta
from decimal import Decimal

from app.domains.activities.api import Activity, ActivityDate, ActivitySubRegistration
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mdm.api import ContactDetail
from tests.conftest import create_test_family


def _members_only_activity(db):
    a = Activity(name="Ledenreis", members_only=True)
    db.add(a)
    db.flush()
    db.add(ActivityDate(activity_id=a.id, start_date=date.today() + timedelta(days=20)))
    db.add(ActivitySubRegistration(
        activity_id=a.id, name="Deelname", registration_type_code="INDIVIDUAL",
        price=Decimal("0"), is_free=True))
    db.flush()
    return a


def test_members_only_badge_on_public_cards(client, db_session):
    _members_only_activity(db_session)
    db_session.commit()
    html = client.get("/activiteiten").text
    assert "enkel leden" in html


def test_registration_form_prefills_email_and_mobile_for_member(client, db_session):
    _member, person = create_test_family(db_session, email="lid@example.com")
    db_session.add(ContactDetail(person_id=person.id, contact_type_code="MOBILE",
                                 value="0470112233", is_primary=True))
    activity = _members_only_activity(db_session)
    comp = activity.sub_registrations[0]
    db_session.commit()

    client.cookies.set(SESSION_COOKIE, make_session_value("lid@example.com"))
    html = client.get(f"/activiteiten/{activity.id}/inschrijven/{comp.id}").text
    assert 'value="lid@example.com"' in html
    assert 'value="0470112233"' in html


def test_registration_form_empty_for_anonymous(client, db_session):
    activity = _members_only_activity(db_session)
    comp = activity.sub_registrations[0]
    db_session.commit()
    html = client.get(f"/activiteiten/{activity.id}/inschrijven/{comp.id}").text
    assert 'value="lid@example.com"' not in html


def test_gezin_add_form_has_gender_mobile_phone(client, db_session):
    _member, person = create_test_family(db_session, email="hoofd@example.com")
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value("hoofd@example.com"))
    html = client.get("/leden/gezin").text
    assert 'name="gender_code"' in html
    assert 'name="mobile"' in html
    assert 'name="phone"' in html
