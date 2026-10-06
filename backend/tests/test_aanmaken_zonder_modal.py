"""Aanmaken opent een volledige-pagina-editor, geen modal (#627, §2.8).

Twee tegenstrijdigheden opgelost: onze eigen conventie §2.8 verbood modals voor
bewerken al, terwijl de C1-correctie er een toeliet voor aanmaken. En v1.14 had geen
enkele modal in de admin, dus er was ook geen pariteitsreden om ze te houden.

De regel eronder is niet "publiek = pagina" maar: één korte, afgeronde handeling in de
context van een lijst → modal; een vorm die je moet overzien of een object waar je in
verderwerkt → volledig scherm. De publieke activiteitinschrijving was daarom een
modal (#601).

Since CR-14 phase 1 (#1332, B4.1) it is a page too: contact, products, the
component's questions and the payment choice are a page's worth, and a page has a
URL and a back button. The exception is gone; the test below guards the new rule.
"""

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

# (lijstscherm, aanmaakscherm, een veld-id dat ALLEEN op het aanmaakscherm staat)
#
# Bewust een `id=` en geen `name=`: een `name="email"` staat ook op de bewerkrij van
# elke gebruiker, en dan toetst de test niets. De id's zijn uniek per formulier.
SCHERMEN = [
    # #1110: het aanmaakscherm is één formulier met de gedeelde veldenset, dus
    # het eerste veld heet m0_first_name.
    ("/admin/leden", "/admin/leden/nieuw", 'id="m0_first_name"'),
    # #1649: the create screen is the activity's fiche, empty; its first date row.
    ("/admin/activiteiten", "/admin/activiteiten/nieuw", 'id="d-n1-start_date"'),
    ("/admin/formulieren", "/admin/formulieren/nieuw", 'id="f-title"'),
    ("/admin/paginas", "/admin/paginas/nieuw", 'id="slug"'),
    ("/admin/media", "/admin/media/nieuw", 'id="me-files"'),
    ("/admin/gebruikers", "/admin/gebruikers/nieuw", 'id="gu-email"'),
    ("/admin/tenants", "/admin/tenants/nieuw", 'id="t-code"'),
]


def _login(client, db):
    """OPERATOR erbij: Tenants is OPERATOR-only (#581)."""
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    for rol in ("ADMIN", "OPERATOR"):
        if not any(r.role_code.value == rol for r in user.roles):
            db.add(UserRole(user_id=user.id, role_code=rol))
    db.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


@pytest.mark.parametrize("lijst,nieuw,veld", SCHERMEN)
def test_het_aanmaakscherm_bestaat_en_toont_zijn_velden(
    client, workspace_host, db_session, lijst, nieuw, veld
):
    _login(client, db_session)
    resp = client.get(nieuw, headers=workspace_host(nieuw))
    assert resp.status_code == 200, f"{nieuw} → {resp.status_code}"
    assert veld in resp.text, f"{nieuw} mist {veld}"


@pytest.mark.parametrize("lijst,nieuw,veld", SCHERMEN)
def test_de_lijst_linkt_ernaartoe_en_bevat_geen_formulier(
    client, workspace_host, db_session, lijst, nieuw, veld
):
    """De knop is een link; het aanmaakformulier staat niet meer in de lijst."""
    _login(client, db_session)
    html = client.get(lijst, headers=workspace_host(lijst)).text
    assert f'href="{nieuw}' in html, f"{lijst} linkt niet naar {nieuw}"
    # Niet op x-data toetsen: de mobiele nav in de AdminShell gebruikt dezelfde
    # Alpine-vlag. Het bewijs is dat het aanmaakveld er niet meer staat.
    assert veld not in html, f"{lijst} bevat nog het aanmaakveld {veld}"


def test_the_public_registration_is_a_page(client, db_session):
    """CR-14 phase 1 (B4.1): the card links to the registration page; no popup."""
    from tests.conftest import seed_activity_with_product

    activity, comp, _p = seed_activity_with_product(db_session, is_free=False)
    html = client.get("/activiteiten").text
    assert f'href="/activiteiten/{activity.id}/inschrijven/{comp.id}"' in html
    assert 'x-show="ins"' not in html, "the registration popup is back"
    page = client.get(f"/activiteiten/{activity.id}/inschrijven/{comp.id}").text
    assert "<main" in page and 'id="inschrijf-pagina"' in page
