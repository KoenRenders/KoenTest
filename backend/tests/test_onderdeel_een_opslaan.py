"""#654/#655 — het onderdeel bewaart met één "Opslaan" en toont zijn bijlage.

§2.12 verbood al een eigen submit-knop bij het uploadveld, maar dat was in #623
alleen op de activiteit toegepast. Het onderdeel hield twee vormen naar twee
endpoints: velden naar `…/onderdelen/{id}` en de bijlage naar `…/info`. Op het
scherm stonden dus twee "Opslaan"-knoppen onder elkaar, en één wijziging kostte
twee handelingen.

#655 trekt de leeszijde gelijk: de activiteit had een leeslink naar haar affiche,
het onderdeel geen naar zijn info-bijlage.
"""

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _bewerkvorm(html: str, activity_id: int, component_id: int) -> str:
    """De bewerkvorm van dít onderdeel, tot haar eigen </form>.

    Twee eerdere pogingen waren te grof. Op de naam zoeken landde op "Nieuw
    onderdeel" in de toevoegvorm bovenaan; tot de doel-div van #650 lopen nam het
    productpaneel mee, en elk product hééft een eigen Opslaan — terecht. De
    invariant gaat over de vorm van het onderdeel zelf.
    """
    anker = html.index(f'hx-post="/admin/activiteiten/{activity_id}/onderdelen/{component_id}"')
    # Terug naar de <form>-tag zelf: enctype en hx-encoding staan vóór hx-post.
    start = html.rindex("<form", 0, anker)
    return html[start : html.index("</form>", start)]


def _kaart(html: str, activity_id: int, component_id: int) -> str:
    """De onderdeelkaart. Het oude aa-insch-anker verdween in ronde 2 van
    golf 8; deze seeds hebben één onderdeel, dus tot het einde lezen volstaat
    voor de /info-vorm-controle."""
    start = html.index(f'hx-post="/admin/activiteiten/{activity_id}/onderdelen/{component_id}"')
    return html[start:]


def test_zonder_bijlage_geen_leeslink(client, db_session):
    """Het geval dat een {% if %} zonder guard stukmaakt."""
    activity, _component, _p = seed_activity_with_product(db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "Huidige info-bijlage bekijken" not in html
