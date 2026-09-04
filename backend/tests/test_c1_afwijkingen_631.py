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


def test_de_verstuurknop_van_de_widget_heeft_een_aria_label():
    """Enige knop zonder leesbare tekst én zonder aria-label, op élke publieke
    pagina. Voor een schermlezer heette ze "➤".

    Op de template getoetst, niet op de gerenderde pagina: `chat_enabled` staat in CI
    uit, dus een render-assertie zou hier stilletjes overgeslagen worden en niets
    bewijzen — precies wat een skip zo verraderlijk maakt.
    """
    from pathlib import Path

    tpl = (Path(__file__).resolve().parents[1] / "app" / "domains" / "chatbot"
           / "templates" / "_raakje_widget.html").read_text()
    knop = [r for r in tpl.splitlines() if "➤" in r and "btn_" in r]
    assert knop, "de verstuurknop is niet gevonden"
    assert "aria_label" in knop[0], "een schermlezer leest anders het teken voor"


def test_albumtitels_staan_in_ink(client, db_session):
    """Sinds #621 draagt een kaarttitel `text-ink`; merkblauw is voor koppen en
    chrome. De publieke fotoalbums waren blijven staan."""
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1] / "app" / "domains" / "media"
           / "templates" / "fotos.html").read_text()
    assert 'font-semibold text-blue-700' not in tpl
    assert 'font-semibold text-ink' in tpl


def test_de_kpi_kaarten_zien_er_op_beide_schermen_hetzelfde_uit(client, db_session):
    """#636: twee zusterschermen die hetzelfde soort informatie tonen hoorden er
    hetzelfde uit te zien. Activiteiten had een getinte eerste kaart en zette het
    cijfer boven het label; Leden stond sinds #611 al op de mock."""
    seed_activity_with_product(db_session)
    _login(client, db_session)

    for pad, label in (("/admin/activiteiten", "Open inschrijvingen"),
                       ("/admin/leden", "Actieve leden")):
        html = client.get(pad).text
        kaart = html[html.index(label) - 400:html.index(label) + 200]
        assert "bg-white border border-line" in kaart, f"{pad}: KPI-kaart is niet wit"
        # Label bóven het cijfer: het label staat eerder in de HTML dan de waarde.
        na_label = html[html.index(label):]
        assert "text-3xl" in na_label[:300], f"{pad}: het cijfer hoort ná het label"
