"""#715 — de info-bijlage hoort al bij het aanmaken van een onderdeel te kunnen.

Tot deze wijziging toonde het toevoegformulier drie URL-velden en geen
uploadveld: de bijlage kon pas ná het aanmaken, via "Bewerken". Het scherm wekte
zo de indruk dat een externe URL de enige manier was om info aan een onderdeel te
hangen.

Waarom hier op het RESULTAAT getoetst wordt en niet op de statuscode: de
regressie is stil. Haal je `hx-encoding` uit de vorm of `file` uit de handler,
dan blijft de POST een 200 geven en wordt het onderdeel netjes aangemaakt — enkel
zonder bijlage. Precies de valkuil van #683/#680.

Kapotgemaakt om te controleren dat deze tests rood kunnen:
  * `hx-encoding` uit de toevoegvorm gehaald → test_toevoegvorm_kan_een_bestand_versturen
    faalt op "de toevoegvorm kan geen bestand versturen";
  * `file`-parameter uit `onderdeel_toevoegen` weggelaten → test_toevoegen_met_bestand
    faalt op de ontbrekende `info_asset_url`;
  * label teruggezet op "Info-URL" → test_het_url_label_zegt_dat_het_extern_is faalt.
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


def _toevoegvorm(html: str, activity_id: int) -> str:
    """De vorm die een nieuw onderdeel aanmaakt, tot haar eigen </form>.

    Ankeren op de hx-post zonder component-id: de bewerkvormen posten naar
    `…/onderdelen/{id}`, deze naar `…/onderdelen"` — het aanhalingsteken houdt de
    twee uit elkaar.
    """
    anker = html.index(f'hx-post="/admin/activiteiten/{activity_id}/onderdelen"')
    start = html.rindex("<form", 0, anker)
    return html[start:html.index("</form>", start)]


def _nieuw_onderdeel(db_session, activity_id: int, naam: str):
    from app.domains.activities.api import ActivitySubRegistration

    db_session.expire_all()
    return (db_session.query(ActivitySubRegistration)
            .filter(ActivitySubRegistration.activity_id == activity_id,
                    ActivitySubRegistration.name == naam)
            .one())


def test_toevoegvorm_kan_een_bestand_versturen(client, db_session):
    """De kern van #715 op het scherm: uploadveld én een vorm die het meestuurt."""
    activity, _c, _p = seed_activity_with_product(db_session)
    _login(client)
    vorm = _toevoegvorm(client.get(f"/admin/activiteiten/{activity.id}").text,
                        activity.id)

    assert 'name="file"' in vorm, "de toevoegvorm heeft geen uploadveld (#715)"
    assert "multipart/form-data" in vorm, (
        "de toevoegvorm kan geen bestand versturen — zonder enctype/hx-encoding "
        "stuurt htmx het bestand niet mee en verdwijnt het stil")


def test_toevoegen_met_bestand(client, db_session):
    """Eén POST maakt het onderdeel én hangt de bijlage eraan."""
    activity, _c, _p = seed_activity_with_product(db_session)
    csrf = _login(client)

    r = client.post(
        f"/admin/activiteiten/{activity.id}/onderdelen",
        data={"name": "Met bijlage", "max_participants": "12"},
        files={"file": ("info.png", io.BytesIO(PNG), "image/png")},
        headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text[:300]

    nieuw = _nieuw_onderdeel(db_session, activity.id, "Met bijlage")
    assert nieuw.max_participants == 12, "de gewone velden zijn niet bewaard"
    assert nieuw.info_asset_url, (
        "de bijlage is niet bewaard bij het aanmaken (#715) — de POST slaagde wel")


def test_toevoegen_zonder_bestand_blijft_werken(client, db_session):
    """De bestandskiezer is optioneel; een lege mag niets stukmaken."""
    activity, _c, _p = seed_activity_with_product(db_session)
    csrf = _login(client)

    r = client.post(f"/admin/activiteiten/{activity.id}/onderdelen",
                    data={"name": "Zonder bijlage"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text[:300]

    nieuw = _nieuw_onderdeel(db_session, activity.id, "Zonder bijlage")
    assert not nieuw.info_asset_url


def test_een_geweigerd_bestand_toont_een_fout(client, db_session):
    """htmx swapt niet op een 4xx, dus de route vangt de fout en toont ze —
    zelfde afhandeling als bij bewerken."""
    activity, _c, _p = seed_activity_with_product(db_session)
    csrf = _login(client)

    r = client.post(f"/admin/activiteiten/{activity.id}/onderdelen",
                    data={"name": "Fout bestand"},
                    files={"file": ("foto.heic", b"nonsense", "image/heic")},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert "bestandstype" in r.text.lower(), (
        "een geweigerd bestand mislukt stil bij het aanmaken")


def test_het_url_label_zegt_dat_het_extern_is(client, db_session):
    """Naast een uploadveld dat binnen het portaal blijft, moet de naam van het
    URL-veld verraden dat het buiten het portaal wijst. "Info-URL" pal naast
    "Info-bijlage" doet dat niet."""
    activity, component, _p = seed_activity_with_product(db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text

    assert ">Externe info-URL<" in html, "het label is niet aangepast (#715)"
    # Toevoegen én bewerken: één per onderdeel plus die van de toevoegvorm.
    assert html.count(">Externe info-URL<") == len(activity.sub_registrations) + 1
    assert ">Info-URL<" not in html, (
        "er staat nog een oud, onbepaald 'Info-URL'-label op het scherm")
    assert component.id  # de kaart bestaat; het label hierboven is dus geteld
