"""Drie kleine C1-afwijkingen op zichtbare plekken (#631)."""
import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "OPERATOR" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def test_de_kpi_rij_staat_na_de_titel(client, db_session):
    """C1-volgorde: titel → duidingsregel → KPI → actie → zoek → filters. De
    kengetallen stonden bóven de H1, wat ook het commentaar in ditzelfde bestand
    tegensprak. `leden.html` deed het wél goed."""
    seed_activity_with_product(db_session)
    _login(client, db_session)
    html = client.get("/admin/activiteiten").text

    assert html.index("<h1") < html.index("Open inschrijvingen"), \
        "de KPI-rij hoort ná de paginatitel te staan"


def test_de_kpi_rij_staat_ook_op_leden_na_de_titel(client, db_session):
    """Het zusterscherm, als vergelijkingspunt."""
    _login(client, db_session)
    html = client.get("/admin/leden").text
    assert html.index("<h1") < html.index("Actieve leden")


def test_de_verstuurknop_van_de_widget_heeft_een_aria_label(client, db_session):
    """Enige knop zonder leesbare tekst én zonder aria-label, op élke publieke
    pagina. Voor een schermlezer heette ze "➤"."""
    html = client.get("/").text
    if "➤" not in html:
        pytest.skip("de chatwidget staat niet aan op deze omgeving")
    knop = [r for r in html.splitlines() if "➤" in r][0]
    assert "aria-label" in knop


def test_albumtitels_staan_in_ink(client, db_session):
    """Sinds #621 draagt een kaarttitel `text-ink`; merkblauw is voor koppen en
    chrome. De publieke fotoalbums waren blijven staan."""
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1] / "app" / "domains" / "media"
           / "templates" / "fotos.html").read_text()
    assert 'font-semibold text-blue-700' not in tpl
    assert 'font-semibold text-ink' in tpl
