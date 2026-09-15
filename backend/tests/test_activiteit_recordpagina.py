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


def test_zonder_finance_geen_betalingen_tab(client, db_session):
    """Een tab die op een 403 uitkomt is erger dan geen tab (#544). De
    gezaaide beheerder draagt FINANCE (migratie 056), dus dit toetst met het
    bestuurslid — ADMIN zonder FINANCE (migratie 014)."""
    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    waarde = make_session_value("bestuurslid@example.com")
    client.cookies.set(SESSION_COOKIE, waarde)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "Inschrijvingen 2" in html
    assert f"/admin/activiteiten/{activity.id}/betalingen" not in html


def test_finance_ziet_de_betalingen_tab(client, db_session):
    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    _make_finance(db_session)
    db_session.commit()
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    # Feedbackronde 15 sep: de tab is de INGEBEDDE pagina onder het record.
    assert f'href="/admin/activiteiten/{activity.id}/betalingen"' in html
    assert "Betalingen 2" in html  # twee inschrijvingen, elk één betaalrecord


def test_de_rail_toont_bezetting_en_totaal(client, db_session):
    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "Bezetting" in html and component.name in html
    assert "Inschrijvingen totaal" in html


def test_inschrijvingen_tab_toont_alles_met_onderdeelkolom(client, db_session):
    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen").text

    assert "<title>" in html  # volwaardige pagina, niet het oude fragment
    assert ">Onderdeel<" in html or "Onderdeel" in html
    assert "Rec Anna" in html and "Rec Bert" in html
    assert html.count(component.name) >= 2  # de Onderdeel-kolom per rij
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


def test_activiteitniveau_fragment_verhuisde_naar_fragment(client, db_session):
    """Het oude fragmentadres is nu de tabpagina; het fragment woont op
    /fragment. De knop staat alleen bij inschrijvingen zonder onderdeel
    (#650), dus de bedrading toetsen we op de template-bron."""
    from pathlib import Path

    activity, component = _activiteit_met_inschrijvingen(client, db_session)
    _login(client)
    frag = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen/fragment").text
    assert "<title>" not in frag
    bron = (Path(__file__).resolve().parents[1] / "app" / "domains" / "activities"
            / "templates" / "_aa_detail.html").read_text(encoding="utf-8")
    assert "/inschrijvingen/fragment" in bron, \
        "de Overzicht-knop wijst niet naar het verhuisde fragment"


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
