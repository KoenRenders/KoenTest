"""Drie kleine C1-afwijkingen op zichtbare plekken (#631)."""

import pytest

from app.domains.auth.api import SESSION_COOKIE, Role, User, UserRole, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == Role.OPERATOR for r in user.roles):
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

    assert html.index("<h1") < html.index("Open activiteiten"), (
        "de KPI-rij hoort ná de paginatitel te staan"
    )


def test_de_kpi_rij_staat_ook_op_leden_na_de_titel(client, db_session):
    """Het zusterscherm, als vergelijkingspunt."""
    _login(client, db_session)
    html = client.get("/admin/leden").text
    assert html.index("<h1") < html.index("Actieve gezinnen")


def test_de_verstuurknop_van_de_widget_heeft_een_aria_label():
    """Enige knop zonder leesbare tekst én zonder aria-label, op élke publieke
    pagina. Voor een schermlezer heette ze "➤".

    Op de template getoetst, niet op de gerenderde pagina: `chat_enabled` staat in CI
    uit, dus een render-assertie zou hier stilletjes overgeslagen worden en niets
    bewijzen — precies wat een skip zo verraderlijk maakt.
    """
    from pathlib import Path

    # #1075: de knop staat sinds het gedeelde bedieningsdeel in
    # `_raakje_controls.html` (compact-variant); de widget roept dat aan.
    tpl = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domains"
        / "chatbot"
        / "templates"
        / "_raakje_controls.html"
    ).read_text()
    # #570: het teken ➤ is een kit-icoon geworden — losse tekens renderen per
    # lettertype en OS anders. De regel die deze test bewaakt verandert daar niet
    # door: een knop zonder leesbare tekst heeft een aria-label nodig, of het nu een
    # glyph of een SVG is.
    knop = [r for r in tpl.splitlines() if "btn_primary" in r and 'ui.icon("send")' in r]
    assert knop, "de verstuurknop is niet gevonden"
    assert "aria_label" in knop[0], "een schermlezer leest anders niets voor"


def test_albumtitels_staan_in_ink(client, db_session):
    """Sinds #621 draagt een kaarttitel `text-ink`; merkblauw is voor koppen en
    chrome. De publieke fotoalbums waren blijven staan."""
    from pathlib import Path

    tpl = (
        Path(__file__).resolve().parents[1] / "app" / "ui" / "templates" / "_public_macros.html"
    ).read_text()  # the album card, `photo_card` (#1663)
    assert "font-semibold text-blue-700" not in tpl
    assert "font-semibold text-ink" in tpl


# `test_de_kpi_kaarten_zien_er_op_beide_schermen_hetzelfde_uit` (#636) went with
# the last tile band: Leden left it for the figures of the list-page layout
# (#1899) and Activiteiten followed (#1930). Both now draw their figures with
# `ui.figures`, which `test_list_page_gate.py` holds.
