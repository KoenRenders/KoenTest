"""De activiteiten-keuzelijst voor het mediabeheer (#645, #476).

`/admin/media` haalde zijn upload-dropdown uit `list_activities(scope="all")`: een
lijstbewerking met eager loading van datums, onderdelen en producten plus de
bezettingsberekening, om er drie velden uit te lezen. Op HDEV kostte dat p95
578 ms tegen 9–122 ms voor de tien andere adminroutes.

Wat hier vastligt is niet de snelheid maar het gedrag dat de snelle variant moet
behouden: élke activiteit staat in de lijst — ook die zonder media, want dat was
de hele reden voor `scope="all"` (#476) — en het jaar dat erbij staat.
"""
from datetime import date, timedelta

import pytest

from app.domains.activities.api import activity_options

pytestmark = pytest.mark.ui_agnostisch


def _activiteit(db, naam: str, *dagen_offsets: int):
    """Een activiteit met nul of meer datums, relatief aan vandaag."""
    from app.domains.activities.api import Activity, ActivityDate

    activiteit = Activity(name=naam)
    db.add(activiteit)
    db.flush()
    for offset in dagen_offsets:
        db.add(ActivityDate(activity_id=activiteit.id,
                            start_date=date.today() + timedelta(days=offset)))
    db.flush()
    return activiteit


def test_elke_activiteit_staat_in_de_lijst_ook_zonder_media(db_session):
    """De reden voor scope="all" (#476): je moet foto's aan om het even welke
    activiteit kunnen koppelen, ook aan een die er nog geen heeft."""
    met_datum = _activiteit(db_session, "Met datum", -30)
    zonder_datum = _activiteit(db_session, "Zonder datum")

    ids = {optie.id for optie in activity_options(db_session)}

    assert met_datum.id in ids
    assert zonder_datum.id in ids


def test_een_activiteit_zonder_datum_heeft_geen_jaar(db_session):
    zonder = _activiteit(db_session, "Datumloos")

    optie = next(o for o in activity_options(db_session) if o.id == zonder.id)

    assert optie.first_date is None


def test_het_jaar_is_de_vroegste_datum_niet_de_eerstvolgende(db_session):
    """De bewuste gedragswijziging (#645).

    Een activiteit die vorig jaar begon en nog een datum in de toekomst heeft,
    kreeg voorheen het jaar van die toekomstige datum — dus het label schoof mee
    met de tijd. Voor een keuzelijst telt herkenbaarheid: het vroegste jaar hoort
    bij de activiteit, niet bij het moment waarop je kijkt.
    """
    meerjarig = _activiteit(db_session, "Meerjarig", -400, +30)

    optie = next(o for o in activity_options(db_session) if o.id == meerjarig.id)

    assert optie.first_date == date.today() - timedelta(days=400)


def test_voorbije_activiteiten_houden_hetzelfde_jaar_als_voorheen(db_session):
    """Voor de grote meerderheid verandert er niets: zonder toekomstige datum viel
    de oude berekening al terug op de eerste datum."""
    voorbij = _activiteit(db_session, "Voorbij", -400, -30)

    optie = next(o for o in activity_options(db_session) if o.id == voorbij.id)

    assert optie.first_date == date.today() - timedelta(days=400)


def test_meest_recente_eerst(db_session):
    """Je koppelt foto's aan wat net geweest is, dus die staat bovenaan."""
    oud = _activiteit(db_session, "Oud", -400)
    recent = _activiteit(db_session, "Recent", -5)

    volgorde = [o.id for o in activity_options(db_session)]

    assert volgorde.index(recent.id) < volgorde.index(oud.id)


def test_een_geschrapte_activiteit_staat_er_niet_in(db_session):
    """De globale soft-delete-filter werkt via with_loader_criteria; deze query
    selecteert kolommen i.p.v. entiteiten, dus dat is het bewijzen waard."""
    from app.soft_delete import soft_delete

    geschrapt = _activiteit(db_session, "Geschrapt", -10)
    soft_delete(geschrapt)
    db_session.flush()

    assert geschrapt.id not in {o.id for o in activity_options(db_session)}


def test_het_scherm_gebruikt_de_lichte_variant(client, db_session):
    """De dropdown op /admin/media moet uit `activity_options` komen.

    Zonder deze test is de enige bewaking de query-budget-gate, en die telt
    query's — terwijl de bevinding rij-volume was.
    """
    import inspect

    from app.domains.media import admin_ui

    bron = inspect.getsource(admin_ui._lijst_ctx)
    assert "activity_options(db)" in bron
    # Op de aanroep toetsen, niet op het woord: de toelichting erboven noemt
    # `list_activities` om uit te leggen waarom het er niet meer staat.
    assert "list_activities(" not in bron


def test_de_dropdown_toont_alle_activiteiten_op_het_scherm(client, db_session):
    from app.domains.auth.api import SESSION_COOKIE, make_session_value

    from tests.conftest import SEEDED_ADMIN_EMAIL

    _activiteit(db_session, "Zichtbaar in de keuzelijst", -20)
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    # De activiteit-dropdown hoort bij foto's, niet bij sponsorlogo's; zonder
    # `kind` toont het scherm het sponsorformulier.
    html = client.get("/admin/media/nieuw", params={"kind": "activity_photo"}).text

    assert "Zichtbaar in de keuzelijst" in html
