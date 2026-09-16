"""Golf 9b (#963): rollen per werkruimte.

Koens drie besluiten van 15 september 2026: (1) OPERATOR is platformbreed
(tenant_id NULL); (2) bestaande rollen migreren naar Raak Millegem, behalve de
accounts in ``SEED_ALLE_WERKRUIMTES_EMAILS``; (3) een ADMIN kent rollen toe
binnen zijn eigen werkruimte — en dus nooit de OPERATOR-rol, want die staat
erboven. De kern: **ADMIN in werkruimte A is geen ADMIN in werkruimte B.**
"""
import pytest
pytestmark = pytest.mark.ui_serverrendered

import pytest as _pytest

from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import (SESSION_COOKIE, User, UserRole,
                                  csrf_token_for, get_user_roles,
                                  make_session_value)
from app.kernel.tenancy import (TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID,
                                current_tenant_id)


def _login(client, email=SEEDED_ADMIN_EMAIL):
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _user(db, email, *rollen):
    """Gebruiker met (role_code, tenant_id)-paren — tenant_id None is de
    platformbrede rij."""
    u = User(email=email, is_active=True)
    db.add(u); db.flush()
    for code, tenant in rollen:
        db.add(UserRole(user_id=u.id, role_code=code, tenant_id=tenant))
    db.flush()
    return u


def test_admin_in_a_is_geen_admin_in_b(db_session):
    _user(db_session, "afdeling-b@example.com",
          ("ADMIN", TENANT_VOORBEELD_ID))
    db_session.flush()

    token = current_tenant_id.set(TENANT_MILLEGEM_ID)
    try:
        assert get_user_roles(db_session, "afdeling-b@example.com") == set()
    finally:
        current_tenant_id.reset(token)
    token = current_tenant_id.set(TENANT_VOORBEELD_ID)
    try:
        assert get_user_roles(db_session, "afdeling-b@example.com") == {"ADMIN"}
    finally:
        current_tenant_id.reset(token)


def test_operator_is_platformbreed(db_session):
    _user(db_session, "platform@example.com", ("OPERATOR", None))
    for tenant in (TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID):
        token = current_tenant_id.set(tenant)
        try:
            assert "OPERATOR" in get_user_roles(db_session,
                                                "platform@example.com")
        finally:
            current_tenant_id.reset(token)


def test_de_poort_volgt_de_werkruimte_van_het_request(client, db_session):
    """Request-niveau: de padprefix kiest de werkruimte (§7), en de
    admin-poort rekent met de rollen van díe werkruimte."""
    _user(db_session, "afdeling-b@example.com", ("ADMIN", TENANT_VOORBEELD_ID))
    db_session.commit()
    _login(client, "afdeling-b@example.com")

    assert client.get("/raakvoorbeeldafdeling/admin").status_code == 200
    # Dezelfde sessie op de standaardwerkruimte (Millegem): geen rol daar.
    # (De tenant-cookie telt enkel op platform-hosts, dus /admin op de
    # testhost resolvet gewoon naar Millegem.)
    r = client.get("/admin")
    assert r.status_code != 200, "ADMIN in A mag niet zomaar B binnen"


def test_operator_wordt_nergens_buiten_het_platform_toegekend(client, db_session):
    """Aanscherping 16 sep: OPERATOR toekennen kan alléén binnen het platform
    — in een gewone werkruimte bestaat het vinkje voor niemand (ook niet voor
    een OPERATOR), en een omzeild formulier krijgt een 403."""
    doel = _user(db_session, "doelwit@example.com", ("ADMIN", TENANT_MILLEGEM_ID))
    db_session.commit()
    # De beheerder is nota bene OPERATOR (migratie 087) — en ziet het vinkje
    # in Millegem tóch niet.
    csrf = _login(client)

    lijst = client.get("/admin/gebruikers").text
    assert 'value="OPERATOR"' not in lijst

    r = client.post(f"/admin/gebruikers/{doel.id}",
                    data={"is_active": "on", "role_codes": ["ADMIN", "OPERATOR"]},
                    headers={"X-CSRF-Token": csrf})
    assert "alleen binnen het platform" in r.text
    db_session.expire_all()
    assert (db_session.query(UserRole)
            .filter(UserRole.user_id == doel.id,
                    UserRole.role_code == "OPERATOR").count()) == 0


