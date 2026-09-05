"""#650 — "Toon inschrijvingen" hoort per onderdeel, en de spookkaart verdwijnt.

Twee klachten die één oorzaak hebben. Er stond één knop op activiteitniveau, ná
de onderdelen-lus en onvoorwaardelijk:

* bij **twee onderdelen** kreeg je één platte lijst van alles — je zag wie
  ingeschreven was, maar niet waarvoor, want de lijst toont het onderdeel nergens
  per rij;
* bij **nul onderdelen** viel die kaart pal onder de lege kop "Onderdelen", met
  dezelfde `h3 font-semibold` als een onderdeelkaart, en las ze als een onderdeel
  dat er niet is. Dat raakt ruim de helft van de activiteiten op HDEV.

De valkuil zit in de conditie, niet in de knop: `Registration.component_id` is
nullable met `ondelete="SET NULL"`. Verdwijnt een onderdeel, dan blijven zijn
inschrijvingen bestaan zonder onderdeel. Een fix die alleen per onderdeel toont,
maakt die onbereikbaar — onzichtbaar terwijl ze in de databank staan.
"""
from decimal import Decimal

import pytest

from app.domains.activities.api import (ActivitySubRegistration, Registration,
                                        registrations_without_component_count)
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _onderdeel(db, activity, naam):
    comp = ActivitySubRegistration(
        activity_id=activity.id, name=naam, registration_type_code="INDIVIDUAL",
        price=Decimal("0"), is_free=True)
    db.add(comp)
    db.flush()
    return comp


def _inschrijving(db, activity, naam, component=None):
    reg = Registration(activity_id=activity.id, registration_type="INDIVIDUAL",
                       contact_name=naam, contact_email=f"{naam}@example.com",
                       component_id=component.id if component else None)
    db.add(reg)
    db.flush()
    return reg


def test_de_knop_van_een_onderdeel_toont_enkel_dat_onderdeel(client, db_session):
    """De kern. Let op de tweede assert: een lijst die álles toont, slaagt voor de
    eerste. De afwezigheid van B is het bewijs, niet de aanwezigheid van A."""
    activity, comp_a, _p = seed_activity_with_product(db_session)
    comp_b = _onderdeel(db_session, activity, "Tweede onderdeel")
    _inschrijving(db_session, activity, "AnnekeA", comp_a)
    _inschrijving(db_session, activity, "BrunoB", comp_b)
    _login(client)

    r = client.get(f"/admin/activiteiten/{activity.id}/onderdelen/{comp_a.id}/inschrijvingen")
    assert r.status_code == 200
    assert "AnnekeA" in r.text
    assert "BrunoB" not in r.text, (
        "de lijst van onderdeel A toont ook de inschrijving van onderdeel B (#650)")

    andersom = client.get(
        f"/admin/activiteiten/{activity.id}/onderdelen/{comp_b.id}/inschrijvingen")
    assert "BrunoB" in andersom.text and "AnnekeA" not in andersom.text


def test_elk_onderdeel_heeft_zijn_eigen_knop_en_doel(client, db_session):
    """De knop staat in de kaart van het onderdeel, met een eigen doel-div; anders
    swapt onderdeel B zijn lijst in de kaart van A."""
    activity, comp_a, _p = seed_activity_with_product(db_session)
    comp_b = _onderdeel(db_session, activity, "Tweede onderdeel")
    _login(client)

    html = client.get(f"/admin/activiteiten/{activity.id}").text
    for comp in (comp_a, comp_b):
        assert f"/onderdelen/{comp.id}/inschrijvingen" in html
        assert f'id="aa-insch-{comp.id}"' in html


def test_zonder_onderdelen_geen_kaart_wel_een_lege_toestand(client, db_session):
    """Geval (b): de gemelde spookkaart is weg en de sectie legt zichzelf uit."""
    from app.domains.activities.api import Activity, ActivityDate
    from datetime import date, timedelta

    activity = Activity(name="Kale activiteit")
    db_session.add(activity)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=activity.id,
                                start_date=date.today() + timedelta(days=10)))
    db_session.flush()
    _login(client)

    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "Nog geen onderdelen" in html, "de lege toestand ontbreekt"
    assert "Inschrijvingen" not in html.split("Nog geen onderdelen")[1], (
        "er staat nog een Inschrijvingen-kaart onder de lege Onderdelen-sectie (#650)")


def test_inschrijving_zonder_onderdeel_blijft_bereikbaar(client, db_session):
    """Geval (c): precies wat een naïeve fix stukmaakt.

    Zonder onderdelen, maar mét een inschrijving die er geen heeft — bijvoorbeeld
    omdat het onderdeel verwijderd is. Die inschrijving moet via het scherm te
    bereiken blijven.
    """
    from app.domains.activities.api import Activity, ActivityDate
    from datetime import date, timedelta

    activity = Activity(name="Activiteit met wees")
    db_session.add(activity)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=activity.id,
                                start_date=date.today() + timedelta(days=10)))
    db_session.flush()
    _inschrijving(db_session, activity, "WeesWillem")
    _login(client)

    assert registrations_without_component_count(db_session, activity.id) == 1
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "Inschrijvingen zonder onderdeel" in html, (
        "de inschrijving zonder onderdeel is via geen enkele knop meer te bereiken")

    lijst = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen")
    assert lijst.status_code == 200 and "WeesWillem" in lijst.text


def test_een_verwijdering_toont_dezelfde_lijst_terug(client, db_session):
    """Na verwijderen in onderdeel A mag niet de volledige lijst in A's plaats
    komen — de knop stond in één bepaalde lijst."""
    activity, comp_a, _p = seed_activity_with_product(db_session)
    comp_b = _onderdeel(db_session, activity, "Tweede onderdeel")
    reg_a = _inschrijving(db_session, activity, "AnnekeA", comp_a)
    _inschrijving(db_session, activity, "BrunoB", comp_b)
    csrf = _login(client)

    r = client.post(
        f"/admin/activiteiten/{activity.id}/inschrijvingen/{reg_a.id}/verwijderen"
        f"?component_id={comp_a.id}", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert "AnnekeA" not in r.text, "de verwijderde inschrijving staat er nog"
    assert "BrunoB" not in r.text, (
        "na een verwijdering in onderdeel A komt de lijst van álle onderdelen terug")


def test_de_wezen_telling_negeert_onderdelen(db_session):
    """De telling waarop de kaart staat of valt."""
    activity, comp_a, _p = seed_activity_with_product(db_session)
    _inschrijving(db_session, activity, "MetOnderdeel", comp_a)
    assert registrations_without_component_count(db_session, activity.id) == 0

    _inschrijving(db_session, activity, "ZonderOnderdeel")
    assert registrations_without_component_count(db_session, activity.id) == 1
