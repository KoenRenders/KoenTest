"""#710 — het type hoort vóór de vraag te staan, op dezelfde regel.

In v1.14 stond *Type · Vraag · Verplicht* op één regel. In v2 stond Vraag vooraan en
Type op een eigen regel eronder, waar op een breed scherm twee kolommen leeg bleven.

Er zit logica onder, en die weegt zwaarder dan de ruimte: **het type bepaalt wélke
velden daarna verschijnen** — min/max tekens, puntenschaal, de optielijst. Je kiest
dus eerst de soort en vult daarna in; andersom vul je in wat nog kan veranderen.

Vier kolommen op `sm`, niet drie: met drie wordt de vraag te smal zodra alle drie op
één regel moeten. Type (1) · Vraag (2) · Verplicht (1).

**Deze tests toetsen de onderlinge POSITIE, niet de aanwezigheid.** Die drie velden
staan er al sinds #700/#701, dus een aanwezigheidstest zou vandaag al groen staan en
niets zeggen over de volgorde.

Alleen indeling: niets aan velden, namen of gedrag. Twee dingen die bij een
herindeling makkelijk achterblijven, hebben daarom een eigen test — de uitleg onder
een geblokkeerde typekeuze, en het `disabled`/`title`-gedrag uit #700.
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


def _formulier(client, admin_headers):
    r = client.post("/api/v1/forms", json={
        "title": "Indeling", "status": "open", "is_anonymous": True,
        "fields": [{"field_type": "text", "label": "Vraag", "position": 0}],
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _bewerkvorm(html: str, veld_id: int) -> str:
    """De veldvorm van dit veld, van <form> tot </form>."""
    merk = f'id="fl-{veld_id}"'
    start = html.rindex("<form", 0, html.index(merk))
    return html[start:html.index("</form>", start)]


# ── 1. De volgorde ─────────────────────────────────────────────────────────

def test_het_type_staat_voor_de_vraag(client, admin_headers):
    """De positie, niet de aanwezigheid: alle drie stonden er al."""
    form = _formulier(client, admin_headers)
    _login(client)
    veld = form["fields"][0]
    vorm = _bewerkvorm(client.get(f"/admin/formulieren/{form['id']}").text,
                       veld["id"])

    type_pos = vorm.index('name="field_type"')
    vraag_pos = vorm.index('name="label"')
    verplicht_pos = vorm.index('name="required"')
    assert type_pos < vraag_pos < verplicht_pos, (
        "de volgorde is Type · Vraag · Verplicht, en het type bepaalt wat er daarna "
        "verschijnt")


def test_ook_op_de_toevoegvorm(client, admin_headers):
    """Eén macro voor beide paden (#701), dus dit hoort automatisch te kloppen — en
    juist daarom is het de moeite om te bewaken: gaan ze ooit weer uit elkaar, dan
    valt het hier op."""
    form = _formulier(client, admin_headers)
    _login(client)
    html = client.get(f"/admin/formulieren/{form['id']}").text
    start = html.rindex("<form", 0, html.index('id="fl-nieuw"'))
    vorm = html[start:html.index("</form>", start)]

    assert vorm.index('name="field_type"') < vorm.index('name="label"')


def test_de_drie_passen_op_een_regel(client, admin_headers):
    """Vier kolommen op `sm`: Type (1) · Vraag (2) · Verplicht (1). Met drie zou de
    vraag te smal worden."""
    form = _formulier(client, admin_headers)
    _login(client)
    vorm = _bewerkvorm(client.get(f"/admin/formulieren/{form['id']}").text,
                       form["fields"][0]["id"])

    vorm_tag = vorm[:vorm.index(">")]
    assert "sm:grid-cols-4" in vorm_tag, vorm_tag
    # De vraag krijgt de dubbele breedte; type en verplicht elk één kolom.
    vraag_div = vorm[vorm.rindex("<div", 0, vorm.index('name="label"')):]
    assert "sm:col-span-2" in vraag_div[:vraag_div.index(">")], vraag_div[:120]


def test_op_smal_blijft_alles_gestapeld(client, admin_headers):
    """Eén kolom zonder breekpunt: op een telefoon horen de velden onder elkaar."""
    form = _formulier(client, admin_headers)
    _login(client)
    vorm = _bewerkvorm(client.get(f"/admin/formulieren/{form['id']}").text,
                       form["fields"][0]["id"])
    assert "grid-cols-1 sm:grid-cols-4" in vorm[:vorm.index(">")]


# ── 2. Wat bij een herindeling achterblijft ────────────────────────────────

def test_de_uitleg_blijft_onder_de_geblokkeerde_typekeuze(client, admin_headers):
    """Ze verschijnt alleen bij een formulier mét inzendingen, dus dit geval moet
    apart. Zonder die uitleg is een grijze lijst een scherm dat weigert zonder te
    zeggen waarom."""
    form = _formulier(client, admin_headers)
    veld = form["fields"][0]
    resp = client.post(f"/formulier/{form['share_token']}",
                       data={f"f{veld['id']}": "iets"})
    assert resp.status_code == 200, resp.text[:200]
    _login(client)

    vorm = _bewerkvorm(client.get(f"/admin/formulieren/{form['id']}").text,
                       veld["id"])
    uitleg = "Er zijn al inzendingen; het type ligt vast."
    assert uitleg in vorm, "de uitleg is verdwenen bij de herindeling"
    assert vorm.index('name="field_type"') < vorm.index(uitleg) < vorm.index('name="label"'), (
        "de uitleg staat niet meer direct onder de typekeuze")


def test_het_blokkeergedrag_uit_700_is_ongewijzigd(client, admin_headers):
    """Alleen de indeling verandert; `disabled` en de tooltip blijven."""
    form = _formulier(client, admin_headers)
    veld = form["fields"][0]
    client.post(f"/formulier/{form['share_token']}", data={f"f{veld['id']}": "iets"})
    _login(client)

    html = client.get(f"/admin/formulieren/{form['id']}").text
    start = html.index('name="field_type"')
    select = html[html.rindex("<select", 0, start):html.index(">", start)]
    assert "disabled" in select and "inzendingen" in select, select


def test_zonder_inzendingen_staat_er_geen_uitleg(client, admin_headers):
    """De keerzijde: zonder haar zou "zet de uitleg er altijd bij" ook slagen, en
    dan lees je bij elk veld dat het type vastligt terwijl dat niet zo is."""
    form = _formulier(client, admin_headers)
    _login(client)
    vorm = _bewerkvorm(client.get(f"/admin/formulieren/{form['id']}").text,
                       form["fields"][0]["id"])
    assert "het type ligt vast" not in vorm
