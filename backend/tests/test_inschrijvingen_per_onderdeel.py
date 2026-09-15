"""#650-waarborgen op de gegroepeerde Inschrijvingen-tab (golf 8, ronde 2).

Herzien op de feedbackronde van 15 september 2026: "Toon inschrijvingen" en de
zonder-onderdeel-kaart verdwenen van het Overzicht; de Inschrijvingen-tab
groepeert per onderdeel en draagt een groep "Zonder onderdeel". De twee
oorspronkelijke #650-waarborgen blijven de meetlat: je ziet wíé waarvoor
ingeschreven is, en een inschrijving zonder onderdeel blijft bereikbaar.

Oorspronkelijke context:

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

from app.domains.activities.api import ActivitySubRegistration, Registration
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


def test_de_tab_groepeert_per_onderdeel(client, db_session):
    """De kern van #650, nu als groepering: wie bij A hoort staat onder A."""
    activity, comp_a, _p = seed_activity_with_product(db_session)
    comp_b = _onderdeel(db_session, activity, "Tweede onderdeel")
    _inschrijving(db_session, activity, "AnnekeA", comp_a)
    _inschrijving(db_session, activity, "BrunoB", comp_b)
    _login(client)

    html = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen").text
    assert comp_a.name in html and "Tweede onderdeel" in html
    # Volgorde bewijst de groepering: A-kop, dan Anneke, dan B-kop, dan Bruno.
    assert html.index(comp_a.name) < html.index("AnnekeA") \
        < html.index("Tweede onderdeel") < html.index("BrunoB")
    # Exportknop per groep (verhuisd van het Overzicht).
    assert f"/onderdelen/{comp_a.id}/export" in html
    assert f"/onderdelen/{comp_b.id}/export" in html


def test_het_overzicht_draagt_geen_inschrijvingenknoppen_meer(client, db_session):
    """Ronde 2: Toon inschrijvingen en Export horen bij de tab, niet bij het
    Overzicht."""
    activity, comp_a, _p = seed_activity_with_product(db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "Toon inschrijvingen" not in html
    assert f"/onderdelen/{comp_a.id}/export" not in html


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


def test_inschrijving_zonder_onderdeel_blijft_bereikbaar(client, db_session):
    """Geval (c): precies wat een naïeve fix stukmaakt. De tab draagt een groep
    "Zonder onderdeel" zodra zulke inschrijvingen bestaan."""
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

    lijst = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen")
    assert lijst.status_code == 200 and "WeesWillem" in lijst.text
    assert "Zonder onderdeel" in lijst.text


def test_een_verwijdering_keert_terug_naar_de_activiteit(client, db_session):
    """Ronde 2: de enige verwijderknop staat op de inschrijvingspagina; na de
    verwijdering stuurt de server terug naar de activiteit."""
    activity, comp_a, _p = seed_activity_with_product(db_session)
    reg_a = _inschrijving(db_session, activity, "AnnekeA", comp_a)
    csrf = _login(client)

    r = client.post(
        f"/admin/activiteiten/{activity.id}/inschrijvingen/{reg_a.id}/verwijderen"
        f"?vanuit=pagina", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 204
    assert r.headers["HX-Redirect"] == f"/admin/activiteiten/{activity.id}"
    tab = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen").text
    assert "AnnekeA" not in tab