PLATFORM_HOST = "platform.example.test"


@_pytest.fixture
def platform_host(monkeypatch):
    """`PLATFORM_HOSTS` zoals op de server, plus een schone lookup-cache —
    zelfde patroon als test_platform_tenant.py."""
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "platform_hosts", PLATFORM_HOST)
    invalidate_tenant_codes()
    yield PLATFORM_HOST
    invalidate_tenant_codes()


def test_platform_beheert_rollen_per_werkruimte(client, db_session, platform_host):
    """Aanscherping 16 sep: op het platform toont de gebruikerskaart een rij
    vinkjes PER werkruimte — zo maakt een OPERATOR de eerste gebruikers van
    een nieuwe tenant aan — en dáár staat ook het OPERATOR-vinkje."""
    doel = _user(db_session, "doelwit@example.com", ("ADMIN", TENANT_MILLEGEM_ID))
    db_session.commit()
    csrf = _login(client)  # beheerder = OPERATOR (087)

    lijst = client.get("/admin/gebruikers",
                       headers={"host": platform_host}).text
    assert f'name="rollen_{TENANT_VOORBEELD_ID}"' in lijst
    assert 'name="operator"' in lijst and 'value="OPERATOR"' not in lijst

    # Rollen voor twee werkruimtes tegelijk + OPERATOR platformbreed.
    r = client.post(f"/admin/gebruikers/{doel.id}",
                    data={"is_active": "on",
                          f"rollen_{TENANT_MILLEGEM_ID}": ["ADMIN", "FINANCE"],
                          f"rollen_{TENANT_VOORBEELD_ID}": ["ADMIN"],
                          "operator": "1"},
                    headers={"X-CSRF-Token": csrf, "host": platform_host})
    assert r.status_code == 200
    db_session.expire_all()
    paren = {(rij.role_code, rij.tenant_id) for rij in
             db_session.query(UserRole).filter(UserRole.user_id == doel.id)}
    assert paren == {("ADMIN", TENANT_MILLEGEM_ID),
                     ("FINANCE", TENANT_MILLEGEM_ID),
                     ("ADMIN", TENANT_VOORBEELD_ID),
                     ("OPERATOR", None)}


def test_eerste_gebruiker_van_een_nieuwe_tenant_via_het_platform(client, db_session, platform_host):
    """Het doel achter de matrix: vanaf het platform een gloednieuwe
    gebruiker zijn eerste rol in een afdeling geven — en die kan daar dan
    ook echt binnen, maar nergens anders."""
    csrf = _login(client)
    r = client.post("/admin/gebruikers",
                    data={"email": "nieuwe-tenantadmin@example.com",
                          f"rollen_{TENANT_VOORBEELD_ID}": ["ADMIN"]},
                    headers={"X-CSRF-Token": csrf, "host": platform_host})
    assert r.status_code in (200, 204)

    _login(client, "nieuwe-tenantadmin@example.com")
    assert client.get("/raakvoorbeeldafdeling/admin").status_code == 200
    assert client.get("/admin").status_code != 200  # Millegem blijft dicht


