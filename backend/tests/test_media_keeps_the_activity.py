"""De gekozen activiteit overleeft het uploaden (#962).

Koen: *"Indien je in de view-modus een activiteit selecteert en je gaat dan
uploaden is het handig als de upload-activiteit dropdown al gepopuleerd wordt met
die activiteit. Indien je een upload doet voor een bepaalde activiteit en je slaat
op keer je best ook terug naar de view-modus van die activiteit."*

Twee keer hetzelfde gebrek: het scherm weet welke activiteit je bekijkt en vergeet
het bij de overgang. Je koos hem bij het filteren, opnieuw bij het uploaden, en een
derde keer na het opslaan — terwijl het typische gebruik nu juist is: foto's van
één activiteit, in meerdere keren.

**Wat deze tests vooral vastleggen is de vorm van de oplossing.** Soort, zoekterm
en activiteit vormen samen "waar ik was", en dat adres wordt op één plaats
samengesteld. Dat is geen netheid: het stond op drie plaatsen, en toen liep er één
achter — de foutafhandeling nam de filterstand wél mee, het geslaagde pad niet. De
uitzondering zat dus op het pad dat je elke keer neemt.

Derde keer deze maand dat een met de hand samengesteld adres context laat vallen
(#922 verloor de tenant-prefix, #928 de slug).
"""
from datetime import date

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.media.admin_ui import _filterstand
from app.domains.media.api import MediaAsset
from tests.conftest import SEEDED_ADMIN_EMAIL


