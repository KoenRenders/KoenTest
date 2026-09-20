"""Een sponsorlogo kiest zelf of het in de footer verschijnt (#1057).

Koen voegde de gemeente toe als tweede sponsorlogo en het stond meteen onder élke
publieke pagina. Geen fout in de code: `kind="sponsor"` werd door twee dingen
gelezen — de footerbalk en de logokiezer van de Design Studio — en er was geen
manier om die twee te scheiden.

`show_in_footer` scheidt ze. De footer luistert; de Design Studio blijft élk actief
sponsorlogo aanbieden, met opzet: een logo dat niet in de footer hoort, hoort
daarom nog niet van de affiche geweerd. `is_active` blijft betekenen "nergens" —
die vlag zit erboven, niet ernaast, en de tweede test houdt dat verschil zichtbaar
in de tests in plaats van alleen in een commentaar.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):

- de `show_in_footer`-filter uit de footerquery (`app/ui/__init__.py`) → *uit de
  footer* valt om: de footer toont er dan twee;
- de Design Studio óók op `show_in_footer` laten filteren → diezelfde test valt om
  aan de andere kant, want dan biedt ze er nog maar één aan;
- `is_active` uit de Design Studio-filter → *niet actief betekent nergens* valt om;
- de kolomstandaard op `False` → *standaard in de footer* valt om;
- het `kind == "sponsor"`-omhulsel om het vinkje weg → *bij een andere soort* valt om;
- `show_in_footer` uit de lijst van velden die `update_media` overneemt → *de
  schakelaar bewaart* valt om.
"""
from io import BytesIO

import pytest
from PIL import Image

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.media.api import MediaAsset
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _png(px=40) -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (px, px), (0, 93, 41, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _logo(db, titel, *, actief=True, in_footer=True):
    beeld = _png()
    asset = MediaAsset(kind="sponsor", title=titel, data=beeld,
                       content_type="image/png", thumbnail=beeld,
                       thumb_content_type="image/png", width=40, height=40,
                       byte_size=len(beeld), sort_order=0, is_active=actief,
                       show_in_footer=in_footer)
    db.add(asset)
    db.flush()
    return asset


def _footer_logos(client, db) -> list[int]:
    """De id's van de logo's die de footer werkelijk rendert."""
    from app.ui import site_context

    ids = [s.id for s in site_context(db)["sponsors"]]
    # De gerenderde pagina toont dezelfde: het sjabloon leest `sponsors`, en dat
    # laatste is wat hierboven gemeten wordt. Eén controle op de HTML erbij, zodat
    # deze test niet alleen de query maar ook de weergave raakt.
    html = client.get("/").text
    for asset_id in ids:
        assert f"/api/v1/media/{asset_id}" in html
    return ids


def _studio_logos(db) -> list[int]:
    from app.domains.designstudio.api import sponsor_options

    return [int(m["id"]) for m in sponsor_options(db)]


def test_uit_de_footer_maar_nog_altijd_op_de_affiche(client, db_session):
    """Het hele issue in één test (#1057, toets 1).

    Twee sponsorlogo's, bij één staat de schakelaar uit. De footer toont er één,
    de Design Studio biedt er twee aan.
    """
    blijft = _logo(db_session, "Sponsor in de voet", in_footer=True)
    alleen_affiche = _logo(db_session, "Gemeente", in_footer=False)

    assert _footer_logos(client, db_session) == [blijft.id]
    assert sorted(_studio_logos(db_session)) == sorted([blijft.id, alleen_affiche.id])


def test_niet_actief_betekent_nergens(client, db_session):
    """Toets 2: `is_active` blijft de bovenliggende vlag.

    Uit betekent nergens — ook niet in de Design Studio, waar de nieuwe schakelaar
    juist géén invloed heeft.
    """
    _logo(db_session, "Gestopte sponsor", actief=False, in_footer=True)

    assert _footer_logos(client, db_session) == []
    assert _studio_logos(db_session) == []


def test_een_nieuw_logo_staat_standaard_in_de_footer(client, db_session):
    """Toets 3: de standaard is aan, zodat een gewone sponsor niets extra vraagt.

    Gemeten via de ECHTE uploadweg, niet via een handgemaakt rij-object: de
    standaard moet gelden voor wat het scherm aanmaakt.
    """
    csrf = _login(client)

    antwoord = client.post("/admin/media",
                           files={"files": ("logo.png", _png(), "image/png")},
                           data={"kind": "sponsor", "title": "Verse sponsor"},
                           headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code in (200, 204), antwoord.text[:300]

    db_session.expire_all()
    asset = db_session.query(MediaAsset).filter(
        MediaAsset.title == "Verse sponsor").one()
    assert asset.show_in_footer is True
    assert asset.id in _footer_logos(client, db_session)


def test_de_schakelaar_staat_op_het_scherm_en_bewaart(client, db_session):
    """Naast het bestaande *Actief*-vinkje, en alleen bij een sponsorlogo."""
    logo = _logo(db_session, "Sponsor met vinkje")
    csrf = _login(client)

    lijst = client.get("/admin/media?kind=sponsor").text
    assert 'name="show_in_footer"' in lijst
    assert "In de footer" in lijst

    antwoord = client.post(f"/admin/media/{logo.id}",
                           data={"kind": "sponsor", "title": logo.title,
                                 "link_url": "", "is_active": "1", "q": ""},
                           headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code == 200, antwoord.text[:300]

    db_session.expire_all()
    assert db_session.get(MediaAsset, logo.id).show_in_footer is False


def test_bij_een_andere_soort_staat_de_schakelaar_er_niet(client, db_session):
    """De kolom heeft alleen betekenis bij `kind="sponsor"`.

    Een vinkje bij een activiteitenfoto zou een keuze suggereren die nergens
    gelezen wordt. Gemeten op het scherm van die andere soort.
    """
    from app.domains.activities.api import Activity

    a = Activity(name="Fotoalbum", location="Miloheem")
    db_session.add(a)
    db_session.flush()
    beeld = _png()
    db_session.add(MediaAsset(kind="activity_photo", activity_id=a.id,
                              title="Een foto", data=beeld,
                              content_type="image/png", thumbnail=beeld,
                              thumb_content_type="image/png", width=40, height=40,
                              byte_size=len(beeld), sort_order=0, is_active=True))
    db_session.flush()
    _login(client)

    lijst = client.get(
        f"/admin/media?kind=activity_photo&activity_id={a.id}").text

    assert "Een foto" in lijst, "de foto staat niet op dit scherm"
    assert 'name="show_in_footer"' not in lijst
