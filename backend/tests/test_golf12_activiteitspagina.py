"""Golf 12 (#913) — de publieke activiteitspagina op het deeladres.

Door Koen goedgekeurd op het pakket `golfpakket-12-activiteitspagina`
(20 september 2026, één feedbackronde): kop met datumtegel, de affiche als
beeld, de volledige omschrijving, en de onderdelen met dezelfde inschrijfacties
als de kaart — uit hetzelfde view-model (`list_activities`), zodat status,
volzet en deadline nooit uiteenlopen met de lijst.

De adres-semantiek (komend/archief/404, geen brekende links) staat in
`test_activiteit_recordpagina.py::test_deeladres_stuurt_naar_de_juiste_lijst`;
de gemeten uitlijning van de kaartacties in
`tests_e2e/test_publieke_kaart_uitlijning.py`.
"""
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.ui_serverrendered


def _activiteit(db, naam="Paginaproef", slug=None, dagen=21, closes_on=None,
                description=None):
    from app.domains.activities.api import Activity, ActivityDate

    a = Activity(name=naam, slug=slug, location="Miloheem",
                 registration_closes_on=closes_on, description=description)
    db.add(a); db.flush()
    db.add(ActivityDate(activity_id=a.id,
                        start_date=date.today() + timedelta(days=dagen)))
    db.commit()
    return a


def test_pagina_toont_kop_omschrijving_en_acties(client, db_session):
    from tests.conftest import seed_activity_with_product

    activity, component, _product = seed_activity_with_product(db_session)
    activity.description = "Een avond voor het hele dorp.\nIedereen welkom."
    db_session.commit()

    html = client.get(f"/activiteiten/{activity.id}").text
    assert f"<h1" in html and activity.name in html
    assert "Een avond voor het hele dorp." in html
    assert f"/activiteiten/{activity.id}/inschrijven/{component.id}" in html
    assert "Wie doet er mee?" in html


def test_affiche_staat_als_beeld_op_de_pagina(client, db_session):
    from app.domains.media.api import MediaAsset

    a = _activiteit(db_session, "Afficheproef")
    db_session.add(MediaAsset(kind="activity_poster", activity_id=a.id,
                              title="Affiche", content_type="image/png",
                              data=b"png"))
    db_session.commit()

    html = client.get(f"/activiteiten/{a.id}").text
    assert "<img" in html and "Affiche van Afficheproef" in html
    # Zonder affiche: geen leeg beeldkader.
    b = _activiteit(db_session, "Kaalproef")
    assert "<img" not in client.get(f"/activiteiten/{b.id}").text.split(
        "</nav>", 1)[1].split("<footer", 1)[0].replace(
        '<img src="/api/v1/media', "AFFICHE")


def test_pdf_affiche_toont_haar_voorblad(client, db_session):
    """#1019-route: het beeld is de /thumb, de klik gaat naar het bestand."""
    from app.domains.media.api import MediaAsset

    a = _activiteit(db_session, "Pdfproef")
    db_session.add(MediaAsset(kind="activity_poster", activity_id=a.id,
                              title="Affiche", content_type="application/pdf",
                              data=b"%PDF"))
    db_session.commit()

    html = client.get(f"/activiteiten/{a.id}").text
    assert "/thumb" in html


def test_klokregel_bovenaan_zonder_jaartal_en_oranje_in_de_laatste_week(client, db_session):
    """#1051-copy op de kopregel: "Inschrijven t/m <dag> <maand>" zonder
    jaartal; binnen zeven dagen kleurt hij oranje. De datum is vandaag nog
    activiteitsbreed en valt dus onder de kopregel-tak van #1053."""
    from app.i18n import long_date

    ver = _activiteit(db_session, "Verweg", dagen=60,
                      closes_on=date.today() + timedelta(days=30))
    html = client.get(f"/activiteiten/{ver.id}").text
    label = long_date(ver.registration_closes_on).rsplit(" ", 1)[0]
    assert f"Inschrijven t/m" in html and label in html
    assert str(ver.registration_closes_on.year) not in label
    assert "text-orange-600" not in html

    gauw = _activiteit(db_session, "Bijna", dagen=10,
                       closes_on=date.today() + timedelta(days=3))
    html = client.get(f"/activiteiten/{gauw.id}").text
    assert "Inschrijven t/m" in html and "text-orange-600" in html


def test_geen_klokregel_na_de_deadline(client, db_session):
    """Na de deadline zegt de badge het al ("Inschrijvingen afgesloten") —
    een klokregel ernaast zou tegenspreken wat eronder staat (#977-les).
    De badge staat bij het onderdeel, dus de activiteit heeft er een nodig."""
    from tests.conftest import seed_activity_with_product

    activity, _component, _product = seed_activity_with_product(db_session)
    activity.registration_closes_on = date.today() - timedelta(days=1)
    db_session.commit()

    html = client.get(f"/activiteiten/{activity.id}").text
    assert "Inschrijven t/m" not in html
    assert "Inschrijvingen afgesloten" in html


def test_kaarttitel_linkt_naar_de_pagina(client, db_session):
    """De titel op de lijst gaat naar de activiteitspagina; de affiche staat
    dáár en is zo nog steeds bereikbaar (tot golf 12 linkte de titel het
    bestand rechtstreeks)."""
    a = _activiteit(db_session, "Linkproef", slug="linkproef")
    html = client.get("/activiteiten").text
    assert 'href="/activiteiten/linkproef"' in html


def test_meta_description_draagt_de_omschrijving(client, db_session):
    a = _activiteit(db_session, "Metaproef",
                    description="Korte samenvatting voor de deellink.")
    html = client.get(f"/activiteiten/{a.id}").text
    assert '<meta name="description" content="Korte samenvatting' in html
    assert '<meta property="og:title" content="Metaproef"' in html
