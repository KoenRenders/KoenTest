"""Golf 11 — de publieke ronde, zoals Koen ze op het voorstel besliste (#913).

Vier beslissingen van 19 september 2026: (1) de kaartlayout met de acties in de
inhoudskolom, (2) de begrensde formulierkolom op Word lid (F18), (3) de eerste
jaarkop weg maar de titel "Activiteiten" behouden, (4) een intro-band bovenaan
de homepage met links de CMS-tekst en rechts tarief + geldigheid + de knoppen
Word lid en Contacteer ons. Geen hero, footer onaangeroerd.
"""
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_serverrendered

_TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "domains"


def test_de_introband_toont_tarief_en_geldigheid_uit_de_betaal_api(client, db_session):
    """Het bedrag komt uit dezelfde helper als de aanrekening — de band kan dus
    niet iets anders beloven dan Word lid vraagt (zelfde contract als F3)."""
    from app.domains.payment.api import (membership_price_for_date,
                                         membership_valid_period)

    html = client.get("/").text
    assert f"€ {membership_price_for_date()}".replace(".", ",") in html
    _van, tot = membership_valid_period()
    assert f"per gezin, geldig tot en met {tot.year}" in html
    # De twee knoppen staan in de band; de hero-variant is er bewust niet.
    assert "Word lid" in html and "Contacteer ons" in html
    assert "Meer samen." not in html


def test_de_homepage_kop_blijft_activiteiten(client):
    """Koens correctie op het voorstel: 'Op de agenda' werd het niet."""
    html = client.get("/").text
    assert ">Activiteiten</h2>" in html
    assert "Op de agenda" not in html


def test_eerste_jaarkop_valt_weg_maar_een_jaarwissel_blijft(client, db_session):
    """De jaarkop pal onder de sectiekop was ruis zolang hij gewoon het lopende
    jaar toont; bij een echte jaarwissel verderop blijft hij staan."""
    from app.domains.activities.api import Activity, ActivityDate

    dit_jaar = date.today() + timedelta(days=30)
    volgend_jaar = date(date.today().year + 1, 3, 1)
    for naam, dag in (("Ditjaar-test", dit_jaar), ("Volgendjaar-test", volgend_jaar)):
        a = Activity(name=naam, location="Miloheem")
        db_session.add(a); db_session.flush()
        db_session.add(ActivityDate(activity_id=a.id, start_date=dag))
    db_session.commit()

    html = client.get("/activiteiten").text
    koppen = re.findall(r"<h3[^>]*>(\d{4})</h3>", html)
    assert str(volgend_jaar.year) in koppen, "de jaarwissel verdient nog altijd een kop"
    assert str(dit_jaar.year) not in koppen, "het lopende jaar hoort geen eerste kop te krijgen"


def test_open_krijgt_geen_badge_maar_vol_wel(client, db_session):
    """Eigenaarbevinding 1: 'Open' is de normale toestand — de inschrijfknop is
    het positieve signaal. Wat afwijkt (een volzet onderdeel) houdt zijn badge."""
    from tests.conftest import seed_activity_with_product

    _, comp, product = seed_activity_with_product(db_session, max_participants=2)
    resp = client.post(f"/api/v1/activities/{comp.activity_id}/register", json={
        "contact_name": "An Janssens", "phone": "0470000000",
        "contact_email": "vol@example.com", "component_id": comp.id,
        "payment_method": "transfer",
        "items": [{"product_id": product.id, "quantity": 2}],
    })
    assert resp.status_code in (200, 201), resp.text

    html = client.get("/activiteiten").text
    assert ">Open<" not in html.replace(" ", "")
    assert "Volzet" in html


def test_acties_staan_in_de_inhoudskolom(client, db_session):
    """F32 (desktop): onderdelen en knoppen sluiten aan bij titel en gegevens.
    De kaartbron zet het actieblok binnen de kolom `min-w-0 flex-1`; op mobiel
    breekt `-ml-[60px] sm:ml-0` het weer uit tot de volle kaartbreedte. De
    gemeten uitlijning staat in tests_e2e/test_publieke_kaart_uitlijning.py."""
    bron = (_TEMPLATES / "activities" / "templates" / "_activiteiten_cards.html").read_text()
    kolom = bron.index('min-w-0 flex-1')
    acties = bron.index('mt-3 space-y-3')
    assert kolom < acties
    # Tussen kolomopening en actieblok wordt de flex-rij nergens al gesloten:
    # het patroon dat de oude versie kenmerkte (twee sluittags direct na de
    # beschrijving, vóór het actieblok) komt er niet meer in voor.
    assert "-ml-[60px] sm:ml-0" in bron


def test_word_lid_heeft_de_begrensde_formulierkolom(client):
    """F18: zelfde kolom als het publieke formulier; velden niet meer over de
    volle paginabreedte."""
    html = client.get("/lid-worden").text
    assert 'class="max-w-2xl mx-auto"' in html


def test_migratie_141_vervangt_alleen_de_onaangeroerde_intro(db_session):
    """De datastap ruilt exact de standaardtekst (na 028+132) voor Koens
    bandtekst; een herschreven intro blijft staan, en nul geraakt gaat nooit
    stil als succes door."""
    import importlib.util

    import sqlalchemy as sa

    pad = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
           / "141_home_intro_membership_band.py")
    spec = importlib.util.spec_from_file_location("migratie_141", pad)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    bind = db_session.connection()
    bind.execute(sa.text(
        "UPDATE cms.cms_pages SET content = :c WHERE slug = 'home-intro'"
    ).bindparams(c=m.OUD))
    assert m.vervang(bind) >= 1
    inhoud = bind.execute(sa.text(
        "SELECT content FROM cms.cms_pages WHERE slug = 'home-intro' LIMIT 1")).scalar()
    assert inhoud == m.NIEUW and "#SamenBeleefJeMeer" in inhoud
    # Idempotent, en een eigen tekst blijft met rust.
    assert m.vervang(bind) == 0
    bind.execute(sa.text(
        "UPDATE cms.cms_pages SET content = :c WHERE slug = 'home-intro'"
    ).bindparams(c="<p>Eigen tekst van een bestuur.</p>"))
    assert m.vervang(bind) == 0
