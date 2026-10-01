"""Copy an activity to a next year (#1397).

Koen, 30 September 2026: many activities come back every year with the same
set-up and a date that moves a day or a year. The copy takes the activity with
every field, its dates moved by one difference in days, and its organisers. Not
its components and products (the board sets those up months ahead, with that
year's prices), registrations or payments. It is on the public agenda at once,
without a way to register.

Proven red against master `0bb17459` (this file on an export of it): there was no
route to copy, so every test that copies failed on the 404.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal

import pytest

from app.domains.activities.api import (
    INDIVIDUAL,
    Activity,
    ActivityDate,
    ActivityProduct,
    ActivitySubRegistration,
    Registration,
)
from app.domains.activities.models import ActivityOrganiser
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Member, MemberPerson, Person
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _person(db, first, *, member=True) -> Person:
    person = Person(
        date_of_birth=date(1980, 1, 1), gender_code="M", first_name=first, last_name="T"
    )
    db.add(person)
    db.flush()
    if member:
        household = Member()
        db.add(household)
        db.flush()
        db.add(MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID"))
        db.flush()
    return person


def _bouwen(db) -> Activity:
    """Two dates (one over two days, with hours), two components with products,
    an organiser who is a member, and a registration."""
    activity = Activity(
        name="Bouwen",
        location="De zaal",
        description="Een dag bouwen.",
        members_only=True,
        board_notes="Sleutel bij de koster.",
    )
    db.add(activity)
    db.flush()
    db.add(
        ActivityDate(
            activity_id=activity.id,
            start_date=date(2026, 11, 14),
            end_date=date(2026, 11, 15),
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
    )
    db.add(ActivityDate(activity_id=activity.id, start_date=date(2026, 11, 21)))
    for n in range(2):
        component = ActivitySubRegistration(
            activity_id=activity.id,
            name=f"Ploeg {n}",
            price=Decimal("5"),
            is_free=False,
            registration_closes_on=date(2026, 11, 7),
        )
        db.add(component)
        db.flush()
        db.add(ActivityProduct(component_id=component.id, name="Deelname", price=Decimal("5")))
    db.add(
        ActivityOrganiser(
            activity_id=activity.id,
            person_id=_person(db, "Organisator").id,
            sort_order=0,
            is_contact=True,
            email_override="bouwen@example.org",
        )
    )
    db.add(
        Registration(
            activity_id=activity.id,
            contact_name="Iemand",
            contact_email="iemand@example.org",
            registration_type=INDIVIDUAL,
        )
    )
    db.commit()
    return activity


def _copy(client, activity_id: int, first_date: date):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return client.post(
        f"/admin/activiteiten/{activity_id}/kopieren",
        data={"start_date": first_date.isoformat()},
        headers={"X-CSRF-Token": csrf_token_for(value)},
    )


def _new_copy(db, answer) -> Activity:
    assert answer.status_code == 204, answer.text[:300]
    new_id = int(answer.headers["HX-Redirect"].rsplit("/", 1)[1])
    db.expire_all()
    return db.get(Activity, new_id)


def test_the_same_weekday_copy_moves_every_date_by_364_days(client, db_session):
    source = _bouwen(db_session)
    before = sorted((d.start_date, d.end_date, d.start_time, d.end_time) for d in source.dates)

    copy = _new_copy(db_session, _copy(client, source.id, date(2027, 11, 13)))

    assert copy.id != source.id
    assert (copy.name, copy.location, copy.description, copy.members_only, copy.board_notes) == (
        "Bouwen",
        "De zaal",
        "Een dag bouwen.",
        True,
        "Sleutel bij de koster.",
    )
    after = sorted((d.start_date, d.end_date, d.start_time, d.end_time) for d in copy.dates)
    moved = [
        (s + timedelta(days=364), e + timedelta(days=364) if e else None, st, et)
        for s, e, st, et in before
    ]
    assert after == moved, "every date 364 days later, the hours unchanged"
    assert [(o.sort_order, o.is_contact, o.email_override) for o in copy.organisers] == [
        (0, True, "bouwen@example.org")
    ]
    assert copy.sub_registrations == [], "no components"
    assert db_session.query(Registration).filter(Registration.activity_id == copy.id).count() == 0
    assert len(source.sub_registrations) == 2, "the original keeps its components"


def test_the_same_calendar_date_crosses_a_leap_year():
    from app.domains.activities.api import copy_suggestions

    assert copy_suggestions(date(2027, 12, 25)).same_date == date(2028, 12, 25)
    assert copy_suggestions(date(2028, 2, 29)).same_date == date(2029, 2, 28)
    assert copy_suggestions(date(2026, 11, 14)).same_weekday == date(2027, 11, 13)


def test_kerstherberg_keeps_25_to_30_december(client, db_session):
    activity = Activity(name="Kerstherberg")
    db_session.add(activity)
    db_session.flush()
    db_session.add(
        ActivityDate(
            activity_id=activity.id, start_date=date(2027, 12, 25), end_date=date(2027, 12, 30)
        )
    )
    db_session.commit()

    same_date = date(2028, 12, 25)  # copy_suggestions(25 December 2027).same_date
    copy = _new_copy(db_session, _copy(client, activity.id, same_date))

    assert [(d.start_date, d.end_date) for d in copy.dates] == [
        (date(2028, 12, 25), date(2028, 12, 30))
    ]


def test_a_copy_that_fails_halfway_leaves_nothing(client, db_session, monkeypatch):
    source = _bouwen(db_session)
    count = db_session.query(Activity).count()

    def broken(*args, **kwargs):
        raise RuntimeError("halfway")

    monkeypatch.setattr(ActivityOrganiser, "__init__", broken)
    with pytest.raises(RuntimeError, match="halfway"):
        _copy(client, source.id, date(2027, 11, 13))

    db_session.expire_all()
    assert db_session.query(Activity).count() == count, "no half copy"


def test_an_organiser_who_is_no_member_does_not_come_along(client, db_session):
    source = _bouwen(db_session)
    db_session.add(
        ActivityOrganiser(
            activity_id=source.id,
            person_id=_person(db_session, "Oudlid", member=False).id,
            sort_order=1,
        )
    )
    db_session.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)

    step = client.get(f"/admin/activiteiten/{source.id}/kopieren").text
    copy = _new_copy(db_session, _copy(client, source.id, date(2027, 11, 13)))

    assert "Niet meer lid, dus niet mee als organisator: Oudlid T." in step
    assert len(copy.organisers) == 1


def test_the_copy_is_on_the_agenda_without_a_way_to_register(client, db_session):
    source = _bouwen(db_session)
    copy = _new_copy(db_session, _copy(client, source.id, date(2027, 11, 13)))
    client.cookies.clear()

    agenda = client.get("/activiteiten").text

    assert f'href="/activiteiten/{copy.id}"' in agenda or copy.name in agenda
    assert f"/activiteiten/{copy.id}/inschrijven/" not in agenda, "no registration button"


def test_the_poster_stays_empty_and_the_design_comes_along_unrendered(client, db_session):
    """Koen, 30 September 2026: the copy's poster and links are empty; a Design
    Studio design comes along as the copy's own, with the same template, texts
    and pictures (the same media), and nothing rendered. The source is untouched."""
    from app.domains.designstudio.models import (
        Design,
        DesignHighlight,
        DesignLogo,
        DesignRendition,
        DesignVersion,
        Layout,
        RenderVariant,
    )

    source = _bouwen(db_session)
    source.poster_url = "https://example.org/affiche.pdf"
    design = Design(
        activity_id=source.id,
        duo_code="blauw-geel",
        tagline="Samen bouwen",
        subtitle="Voor jong en oud",
        main_image_id=11,
        inset_image_id=12,
        third_image_id=13,
    )
    design.highlights = [DesignHighlight(sort_order=0, icon_code="hammer", text="Timmeren")]
    design.logos = [DesignLogo(media_asset_id=21, sort_order=0)]
    db_session.add(design)
    db_session.flush()
    version = DesignVersion(design_id=design.id, number=1, facts_fingerprint="f" * 64)
    db_session.add(version)
    db_session.flush()
    db_session.add(
        DesignRendition(
            design_id=design.id,
            version_id=version.id,
            layout_code=Layout.PRINT_A,
            variant=RenderVariant.PDF,
            media_asset_id=31,
        )
    )
    db_session.commit()
    source_id, design_id = source.id, design.id

    copy = _new_copy(db_session, _copy(client, source_id, date(2027, 11, 13)))

    assert copy.poster_url is None, "the poster address is empty on the copy"
    [own] = db_session.query(Design).filter(Design.activity_id == copy.id).all()
    assert own.id != design_id
    assert (own.duo_code, own.tagline, own.subtitle) == (
        "blauw-geel",
        "Samen bouwen",
        "Voor jong en oud",
    )
    assert (own.main_image_id, own.inset_image_id, own.third_image_id) == (11, 12, 13)
    assert [(h.icon_code, h.text) for h in own.highlights] == [("hammer", "Timmeren")]
    assert [lg.media_asset_id for lg in own.logos] == [21]
    assert own.versions == [] and own.published_version_id is None, "nothing rendered"
    assert (
        db_session.query(DesignRendition).filter(DesignRendition.design_id == own.id).count() == 0
    )

    source_design = db_session.get(Design, design_id)
    assert source_design.activity_id == source_id and len(source_design.versions) == 1
    assert db_session.get(Activity, source_id).poster_url == "https://example.org/affiche.pdf"


def test_a_copy_without_a_new_start_date_is_refused_with_the_reason(client, db_session):
    source = _bouwen(db_session)
    count = db_session.query(Activity).count()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)

    answer = client.post(
        f"/admin/activiteiten/{source.id}/kopieren",
        data={},
        headers={"X-CSRF-Token": csrf_token_for(value)},
    )

    assert answer.status_code == 200
    assert "Kies de nieuwe begindatum." in answer.text
    db_session.expire_all()
    assert db_session.query(Activity).count() == count, "no copy"
