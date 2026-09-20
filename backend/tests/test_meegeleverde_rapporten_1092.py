"""Meegeleverde rapporten: alleen de zes met een dashboardtegel blijven onverwijderbaar (#1092).

Besloten door Koen op 20 september 2026. Verwijderen was geblokkeerd voor alle
negentien meegeleverde rapporten, met als reden dat ze "bij de volgende deploy
terugkomen" — en dat klopte niet: migraties draaien één keer en niets bij het
opstarten seedt rapporten. De grens verschuift van *is meegeleverd* naar *voedt
een dashboardtegel*: `dashboard_numbers` zoekt die zes op via hun `builtin_key`,
en zonder rapport toont de tegel een streepje zonder weg terug. De andere dertien
zijn van de vereniging om weg te gooien (zachte verwijdering als enige vangnet).

Wat hier bewezen wordt, in de volgorde van het issue:

1. een tegelrapport toont geen verwijderknop, een ander meegeleverd rapport wél;
   en de service weigert het tegelrapport ook zonder scherm — de knop is een
   zichtbaarheidsregel, de weigering de echte grens;
2. de beschermde lijst is **afgeleid** uit `DASHBOARD_TEGELS`: een tegel erbij in
   de test beschermt zijn rapport meteen, zonder dat er ergens iets bijgewerkt is.
   Stond er een overgeschreven lijst, dan bleef die test groen — en dan meet hij
   niets;
3. het bewerkscherm van een tegelrapport noemt de tegel, dat van een gewoon
   rapport niet;
4. een rapport van iemand anders blijft onverwijderbaar.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
`DASHBOARD_TEGELS` in de service leeggemaakt → test 1 (knop én weigering) en
test 3 vallen om; `dashboard_tile_of` vervangen door een lookup in een vaste,
overgetypte set van de zes sleutels → test 2 valt om (de toegevoegde tegel
beschermt niets), terwijl 1, 3 en 4 groen blijven — precies het verschil tussen
afleiden en overschrijven.
"""
from __future__ import annotations

import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from app.domains.reporting import service
from app.domains.reporting.api import (SavedReportError, delete_report,
                                       get_saved_report, list_saved_reports,
                                       may_delete, save_report,
                                       selection_from_dict)
from tests._reporting_seed import TENANT_A, seed

pytestmark = pytest.mark.ui_serverrendered

ADMIN = "bestuur@example.com"
ANDER = "penningmeester@example.com"
TEGEL_SLEUTEL = "dashboard_members"
GEWOON_SLEUTEL = "revenue_per_month"   # meegeleverd, voedt geen tegel


@pytest.fixture
def situatie(db_session):
    return seed(db_session)


def _login(client, db, email=ADMIN) -> str:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(email=email, is_active=True)
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
        db.flush()
    waarde = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _meegeleverd(db, sleutel: str):
    rapport = [r for r in list_saved_reports(db, tenant_id=TENANT_A, viewer=ADMIN)
               if r.builtin_key == sleutel]
    assert rapport, f"geen meegeleverd rapport met sleutel {sleutel}"
    return rapport[0]


def _verwijderroute(rapport) -> str:
    return f"/admin/rapporten/{rapport.id}/verwijderen"


# ── 1. De grens: tegelrapport vast, ander meegeleverd rapport vrij ───────────

