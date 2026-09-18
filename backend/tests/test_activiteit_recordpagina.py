"""Golf 8 (#913): de activiteit als recordpagina — P13 in tabvorm.

Tabs Overzicht · Inschrijvingen N · Betalingen N: elke tab toont een bestaand
lijstscherm in de scope van dit record. Betalingen alleen met FINANCE (#544);
de tab navigeert naar het gewone betalingenscherm in `?activiteit=`-scope.
"""
import pytest
pytestmark = pytest.mark.ui_serverrendered

from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product
from app.domains.auth.api import (SESSION_COOKIE, User, UserRole,
                                  csrf_token_for, make_session_value)


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _make_finance(db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db.flush()


def _activiteit_met_inschrijvingen(client, db_session, namen=("Rec Anna", "Rec Bert")):
    activity, component, product = seed_activity_with_product(
        db_session, price="10.00", is_free=False)
    for naam in namen:
        client.post(f"/activiteiten/{activity.id}/inschrijven/{component.id}",
                    data={"contact_name": naam, "contact_email": "rec@example.com",
                          "phone": "047", f"product_{product.id}": "1",
                          "payment_method": "OVERSCHRIJVING"})
    return activity, component


def test_overzicht_draagt_tabs_met_aantallen(client, db_session):
    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text

    assert ">Overzicht</a>" in html
    assert "Inschrijvingen 2" in html
    assert f'href="/admin/activiteiten/{activity.id}/inschrijvingen"' in html


def test_admin_zonder_finance_ziet_de_betalingen_tab_wel(client, db_session):
    """Herzien in golf 9: betalingen BEKIJKEN mag voor ADMIN/FINANCE/OPERATOR
    (require_finance_ui) — de golf 8-gating op FINANCE alleen was te streng en
    verstopte de tab voor een gewone ADMIN terwijl het scherm gewoon opende.
    De tab volgt nu exact dezelfde vraag als de poort (may_view_payments)."""
    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    waarde = make_session_value("bestuurslid@example.com")
    client.cookies.set(SESSION_COOKIE, waarde)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "Inschrijvingen 2" in html
    assert f"/admin/activiteiten/{activity.id}/betalingen" in html


def test_finance_ziet_de_betalingen_tab(client, db_session):
    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    _make_finance(db_session)
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    # Feedbackronde 15 sep: de tab is de INGEBEDDE pagina onder het record.
    assert f'href="/admin/activiteiten/{activity.id}/betalingen"' in html
    assert "Betalingen 2" in html  # twee inschrijvingen, elk één betaalrecord


def test_de_rail_toont_bezetting(client, db_session):
    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "Bezetting" in html and component.name in html
    # "Inschrijvingen totaal" verdween op Koens vraag (15 sep): het aantal
    # staat al op de tab.
    assert "Inschrijvingen totaal" not in html


def test_inschrijvingen_tab_toont_alles_met_onderdeelkolom(client, db_session):
    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen").text

    assert "<title>" in html  # volwaardige pagina
    # Ronde 2: gegroepeerd per onderdeel — de groepskop draagt de naam en het
    # aantal, met een exportknop per groep.
    assert component.name in html
    assert f"/onderdelen/{component.id}/export" in html
    assert "Rec Anna" in html and "Rec Bert" in html
    # Naamlink draagt de A7-terugweg met de sorteerstand.
    assert "?terug=" in html


def test_inschrijvingen_tab_sorteert_en_valt_veilig_terug(client, db_session):
    import re

    activity, component = _activiteit_met_inschrijvingen(
        client, db_session, namen=("Rec Carla", "Rec Anna", "Rec Bert"))
    _login(client)
    basis = f"/admin/activiteiten/{activity.id}/inschrijvingen"

    def namen(html):
        gezien = []
        for n in re.findall(r"Rec (\w+)", html):
            if n not in gezien:
                gezien.append(n)
        return gezien

    assert namen(client.get(f"{basis}?sort=naam&richting=asc").text) == \
        ["Anna", "Bert", "Carla"]
    resp = client.get(f"{basis}?sort=x);DROP--&richting=zijwaarts")
    assert resp.status_code == 200
    assert namen(resp.text) == ["Carla", "Anna", "Bert"]  # inschrijfvolgorde


def test_de_lijstfragmenten_bestaan_niet_meer(client, db_session):
    """Ronde 2 (15 sep): de tab verving de losse lijstfragmenten volledig; het
    oude fragmentadres hoort niet stil iets anders te gaan betekenen."""
    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    _login(client)
    assert client.get(
        f"/admin/activiteiten/{activity.id}/inschrijvingen/fragment"
    ).status_code == 404


def test_betalingen_activiteitscope_toont_enkel_deze_activiteit(client, db_session):
    a1, _c1 = _activiteit_met_inschrijvingen(client, db_session,
                                             namen=("Rec Anna",))
    a2, _c2 = _activiteit_met_inschrijvingen(client, db_session,
                                             namen=("Ander Feest",))
    _make_finance(db_session)
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/betalingen?activiteit={a1.id}").text

    assert "Voor activiteit:" in html and a1.name in html
    assert "Rec Anna" in html
    assert "Ander Feest" not in html
    assert "Alle bekijken" in html
    assert f'name="activiteit" value="{a1.id}"' in html
    # De exportknop draagt de scope mee.
    assert f"&amp;activiteit={a1.id}" in html


def test_betalingen_activiteitscope_vervalst_id_lekt_niets(client, db_session):
    a1, _c1 = _activiteit_met_inschrijvingen(client, db_session,
                                             namen=("Rec Anna",))
    _make_finance(db_session)
    db_session.commit()
    _login(client)
    los = client.get("/admin/betalingen?activiteit=1;DROP--").text
    assert "Voor activiteit:" not in los and "Rec Anna" in los
    leeg = client.get("/admin/betalingen?activiteit=999999").text
    assert "Voor activiteit:" in leeg and "#999999" in leeg
    assert "Rec Anna" not in leeg


def test_elk_invulbaar_veld_is_zichtbaar_in_leesmodus(client, db_session):
    """Ronde 4/5 (15 sep): wat je kan invullen, zie je ook in leesmodus — maar
    zonder misleiding. De Poster-URL toont alleen wanneer hij GELDT (zonder
    upload; een upload prevaleert, #223), en de vriendelijke URL zit in de
    deellink rechts — kopieerbaar, en niet dubbel op de kaart."""
    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    activity.slug = "proefslug-2026"
    activity.poster_url = "https://example.org/affiche.png"
    db_session.flush()
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text

    # Zonder upload geldt de Poster-URL en staat hij als leesregel.
    assert "Poster-URL" in html and "https://example.org/affiche.png" in html
    # De slug zit in de deellink (het kanonieke adres, ronde 6), niet dubbel
    # links als leesregel — het bewérkveld heet uiteraard nog zo.
    assert "/activiteiten/proefslug-2026" in html
    assert "Vriendelijke URL:" not in html
    blok = html.split("Poster-URL")[0]
    assert 'x-show="!edit"' in blok[-400:]


def test_deeladres_stuurt_naar_de_juiste_lijst(client, db_session):
    """Ronde 6 (15 sep): een vooraf gedeelde link blijft ná het evenement
    werken — het kanonieke adres kiest zelf tussen de komende lijst en het
    archief, met het kaart-anker erbij."""
    from datetime import date, timedelta

    from app.domains.activities.api import Activity, ActivityDate

    komend = Activity(name="Komende proef", slug="komende-proef")
    voorbij = Activity(name="Voorbije proef", slug="voorbije-proef")
    db_session.add_all([komend, voorbij])
    db_session.flush()
    db_session.add_all([
        ActivityDate(activity_id=komend.id,
                     start_date=date.today() + timedelta(days=10)),
        ActivityDate(activity_id=voorbij.id,
                     start_date=date.today() - timedelta(days=10)),
    ])
    db_session.flush()

    r1 = client.get("/activiteiten/komende-proef", follow_redirects=False)
    assert r1.status_code == 302 and r1.headers["location"].endswith(
        "/activiteiten#komende-proef")
    r2 = client.get("/activiteiten/voorbije-proef", follow_redirects=False)
    assert r2.status_code == 302 and r2.headers["location"].endswith(
        "/activiteiten/archief#voorbije-proef")
    # Ook op nummer, en onbekend is een nette 404.
    r3 = client.get(f"/activiteiten/{komend.id}", follow_redirects=False)
    assert r3.status_code == 302
    assert client.get("/activiteiten/bestaat-niet",
                      follow_redirects=False).status_code == 404


def test_opslaan_ververst_kop_en_rail_out_of_band(client, db_session):
    """HDEV-melding 15 sep: kop en rail staan buiten #aa-detail en bleven na
    een opslag op de oude stand. Het fragment-antwoord draagt ze nu oob mee —
    mét de nieuwe naam."""
    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    csrf = _login(client)
    r = client.post(f"/admin/activiteiten/{activity.id}",
                    data={"name": "Vernieuwde naam", "location": "Elders"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert 'id="aa-recordkop" hx-swap-oob="true"' in r.text
    assert 'id="aa-rail" hx-swap-oob="true"' in r.text
    assert "Vernieuwde naam" in r.text and "Bezetting" in r.text


def test_raakje_knop_volgt_de_beheerassistent_schakelaar(client, db_session, monkeypatch):
    """Golf 10 (#913): de "AI · Activiteit"-knop bestaat alleen als Raakje voor
    beheer aan staat — één bron (tenant_admin_chat_enabled, CR-07 §6.3), geen
    eigen vlag. Zolang het record-endpoint er niet is toont de overlay een
    nette uitgeschakelde staat."""
    from app.config import settings
    from app.kernel.tenant_config import set_setting
    from app.kernel.tenancy import DEFAULT_TENANT_ID

    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    _login(client)

    # Uit (standaard): geen knop, ook niet op de betalingen-tab.
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "AI · Activiteit" not in html

    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    set_setting(db_session, "admin_chat_enabled", "1", tenant_id=DEFAULT_TENANT_ID)
    db_session.commit()

    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "AI · Activiteit" in html
    # De overlay draagt het echte gesprek (#975): het pad-gebonden endpoint en
    # het historie-veld dat het antwoordfragment out-of-band bijwerkt.
    assert f'hx-post="/admin/rapporten/raakje/activiteit/{activity.id}"' in html
    assert 'name="historie" id="rp-raakje-historie"' in html
