"""#703 — de sectiebalk zweefde, en een lege kaart bestond alleen voor een knop.

De rest van dezelfde scheur als #701: dat issue verving de invoerbalk *binnen* een
sectie, dit de twee eronder.

1. De sectiebalk was een kaal invoerveld met knop tussen twee kaarten in — geen
   kaart, geen kop, geen omhulsel. Vandaar dat hij verloren aanvoelde.
2. Zonder losse velden rendeerde de bouwer alsnog een volledige kaart met een kop
   waarvan de enige inhoud de toevoegbalk was: een omhulsel om een knop.
3. Eén begrip, twee namen op hetzelfde scherm — "Ongegroepeerde velden" mét losse
   velden, "Velden zonder sectie" zonder. Afhankelijk van of de lijst toevallig leeg
   was.

**Waarom de sectieknop wél meteen post, anders dan bij #701.** `add_section` laat een
lege titel toe, en de template rekent daar al op: de kop van een sectie staat achter
een voorwaarde op haar titel. Een naamloze sectie is dus een geldige toestand.
`add_field` daarentegen eist een label, en dáárom moet de lege veldkaart client-side
verschijnen. De derde test hieronder legt dat fundament vast — valt die aanname weg,
dan klopt de keuze om direct te posten niet meer.
"""
import pytest

from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_agnostisch


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _formulier(client, admin_headers, velden=None, secties=None):
    r = client.post("/api/v1/forms", json={
        "title": "Staart", "status": "draft",
        "sections": secties if secties is not None else [],
        "fields": velden or [],
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _bouwer(client, form_id) -> str:
    resp = client.get(f"/admin/formulieren/{form_id}")
    assert resp.status_code == 200, resp.text[:200]
    return resp.text


# ── 1. Geen lege kaart meer ────────────────────────────────────────────────

def test_zonder_losse_velden_staat_er_geen_lege_kaart(client, admin_headers):
    """Een kop met als enige inhoud een knop is een omhulsel om niets."""
    form = _formulier(client, admin_headers)
    _login(client)
    html = _bouwer(client, form["id"])

    assert "Velden zonder sectie" not in html, (
        "de kaart staat er terwijl er geen losse velden zijn")
    assert "+ Vraag (zonder sectie)" in html, "de knop is meeverdwenen"


def test_met_losse_velden_blijft_de_kaart(client, admin_headers):
    form = _formulier(client, admin_headers, [
        {"field_type": "text", "label": "Los", "position": 0}])
    _login(client)
    html = _bouwer(client, form["id"])

    assert "Velden zonder sectie" in html
    assert "Los" in html
    # De knop staat dan ín de kaart, zoals bij "+ Vraag in deze sectie".
    assert "+ Vraag in deze sectie" in html


# ── 2. Eén naam voor één begrip ────────────────────────────────────────────

@pytest.mark.parametrize("met_velden", [True, False])
def test_er_is_maar_een_naam_voor_velden_zonder_sectie(client, admin_headers,
                                                       met_velden):
    """"Ongegroepeerd" is jargon dat elders in de app niet voorkomt, en de naam mag
    niet afhangen van of de lijst toevallig leeg is."""
    velden = [{"field_type": "text", "label": "Los", "position": 0}] if met_velden else []
    form = _formulier(client, admin_headers, velden)
    _login(client)
    html = _bouwer(client, form["id"])

    assert "Ongegroepeerde" not in html, "de tweede naam staat er nog"


# ── 3. Het fundament: een naamloze sectie is geldig ────────────────────────

def test_een_sectie_zonder_titel_rendert_zonder_lege_kop(client, admin_headers,
                                                         db_session):
    """Hierop leunt de keuze om de sectieknop meteen te laten posten.

    Valt deze aanname weg — bijvoorbeeld doordat iemand `add_section` een verplichte
    titel geeft — dan levert die knop een fout in plaats van een sectie, en klopt de
    rest van dit issue niet meer.
    """
    from app.domains.forms.models import FormSection

    form = _formulier(client, admin_headers)
    csrf = _login(client)

    resp = client.post(f"/admin/formulieren/{form['id']}/secties",
                       data={"title": ""}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200, resp.text[:300]

    db_session.expire_all()
    sectie = db_session.query(FormSection).filter(
        FormSection.form_id == form["id"]).one()
    assert sectie.title is None, "een lege titel werd niet als 'geen titel' bewaard"

    html = _bouwer(client, form["id"])
    assert "Sectie 1 van 1" in html, "de sectie staat niet op het scherm"


def test_een_naamloze_sectie_blijft_bewerkbaar(client, admin_headers, db_session):
    """Benoemen doe je in haar eigen bewerkvorm — dat is de hele reden dat direct
    posten mag."""
    from app.domains.forms.models import FormSection

    form = _formulier(client, admin_headers)
    csrf = _login(client)
    client.post(f"/admin/formulieren/{form['id']}/secties", data={"title": ""},
                headers={"X-CSRF-Token": csrf})
    db_session.expire_all()
    sectie = db_session.query(FormSection).filter(
        FormSection.form_id == form["id"]).one()

    resp = client.post(f"/admin/formulieren/{form['id']}/secties/{sectie.id}",
                       data={"title": "Nu wel een naam"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200, resp.text[:300]

    db_session.expire_all()
    assert db_session.get(FormSection, sectie.id).title == "Nu wel een naam"


# ── 4. De twee knoppen onderaan ────────────────────────────────────────────

def test_de_sectieknop_staat_niet_meer_los_tussen_de_kaarten(client, admin_headers):
    """Geen invoerveld meer: de knop maakt de sectie aan, benoemen komt daarna."""
    form = _formulier(client, admin_headers)
    _login(client)
    html = _bouwer(client, form["id"])

    assert "+ Sectie toevoegen" in html
    assert 'placeholder="Nieuwe sectie"' not in html, (
        "de oude invoerbalk staat er nog")


def test_de_knop_voor_een_los_veld_is_dezelfde_vorm(client, admin_headers):
    """Dezelfde `veld_vorm` als "+ Vraag in deze sectie", alleen zonder sectie-id.
    Zou dit een eigen formulier zijn, dan lopen de twee opnieuw uit elkaar (#701)."""
    form = _formulier(client, admin_headers)
    _login(client)
    html = _bouwer(client, form["id"])

    start = html.index('id="fl-nieuw"')
    vorm = html[html.rindex("<form", 0, start):html.index("</form>", start)]
    for veld in ('name="label"', 'name="field_type"', 'name="help_text"'):
        assert veld in vorm, f"{veld} ontbreekt in de losse-veldvorm"
    assert 'name="section_id" value=""' in vorm, "het veld krijgt tóch een sectie"