def test_platform_admin_zonder_operator_kan_operator_niet_zetten(client, db_session, platform_host):
    """Ook op het platform blijft de OPERATOR-wissel OPERATOR-only: een
    platform-ADMIN die het formulier omzeilt krijgt de 403."""
    doel = _user(db_session, "doelwit@example.com", ("ADMIN", TENANT_MILLEGEM_ID))
    from app.domains.mdm.api import platform_tenant_id

    pid = platform_tenant_id(db_session)
    _user(db_session, "platform-admin@example.com", ("ADMIN", pid))
    db_session.commit()
    csrf = _login(client, "platform-admin@example.com")

    assert 'name="operator"' not in client.get(
        "/admin/gebruikers", headers={"host": platform_host}).text
    r = client.post(f"/admin/gebruikers/{doel.id}",
                    data={"is_active": "on", "operator": "1",
                          f"rollen_{TENANT_MILLEGEM_ID}": ["ADMIN"]},
                    headers={"X-CSRF-Token": csrf, "host": platform_host})
    assert "Alleen een OPERATOR" in r.text
    db_session.expire_all()
    assert (db_session.query(UserRole)
            .filter(UserRole.user_id == doel.id,
                    UserRole.role_code == "OPERATOR").count()) == 0


def test_rollen_vervangen_raakt_andere_werkruimte_niet(client, db_session):
    """Besluit 3: de rollenlijst in gebruikersbeheer vervangt alleen de rijen
    van de actieve werkruimte; wat het doelwit elders heeft, blijft staan."""
    doel = _user(db_session, "doelwit@example.com",
                 ("FINANCE", TENANT_MILLEGEM_ID),
                 ("ADMIN", TENANT_VOORBEELD_ID))
    db_session.commit()
    csrf = _login(client)

    r = client.post(f"/admin/gebruikers/{doel.id}",
                    data={"is_active": "on", "role_codes": ["ADMIN"]},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    db_session.expire_all()
    paren = {(r.role_code, r.tenant_id) for r in
             db_session.query(UserRole).filter(UserRole.user_id == doel.id)}
    assert paren == {("ADMIN", TENANT_MILLEGEM_ID),
                     ("ADMIN", TENANT_VOORBEELD_ID)}


def test_lijst_toont_rollen_van_de_actieve_werkruimte(client, db_session):
    """Het rolvinkje op de kaart toont de werkruimte waarin je kijkt — een
    ADMIN-vinkje uit een andere werkruimte zou hier liegen."""
    doel = _user(db_session, "doelwit@example.com",
                 ("ADMIN", TENANT_VOORBEELD_ID))
    db_session.commit()
    _login(client)
    html = client.get("/admin/gebruikers?q=doelwit").text
    kaart = html.split("doelwit@example.com")[1]
    assert 'value="ADMIN" checked' not in kaart and 'value="ADMIN"  checked' not in kaart


def test_accountmenu_toont_wisselen_alleen_bij_meerdere_werkruimtes(client, db_session):
    """Het menu-fragment (lui geladen door de schil): één werkruimte → geen
    "Werkruimte wisselen"; een platformbrede rol → alle werkruimtes, dus wél."""
    db_session.commit()
    _login(client, "bestuurslid@example.com")  # ADMIN in één werkruimte (126)
    alleen = client.get("/admin/accountmenu").text
    assert "Mijn profiel" in alleen and "Werkruimte wisselen" not in alleen

    _login(client)  # beheerder: OPERATOR (087) → platformbreed → alles
    menu = client.get("/admin/accountmenu").text
    assert "Werkruimte wisselen" in menu


def test_werkruimte_wisselen_linkt_via_de_padprefix(client, db_session):
    _user(db_session, "twee@example.com",
          ("ADMIN", TENANT_MILLEGEM_ID), ("ADMIN", TENANT_VOORBEELD_ID))
    db_session.commit()
    _login(client, "twee@example.com")
    html = client.get("/admin/werkruimte-wisselen").text

    assert 'href="/raakvoorbeeldafdeling/admin"' in html
    assert 'href="/raakmillegem/admin"' in html
    assert "Huidige" in html  # de actieve werkruimte gemarkeerd, niet verstopt
    # En de prefix-link komt ook echt in de andere werkruimte uit.
    assert client.get("/raakvoorbeeldafdeling/admin").status_code == 200
