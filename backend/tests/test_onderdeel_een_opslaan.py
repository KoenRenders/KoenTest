"""#654/#655 — het onderdeel bewaart met één "Opslaan" en toont zijn bijlage.

§2.12 verbood al een eigen submit-knop bij het uploadveld, maar dat was in #623
alleen op de activiteit toegepast. Het onderdeel hield twee vormen naar twee
endpoints: velden naar `…/onderdelen/{id}` en de bijlage naar `…/info`. Op het
scherm stonden dus twee "Opslaan"-knoppen onder elkaar, en één wijziging kostte
twee handelingen.

#655 trekt de leeszijde gelijk: de activiteit had een leeslink naar haar affiche,
het onderdeel geen naar zijn info-bijlage.
"""
import io

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
       b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
       b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


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
    start = html.index(f'hx-post="/admin/activiteiten/{activity_id}/onderdelen/{component_id}"')
    return html[start:html.index("</form>", start)]


def _kaart(html: str, activity_id: int, component_id: int) -> str:
    """De hele onderdeelkaart, tot de doel-div die haar afsluit (#650)."""
    start = html.index(f'hx-post="/admin/activiteiten/{activity_id}/onderdelen/{component_id}"')
    return html[start:html.index(f'id="aa-insch-{component_id}"', start)]


def test_een_onderdeel_in_bewerkmodus_toont_precies_een_opslaan(client, db_session):
    """De kern van #654, en het enige wat je op het scherm ziet."""
    activity, component, _p = seed_activity_with_product(db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    vorm = _bewerkvorm(html, activity.id, component.id)
    assert vorm.count(">Opslaan<") == 1, (
        f"de bewerkvorm van het onderdeel toont {vorm.count('>Opslaan<')} "
        "Opslaan-knoppen (#654)")

    # En het uploadblok zit erin, niet in een tweede vorm ernaast.
    assert 'name="file"' in vorm, "het uploadblok staat niet in de gedeelde vorm"
    assert "multipart/form-data" in vorm, "de vorm kan geen bestand versturen"
    kaart = _kaart(html, activity.id, component.id)
    assert f'hx-post="/admin/activiteiten/{activity.id}/onderdelen/{component.id}/info"' \
        not in kaart, "er staat nog een tweede vorm naar /info op de kaart (#654)"


def test_velden_en_bestand_gaan_in_een_post(client, db_session):
    """Eén POST met gewijzigde velden én een bestand — beide toegepast."""
    activity, component, _p = seed_activity_with_product(db_session)
    csrf = _login(client)

    r = client.post(
        f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}",
        data={"name": "Gewijzigd onderdeel", "max_participants": "7"},
        files={"file": ("info.png", io.BytesIO(PNG), "image/png")},
        headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text[:300]

    db_session.expire_all()
    from app.domains.activities.api import ActivitySubRegistration
    vers = db_session.get(ActivitySubRegistration, component.id)
    assert vers.name == "Gewijzigd onderdeel"
    assert vers.max_participants == 7
    assert vers.info_asset_url, "de bijlage is niet bewaard bij dezelfde POST (#654)"


def test_opslaan_zonder_bestand_laat_de_bijlage_staan(client, db_session):
    """De valkuil van één gedeelde vorm: een lege bestandskiezer mag de bestaande
    bijlage niet wissen."""
    activity, component, _p = seed_activity_with_product(db_session)
    csrf = _login(client)
    client.post(f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}",
                data={"name": component.name},
                files={"file": ("info.png", io.BytesIO(PNG), "image/png")},
                headers={"X-CSRF-Token": csrf})
    db_session.expire_all()
    from app.domains.activities.api import ActivitySubRegistration
    voor = db_session.get(ActivitySubRegistration, component.id).info_asset_url
    assert voor

    r = client.post(f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}",
                    data={"name": "Alleen de naam"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    db_session.expire_all()
    vers = db_session.get(ActivitySubRegistration, component.id)
    assert vers.name == "Alleen de naam"
    assert vers.info_asset_url == voor, "de bijlage is verdwenen bij een gewone opslag"


def test_de_verwijderknop_blijft_een_aparte_actie(client, db_session):
    """§2.12: verwijderen is geen bewaarhandeling en hoort niet onder Opslaan."""
    activity, component, _p = seed_activity_with_product(db_session)
    csrf = _login(client)
    client.post(f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}",
                data={"name": component.name},
                files={"file": ("info.png", io.BytesIO(PNG), "image/png")},
                headers={"X-CSRF-Token": csrf})

    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert f"/onderdelen/{component.id}/info/verwijderen" in html

    r = client.post(
        f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}/info/verwijderen",
        headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    db_session.expire_all()
    from app.domains.activities.api import ActivitySubRegistration
    assert not db_session.get(ActivitySubRegistration, component.id).info_asset_url


def test_de_leeslink_naar_de_info_bijlage(client, db_session):
    """#655: mét bijlage staat het label twee keer — één leeslink, één in het
    uploadblok — en de leeslink hangt aan de leesmodus."""
    activity, component, _p = seed_activity_with_product(db_session)
    csrf = _login(client)
    client.post(f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}",
                data={"name": component.name},
                files={"file": ("info.png", io.BytesIO(PNG), "image/png")},
                headers={"X-CSRF-Token": csrf})

    html = client.get(f"/admin/activiteiten/{activity.id}").text
    regels = [r.strip() for r in html.splitlines()
              if "Huidige info-bijlage bekijken" in r]
    assert len(regels) == 2, (
        f"verwacht één leeslink en één in het uploadblok, kreeg er {len(regels)}")
    assert sum('x-show="!edit"' in r for r in regels) == 1, (
        "de leeslink hangt niet aan de leesmodus:\n  " + "\n  ".join(regels))


def test_zonder_bijlage_geen_leeslink(client, db_session):
    """Het geval dat een {% if %} zonder guard stukmaakt."""
    activity, _component, _p = seed_activity_with_product(db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "Huidige info-bijlage bekijken" not in html