def test_een_tegelrapport_toont_geen_verwijderknop_en_de_service_weigert(
        client, db_session, situatie):
    tegel = _meegeleverd(db_session, TEGEL_SLEUTEL)
    csrf = _login(client, db_session)

    paneel = client.get(f"/admin/rapporten/{tegel.id}")
    assert paneel.status_code == 200
    assert _verwijderroute(tegel) not in paneel.text

    assert may_delete(tegel, actor=ADMIN) is False
    with pytest.raises(SavedReportError) as fout:
        delete_report(db_session, tegel, actor=ADMIN)
    assert "Gezinnen" in str(fout.value), "de weigering noemt de tegel"

    # En via de route, voor wie de knop omzeilt: dezelfde weigering, geen 204.
    antwoord = client.post(_verwijderroute(tegel), headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code == 422
    assert "Gezinnen" in antwoord.text
    db_session.expire_all()
    assert get_saved_report(db_session, tegel.id, tenant_id=TENANT_A,
                            viewer=ADMIN) is not None


def test_een_ander_meegeleverd_rapport_is_wel_te_verwijderen(client, db_session,
                                                            situatie):
    gewoon = _meegeleverd(db_session, GEWOON_SLEUTEL)
    csrf = _login(client, db_session)

    paneel = client.get(f"/admin/rapporten/{gewoon.id}")
    assert paneel.status_code == 200
    assert _verwijderroute(gewoon) in paneel.text, "de knop hoort er nu wél te staan"
    assert may_delete(gewoon, actor=ADMIN) is True

    antwoord = client.post(_verwijderroute(gewoon), headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code == 204
    db_session.expire_all()
    assert get_saved_report(db_session, gewoon.id, tenant_id=TENANT_A,
                            viewer=ADMIN) is None


# ── 2. Afgeleid, niet overgeschreven ─────────────────────────────────────────

def test_de_bescherming_is_afgeleid_uit_de_tegellijst(client, db_session, situatie,
                                                     monkeypatch):
    """Een tegel erbij beschermt zijn rapport meteen — nergens iets bijgewerkt."""
    gewoon = _meegeleverd(db_session, GEWOON_SLEUTEL)
    assert may_delete(gewoon, actor=ADMIN) is True, "voorwaarde: vandaag vrij"

    monkeypatch.setattr(service, "DASHBOARD_TEGELS", service.DASHBOARD_TEGELS + [
        ("Omzet per maand", GEWOON_SLEUTEL, "payment_amount", "/admin/betalingen", True),
    ])

    assert may_delete(gewoon, actor=ADMIN) is False
    with pytest.raises(SavedReportError) as fout:
        delete_report(db_session, gewoon, actor=ADMIN)
    assert "Omzet per maand" in str(fout.value)

    _login(client, db_session)
    paneel = client.get(f"/admin/rapporten/{gewoon.id}")
    assert _verwijderroute(gewoon) not in paneel.text
    assert "Omzet per maand" in paneel.text, "en het paneel noemt de nieuwe tegel"


def test_het_dashboard_leest_dezelfde_lijst(client, db_session, situatie):
    """De tegellijst woont in het domein en het dashboardscherm leest ze daar:
    één lijst voor tonen én beschermen."""
    from app.ui import system_ui

    assert system_ui.DASHBOARD_TEGELS is service.DASHBOARD_TEGELS
    assert len(service.DASHBOARD_TEGELS) == 6


# ── 3. Het bewerkscherm noemt de tegel ───────────────────────────────────────

def test_het_paneel_van_een_tegelrapport_noemt_de_tegel(client, db_session, situatie):
    _login(client, db_session)
    tegel = client.get(f"/admin/rapporten/{_meegeleverd(db_session, TEGEL_SLEUTEL).id}")
    assert "voedt de dashboardtegel «Gezinnen»" in tegel.text

    gewoon = client.get(f"/admin/rapporten/{_meegeleverd(db_session, GEWOON_SLEUTEL).id}")
    assert "voedt de dashboardtegel" not in gewoon.text


# ── 4. Van iemand anders: onverwijderbaar, zoals voorheen ────────────────────

def test_een_rapport_van_iemand_anders_blijft_onverwijderbaar(client, db_session,
                                                              situatie):
    selectie = selection_from_dict({"objects": ["payment_amount"]})
    van_ander = save_report(db_session, tenant_id=TENANT_A, owner=ANDER,
                            name="Van de penningmeester", selection=selectie,
                            is_shared=True)
    csrf = _login(client, db_session)

    assert may_delete(van_ander, actor=ADMIN) is False
    paneel = client.get(f"/admin/rapporten/{van_ander.id}")
    assert paneel.status_code == 200
    assert _verwijderroute(van_ander) not in paneel.text
    antwoord = client.post(_verwijderroute(van_ander), headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code == 422
    assert "iemand anders" in antwoord.text
