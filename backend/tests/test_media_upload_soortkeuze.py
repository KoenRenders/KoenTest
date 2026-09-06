"""#696 — op het uploadscherm kon je geen activiteit meer kiezen.

De soort was daar geen keuze: `"+ Uploaden"` linkte naar
`/admin/media/nieuw?kind=<huidig filter>` en die waarde stond daarna als verborgen
veld in het formulier. Stond je op het sponsorfilter, dan kon je alleen een sponsor
uploaden, en de activiteitendropdown zat achter `{% if kind == "activity_photo" %}`
en verscheen dus nooit. Geen weg terug op dat scherm.

**De kern: op de lijst is `kind` een filter, op het uploadscherm een eigenschap van
wat je uploadt.** Die twee zijn bij #627 samengevallen in één parameter. De
filterstand is nu de beginwaarde van een echte keuze.

In v1.14 stonden de twee tabbladen op dezelfde pagina als het uploadformulier en was
omschakelen één klik; daar zat ook de controle "Kies eerst een activiteit."

**Let op waar het stil kan misgaan**: de dropdown moet álle activiteiten tonen, ook
die zonder foto's (#476), terwijl het lijstfilter bewust alleen activiteiten mét
media toont. En een geüploade foto hoort onder de **gekozen** activiteit te landen,
niet onder die uit het lijstfilter.
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
    Image.new("RGB", (40, 40), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _activiteit(db, naam):
    from datetime import date, timedelta

    from app.domains.activities.api import Activity, ActivityDate

    a = Activity(name=naam)
    db.add(a)
    db.flush()
    db.add(ActivityDate(activity_id=a.id, start_date=date.today() + timedelta(days=7)))
    db.flush()
    return a


def _upload(client, csrf, **velden):
    data = {"kind": "sponsor", "q": "", "filter_activity_id": ""}
    data.update({k: str(v) for k, v in velden.items() if v is not None})
    return client.post("/admin/media", data=data,
                       files={"files": ("foto.png", _png(), "image/png")},
                       headers={"X-CSRF-Token": csrf})


# ── 1. De soort is een keuze op het scherm ──────────────────────────────────

@pytest.mark.parametrize("filterstand", ["sponsor", "activity_photo"])
def test_het_uploadscherm_laat_de_soort_kiezen(client, db_session, filterstand):
    """Vanaf élke filterstand, want dat was juist het probleem: vanaf het
    sponsorfilter was activiteitenfoto onbereikbaar."""
    _login(client)
    html = client.get(f"/admin/media/nieuw?kind={filterstand}").text

    assert 'name="kind"' in html
    assert '<select name="kind"' in html, "de soort staat nog als verborgen veld"
    for waarde in ("sponsor", "activity_photo"):
        assert f'value="{waarde}"' in html, f"{waarde} ontbreekt in de keuzelijst"


def test_de_filterstand_is_de_beginwaarde_en_niet_de_beslissing(client, db_session):
    _login(client)
    html = client.get("/admin/media/nieuw?kind=activity_photo").text
    assert 'value="activity_photo" selected' in html, "de filterstand staat niet voor"
    assert 'value="sponsor"' in html, "en de andere soort is nog altijd kiesbaar"


def test_de_activiteitendropdown_staat_er_ook_vanaf_het_sponsorfilter(client,
                                                                      db_session):
    """Ze zat achter een server-side `{% if kind == "activity_photo" %}` en
    verscheen dus nooit als je vanaf het sponsorfilter kwam. Nu volgt ze de keuze in
    het scherm."""
    _activiteit(db_session, "Zomerfeest")
    db_session.commit()
    _login(client)

    html = client.get("/admin/media/nieuw?kind=sponsor").text
    assert 'name="activity_id"' in html, "de dropdown ontbreekt"
    assert "Zomerfeest" in html
    assert "soort === 'activity_photo'" in html, (
        "de dropdown volgt de keuze niet")


def test_de_dropdown_toont_ook_activiteiten_zonder_media(client, db_session):
    """#476: je moet foto's aan om het even welke activiteit kunnen koppelen. Het
    lijstfilter toont bewust alleen activiteiten mét media — die twee lijsten zijn
    niet hetzelfde en mogen niet samenvallen."""
    _activiteit(db_session, "Nog Geen Fotos")
    db_session.commit()
    _login(client)

    assert "Nog Geen Fotos" in client.get("/admin/media/nieuw?kind=activity_photo").text


def test_de_dropdown_draagt_geen_vast_required(client, db_session):
    """Een verborgen veld met `required` laat de browser bij verzenden falen met
    "An invalid form control is not focusable" — het verzenden mislukt dan
    geruisloos. Dezelfde val als bij #688; de server controleert het hoe dan ook."""
    _login(client)
    html = client.get("/admin/media/nieuw?kind=sponsor").text

    start = html.index('name="activity_id"')
    tag = html[html.rindex("<select", 0, start):html.index(">", start)]
    assert " required" not in tag, tag
    assert ":required=" in tag, tag


# ── 2. Wat er werkelijk opgeslagen wordt ────────────────────────────────────

def test_de_foto_landt_onder_de_gekozen_activiteit(client, db_session):
    """De stille fout die deze samenvoeging kan opleveren: opslaan onder de
    activiteit uit het lijstfilter in plaats van onder de gekozen."""
    from app.domains.media.api import MediaAsset

    gekozen = _activiteit(db_session, "Gekozen")
    uit_filter = _activiteit(db_session, "Uit het filter")
    db_session.commit()
    csrf = _login(client)

    resp = _upload(client, csrf, kind="activity_photo",
                   activity_id=gekozen.id, filter_activity_id=uit_filter.id,
                   title="Testfoto")
    assert resp.status_code in (200, 204), resp.text[:300]

    asset = (db_session.query(MediaAsset)
             .filter(MediaAsset.title == "Testfoto").one())
    assert asset.activity_id == gekozen.id, (
        "de foto hangt aan de activiteit uit het lijstfilter")


def test_een_sponsor_hangt_aan_geen_enkele_activiteit(client, db_session):
    """De keerzijde: kies je sponsor, dan mag een meegestuurde activiteit niet
    blijven plakken."""
    from app.domains.media.api import MediaAsset

    activiteit = _activiteit(db_session, "Niet gebruiken")
    db_session.commit()
    csrf = _login(client)

    resp = _upload(client, csrf, kind="sponsor", activity_id=activiteit.id,
                   title="Logo")
    assert resp.status_code in (200, 204), resp.text[:300]
    assert db_session.query(MediaAsset).filter(
        MediaAsset.title == "Logo").one().activity_id is None


# ── 3. De melding uit v1.14 ─────────────────────────────────────────────────

def test_uploaden_zonder_activiteit_zegt_wat_je_moet_doen(client, db_session):
    """v1.14 zei "Kies eerst een activiteit."; de melding was "activity_id vereist
    voor activiteitenfoto's" — dat is de naam van een kolom, niet iets wat je doet.

    Toetsen op de reden én op wat er níet bewaard is: een banner tonen en tóch
    opslaan ziet er van buitenaf hetzelfde uit.
    """
    from app.domains.media.api import MediaAsset

    csrf = _login(client)
    resp = _upload(client, csrf, kind="activity_photo", title="Zonder activiteit")

    assert resp.status_code == 200, resp.text[:300]
    assert "Kies eerst een activiteit" in resp.text, resp.text[:400]
    assert not db_session.query(MediaAsset).filter(
        MediaAsset.title == "Zonder activiteit").all()
