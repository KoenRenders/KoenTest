"""#707 + #708 — het linkveld hoort bij een sponsor, en media opent op foto's.

**#707.** `link_url` is de doorklik van een sponsorlogo en wordt op precies één plek
gerenderd: de sponsorstrook. Bij een activiteitenfoto werd de waarde bewaard en
nooit gebruikt — dan is het geen instelling maar rommel die later iemand verwart.

Tweede helft, en die weegt zwaarder: er stond **geen enkele controle** op de waarde,
niet bij het uploaden, niet bij het bijwerken en niet in de JSON-route. Ze gaat
rechtstreeks in een `href` op een publieke pagina, dus een `javascript:`-URL was
klikbaar. Alleen een beheerder kan het zetten, dus de ernst is beperkt — maar er was
nooit over nagedacht.

**De regel staat in de service, niet in het scherm.** Er zijn twee ingangen, en een
regel in het scherm wordt langs de andere omzeild. Dat is de derde test hieronder.

**#708.** "Sponsor" stond op drie plaatsen als standaard. Alle drie moeten mee: "+
Uploaden" geeft de huidige filterstand door in de URL, dus alleen het uploadscherm
wijzigen laat de lijst hem meteen overschrijven — en dan lijkt de wijziging niet te
werken.
"""
import io

import pytest

from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_agnostisch


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (30, 30), (10, 90, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _activiteit(db, naam="Zomerfeest"):
    from datetime import date, timedelta

    from app.domains.activities.api import Activity, ActivityDate

    a = Activity(name=naam)
    db.add(a)
    db.flush()
    db.add(ActivityDate(activity_id=a.id, start_date=date.today() + timedelta(days=5)))
    db.flush()
    return a


def _upload(client, csrf, **velden):
    data = {"kind": "sponsor", "q": "", "filter_activity_id": ""}
    data.update({k: str(v) for k, v in velden.items() if v is not None})
    return client.post("/admin/media", data=data,
                       files={"files": ("x.png", _png(), "image/png")},
                       headers={"X-CSRF-Token": csrf})


def _asset(db, titel):
    from app.domains.media.api import MediaAsset

    return db.query(MediaAsset).filter(MediaAsset.title == titel).one()


# ── 1. De link hoort bij een sponsor ───────────────────────────────────────

def test_een_foto_bewaart_geen_link(client, db_session):
    """Server-side genegeerd, niet alleen verborgen in het scherm: op een verborgen
    veld vertrouwen laat de andere ingang open."""
    activiteit = _activiteit(db_session)
    db_session.commit()
    csrf = _login(client)

    resp = _upload(client, csrf, kind="activity_photo", activity_id=activiteit.id,
                   title="Foto", link_url="https://example.org")
    assert resp.status_code in (200, 204), resp.text[:300]

    db_session.expire_all()
    assert _asset(db_session, "Foto").link_url is None


def test_een_sponsor_bewaart_de_link_wel(client, db_session):
    csrf = _login(client)
    resp = _upload(client, csrf, kind="sponsor", title="Logo",
                   link_url="https://sponsor.example")
    assert resp.status_code in (200, 204), resp.text[:300]

    db_session.expire_all()
    assert _asset(db_session, "Logo").link_url == "https://sponsor.example"


@pytest.mark.parametrize("gevaarlijk", [
    "javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,<script>",
])
def test_een_onveilig_schema_wordt_geweigerd(client, db_session, gevaarlijk):
    """De waarde gaat rechtstreeks in een `href` op een publieke pagina."""
    csrf = _login(client)
    resp = _upload(client, csrf, kind="sponsor", title="Kwaad",
                   link_url=gevaarlijk)
    assert resp.status_code == 200
    assert "moet met" in resp.text, resp.text[:300]

    from app.domains.media.api import MediaAsset
    assert not db_session.query(MediaAsset).filter(
        MediaAsset.title == "Kwaad").all()


@pytest.mark.parametrize("goed", ["https://x.example", "http://x.example",
                                  "mailto:info@example.org", "/fotos"])
def test_gewone_links_blijven_toegestaan(client, db_session, goed):
    """De keerzijde: zonder haar zou "weiger alles" ook slagen, en dan kan een
    sponsorlogo nergens meer heen wijzen."""
    csrf = _login(client)
    resp = _upload(client, csrf, kind="sponsor", title=f"Ok {goed}", link_url=goed)
    assert resp.status_code in (200, 204), resp.text[:300]
    db_session.expire_all()
    assert _asset(db_session, f"Ok {goed}").link_url == goed


def test_de_regel_geldt_ook_op_de_json_route(client, db_session, admin_headers):
    """Twee ingangen, één regel. Stond ze in het scherm, dan was ze hier omzeild —
    en dat is precies waarom ze in de service hoort."""
    from app.domains.media.api import MediaAsset

    csrf = _login(client)
    _upload(client, csrf, kind="sponsor", title="Viaapi",
            link_url="https://ok.example")
    db_session.commit()
    asset = _asset(db_session, "Viaapi")

    resp = client.patch(f"/api/v1/admin/media/{asset.id}",
                        json={"link_url": "javascript:alert(1)"},
                        headers=admin_headers)
    assert resp.status_code == 400, resp.text[:300]

    db_session.expire_all()
    assert db_session.get(MediaAsset, asset.id).link_url == "https://ok.example"


# ── 2. Het scherm toont het veld alleen bij een sponsor ────────────────────

def test_het_linkveld_volgt_de_soortkeuze(client, db_session):
    _login(client)
    html = client.get("/admin/media/nieuw?kind=sponsor").text
    start = html.index('id="me-link"')
    blok = html[html.rindex("<div", 0, start):start]
    assert "soort === 'sponsor'" in blok, blok


# ── 3. De standaardsoort (#708) ────────────────────────────────────────────

def test_de_medialijst_opent_op_activiteitenfotos(client, db_session):
    _login(client)
    html = client.get("/admin/media").text
    assert 'href="/admin/media/nieuw?kind=activity_photo"' in html, (
        "de lijst geeft nog sponsor door aan het uploadscherm")


def test_het_uploadscherm_staat_standaard_op_activiteitenfoto(client, db_session):
    _login(client)
    html = client.get("/admin/media/nieuw").text
    assert 'value="activity_photo" selected' in html


def test_een_meegegeven_soort_wint_nog_altijd(client, db_session):
    """De keerzijde, en niet theoretisch: zonder haar zou "zet overal
    activity_photo" ook slagen terwijl het meegegeven type genegeerd wordt — en dan
    is de soortkeuze uit #696 stilletjes stuk."""
    _login(client)
    html = client.get("/admin/media/nieuw?kind=sponsor").text
    assert 'value="sponsor" selected' in html


# ── 4. De volgorde van de velden ───────────────────────────────────────────

def test_de_bestanden_staan_onderaan(client, db_session):
    """Soort → Activiteit → Titel/Link → Bestanden: eerst zeggen wát je uploadt,
    dan pas kiezen wélke bestanden."""
    _login(client)
    html = client.get("/admin/media/nieuw?kind=activity_photo").text

    assert html.index('name="kind"') < html.index('name="activity_id"')
    assert html.index('name="activity_id"') < html.index('name="title"')
    assert html.index('name="title"') < html.index('name="files"')