def _png() -> bytes:
    """Een echte, minimale PNG: de upload valideert de afbeelding.

    Drie bytes 'JPEG' halen het niet — dat leverde een nette foutmelding en een
    200 waar deze tests een 204 verwachten, wat me eerst als een bug in de redirect
    las. Bouwen dus, niet nabootsen."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


@pytest.fixture
def activiteit(db_session):
    a = Activity(tenant_id=2, name="Zomerfeest")
    db_session.add(a)
    db_session.flush()
    db_session.add(ActivityDate(tenant_id=2, activity_id=a.id,
                                start_date=date.today()))
    # Eén foto, want de filterdropdown toont enkel activiteiten die media hebben.
    db_session.add(MediaAsset(tenant_id=2, kind="activity_photo", activity_id=a.id,
                              content_type="image/jpeg", data=b"x"))
    db_session.commit()
    return a


# ── Het adres komt uit één plek ──────────────────────────────────────────────

def test_the_address_carries_what_you_were_looking_at():
    assert _filterstand("activity_photo", "", 7) == "kind=activity_photo&activity_id=7"
    assert _filterstand("activity_photo", "zomer", 7) == (
        "kind=activity_photo&q=zomer&activity_id=7")
    assert _filterstand("activity_photo") == "kind=activity_photo"


def test_an_activity_only_travels_with_activity_photos():
    """Bij een sponsorlogo betekent een activiteit niets — er is daar geen filter.

    Meesturen zou een parameter achterlaten die bij de volgende overgang weer
    opduikt, en de regel hoort op één plaats en niet bij de drie aanroepers.

    Kapotgemaakt om het rood te zien: de `and kind == "activity_photo"`-voorwaarde
    weggehaald — dan draagt een sponsorterugkeer een activiteit mee.
    """
    assert _filterstand("sponsor", "", 7) == "kind=sponsor"
    assert _filterstand("sponsor", "logo", 7) == "kind=sponsor&q=logo"


def test_no_screen_composes_this_address_by_hand():
    """De drie overgangen lezen uit `filterstand`; geen sjabloon plakt zelf iets.

    Kapotgemaakt om het rood te zien: `"/admin/media/nieuw?kind=" ~ kind` teruggezet
    in `admin_media.html` — dan noemt dit de sjabloonnaam.
    """
    from pathlib import Path

    sjablonen = Path(__file__).resolve().parents[1] / "app" / "domains" / "media" \
        / "templates"
    bekeken = 0
    for pad in sjablonen.glob("*.html"):
        bekeken += 1
        tekst = pad.read_text(encoding="utf-8")
        regels = [r for r in tekst.splitlines()
                  if "/admin/media/nieuw?" in r and "filterstand" not in r
                  and not r.strip().startswith("{#")]
        assert not regels, (
            f"{pad.name} stelt zelf een uploadadres samen: {regels[0].strip()}")
    assert bekeken >= 3, (
        f"deze poort keek naar {bekeken} sjablonen, te weinig om iets te bewijzen (#678)")


# ── Van de lijst naar het uploadscherm ───────────────────────────────────────

def test_the_upload_button_carries_the_chosen_activity(client, db_session,
                                                       activiteit):
    """Punt 1, en het was één parameter: de voorselectie stond er al.

    `_lijst_ctx` las `activity_id` al uit de query en het uploadsjabloon had
    `selected` al. De knop gaf hem alleen nooit mee.
    """
    _login(client)
    tekst = client.get(
        f"/admin/media?kind=activity_photo&activity_id={activiteit.id}").text

    # `&amp;` en niet `&`: dat is hoe een href in HTML hoort te staan.
    assert (f"/admin/media/nieuw?kind=activity_photo&amp;activity_id={activiteit.id}"
            in tekst)


def test_the_upload_screen_preselects_that_activity(client, db_session, activiteit):
    _login(client)
    tekst = client.get(
        f"/admin/media/nieuw?kind=activity_photo&activity_id={activiteit.id}").text

    assert f'value="{activiteit.id}" selected' in tekst


# ── En terug ─────────────────────────────────────────────────────────────────

def test_a_successful_upload_returns_to_the_same_list(client, db_session,
                                                      activiteit):
    """Punt 2. Het geslaagde pad was de uitzondering, niet de foutafhandeling.

    Kapotgemaakt om het rood te zien: de redirect terug op het kale `/admin/media`
    — dan staat er geen activiteit in en kom je in de ongefilterde lijst.
    """
    csrf = _login(client)
    resp = client.post(
        "/admin/media",
        data={"kind": "activity_photo", "activity_id": str(activiteit.id),
              "q": "", "filter_activity_id": str(activiteit.id)},
        files={"files": ("foto.png", _png(), "image/png")},
        headers={"X-CSRF-Token": csrf})

    assert resp.status_code == 204
    assert resp.headers["HX-Redirect"] == (
        f"/admin/media?kind=activity_photo&activity_id={activiteit.id}")


def test_a_failed_upload_still_keeps_you_where_you_were(client, db_session,
                                                        activiteit):
    """Dit deed het al goed, en daarom staat het hier.

    De foutafhandeling bouwde de filterstand al terug op terwijl het geslaagde pad
    dat niet deed. Als deze ooit rood wordt, is de reparatie van #962 de verkeerde
    kant opgevallen — dan is de uitzondering verplaatst in plaats van weggehaald.
    """
    csrf = _login(client)
    resp = client.post(
        "/admin/media",
        data={"kind": "activity_photo", "activity_id": "",   # verplicht, dus fout
              "q": "", "filter_activity_id": str(activiteit.id)},
        files={"files": ("foto.png", _png(), "image/png")},
        headers={"X-CSRF-Token": csrf})

    assert resp.status_code == 200
    assert f'value="{activiteit.id}" selected' in resp.text


def test_a_sponsor_upload_returns_to_the_sponsor_list(client, db_session,
                                                      activiteit):
    """Schakel je op het uploadscherm om, dan toont de lijst wat je net toevoegde.

    De terugkeer volgt de soort die je UPLOADDE en niet het filter waar je vandaan
    kwam — anders land je in een filtering waarin je eigen upload onzichtbaar is.
    """
    csrf = _login(client)
    resp = client.post(
        "/admin/media",
        data={"kind": "sponsor", "title": "Bakkerij", "q": "",
              "filter_activity_id": str(activiteit.id)},
        files={"files": ("logo.png", _png(), "image/png")},
        headers={"X-CSRF-Token": csrf})

    assert resp.status_code == 204
    assert resp.headers["HX-Redirect"] == "/admin/media?kind=sponsor"
