"""#651 — het detail van één activiteit haalt niet meer de hele lijst op.

`_detail_response` hergebruikte `list_activities(scope="all")` en filterde daarna
in Python op id. Daardoor kostte het detail van ÉÉN activiteit meer dan de lijst
van alle 167: op HDEV gemiddeld 483 ms tegenover 89 ms. En omdat het de gedeelde
render-helper is, betaalde élke mutatie op dat scherm — datum opslaan, onderdeel
toevoegen, product verwijderen, volgorde wijzigen — die 483 ms opnieuw.

Een kale query was niet de oplossing: het scherm heeft de verrijking wél nodig.
Deze tests bewaken precies dat — dat de doorgang lichter is én evenveel toont.
"""
from datetime import date, timedelta

import pytest

from app.domains.activities.api import (Activity, ActivityDate,
                                        get_activity_detail)
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def test_het_detail_toont_ook_voorbije_datums(client, db_session):
    """De valkuil van een herimplementatie: `all_dates=True`.

    Het beheerscherm toont álle datums, niet enkel de toekomstige. Vergeet je die
    vlag, dan verdwijnen voorbije datums stil uit het detail — stil, want er faalt
    niets, er staat gewoon minder.
    """
    activity, _c, _p = seed_activity_with_product(db_session)
    verleden = date.today() - timedelta(days=60)
    toekomst = date.today() + timedelta(days=60)
    db_session.add(ActivityDate(activity_id=activity.id, start_date=verleden))
    db_session.add(ActivityDate(activity_id=activity.id, start_date=toekomst))
    db_session.flush()

    detail = get_activity_detail(db_session, activity.id)
    datums = {d.start_date for d in detail.dates}
    assert verleden in datums, "een voorbije datum verdween uit het detail (#651)"
    assert toekomst in datums

    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert verleden.strftime("%d-%m-%Y") in html


def test_het_detail_draagt_dezelfde_verrijking_als_de_lijst(client, db_session):
    """Niet alleen sneller, ook gelijk: status, telling en volzet-vlag.

    Vergeleken met wat de lijst voor diezelfde activiteit oplevert — dat is de
    enige zinvolle maatstaf, want de lijst was de bron van deze gegevens.
    """
    from app.domains.activities.api import list_activities

    activity, component, _p = seed_activity_with_product(db_session,
                                                         max_participants=1)
    db_session.flush()

    uit_lijst = next(a for a in list_activities(db_session, scope="all")
                     if a.id == activity.id)
    los = get_activity_detail(db_session, activity.id)

    assert los.status == uit_lijst.status
    assert los.registration_count == uit_lijst.registration_count
    assert los.sort_date == uit_lijst.sort_date
    assert [d.start_date for d in los.dates] == [d.start_date for d in uit_lijst.dates]
    # De bezetting per onderdeel wordt batched berekend; hier met één id. Als die
    # berekening stilzwijgend van de volledige lijst afhing, stond is_full nu op
    # None of False terwijl de lijst iets anders zegt.
    volzet_los = {c.id: c.is_full for c in los.sub_registrations}
    volzet_lijst = {c.id: c.is_full for c in uit_lijst.sub_registrations}
    assert volzet_los == volzet_lijst
    assert component.id in volzet_los


def test_een_onbestaande_activiteit_geeft_none(db_session):
    assert get_activity_detail(db_session, 999999) is None


def test_het_detail_haalt_de_andere_activiteiten_niet_op(client, db_session):
    """De kern van #651, uitgedrukt zonder klok.

    Een tijdmeting is te wisselvallig voor CI; het aantal opgehaalde activiteiten
    niet. Dit detail hoort er precies één te raken, hoeveel er ook naast staan.
    """
    activity, _c, _p = seed_activity_with_product(db_session)
    for i in range(10):
        extra = Activity(name=f"Buuractiviteit {i}")
        db_session.add(extra)
        db_session.flush()
        db_session.add(ActivityDate(activity_id=extra.id,
                                    start_date=date.today() + timedelta(days=i + 1)))
    db_session.flush()
    _login(client)

    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert activity.name in html
    assert "Buuractiviteit" not in html, (
        "het detail rendert gegevens van andere activiteiten — dan haalt het ze ook op")
