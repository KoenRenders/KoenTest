"""Aanmaken opent een volledige-pagina-editor, geen modal (#627, §2.8).

Twee tegenstrijdigheden opgelost: onze eigen conventie §2.8 verbood modals voor
bewerken al, terwijl de C1-correctie er een toeliet voor aanmaken. En v1.14 had geen
enkele modal in de admin, dus er was ook geen pariteitsreden om ze te houden.

De regel eronder is niet "publiek = pagina" maar: één korte, afgeronde handeling in de
context van een lijst → modal; een vorm die je moet overzien of een object waar je in
verderwerkt → volledig scherm. De publieke activiteitinschrijving blijft daarom een
modal (#601) — die uitzondering wordt hier expliciet bewaakt.
"""
import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

# (lijstscherm, aanmaakscherm, een veld dat het aanmaakscherm hoort te tonen)
SCHERMEN = [
    ("/admin/leden", "/admin/leden/nieuw", 'name="first_name"'),
    ("/admin/activiteiten", "/admin/activiteiten/nieuw", 'name="start_date"'),
    ("/admin/formulieren", "/admin/formulieren/nieuw", 'name="title"'),
    ("/admin/paginas", "/admin/paginas/nieuw", 'name="slug"'),
    ("/admin/media", "/admin/media/nieuw", 'name="files"'),
    ("/admin/gebruikers", "/admin/gebruikers/nieuw", 'name="email"'),
    ("/admin/tenants", "/admin/tenants/nieuw", 'name="code"'),
]


def _login(client, db):
    """OPERATOR erbij: Tenants is OPERATOR-only (#581)."""
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    for rol in ("ADMIN", "OPERATOR"):
        if not any(r.role_code == rol for r in user.roles):
            db.add(UserRole(user_id=user.id, role_code=rol))
    db.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


@pytest.mark.parametrize("lijst,nieuw,veld", SCHERMEN)
def test_het_aanmaakscherm_bestaat_en_toont_zijn_velden(client, db_session, lijst, nieuw, veld):
    _login(client, db_session)
    resp = client.get(nieuw)
    assert resp.status_code == 200, f"{nieuw} → {resp.status_code}"
    assert veld in resp.text, f"{nieuw} mist {veld}"


@pytest.mark.parametrize("lijst,nieuw,veld", SCHERMEN)
def test_de_lijst_linkt_ernaartoe_en_bevat_geen_formulier(client, db_session, lijst, nieuw, veld):
    """De knop is een link; het aanmaakformulier staat niet meer in de lijst."""
    _login(client, db_session)
    html = client.get(lijst).text
    assert f'href="{nieuw}"' in html, f"{lijst} linkt niet naar {nieuw}"
    # Niet op x-data toetsen: de mobiele nav in de AdminShell gebruikt dezelfde
    # Alpine-vlag. Het bewijs is dat het aanmaakveld er niet meer staat.
    assert veld not in html, f"{lijst} bevat nog het aanmaakveld {veld}"


def test_de_publieke_inschrijving_blijft_een_modal(client, db_session):
    """De beredeneerde uitzondering (#601): één korte, afgeronde handeling in de
    context van een lijst, en de smalle popup houdt de activiteitkaart zichtbaar."""
    from tests.conftest import seed_activity_with_product

    activity, comp, _p = seed_activity_with_product(db_session, is_free=False)
    html = client.get("/activiteiten").text
    assert 'x-show="ins"' in html, "de inschrijfpopup hoort te blijven"
    assert "max-w-md" in html
