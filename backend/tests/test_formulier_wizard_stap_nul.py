"""#688 — inleiding en naam/e-mailkaart hoorden alleen op de eerste stap.

Beide blokken staan één keer in de HTML, maar stonden buiten de wizard-container.
Alleen de stappen worden met `x-show` verborgen, dus alles erboven bleef op élke
stap staan. De Alpine-scope omvat nu de hele pagina, en de twee blokken hangen aan
stap 0. De **titel** blijft wel op elke stap staan: die zegt waar je bent.

**Aanwezigheid bewijst hier niets.** `x-show` verbergt in de browser; de tekst
staat in beide gevallen gewoon in de opgeleverde HTML. `"…" in html` zou dus ook
groen zijn geweest als deze wijziging nooit gemaakt was. Deze tests toetsen daarom
de **binding aan stap 0**, niet de tekst.

De val zat in `required`: `submitter_name` en `submitter_email` stonden er
onvoorwaardelijk op. Een verborgen veld met `required` laat de browser bij
verzenden falen met *"An invalid form control is not focusable"* — de
constraint-validatie wil naar een onzichtbaar veld springen, en het verzenden
mislukt geruisloos. Erger dan het probleem dat we oplossen. Het attribuut valt dus
weg in wizardmodus, precies zoals bij de sectievelden; `assert_submitter` blijft
het vangnet eronder, en de laatste test hier bewaakt dat dat vangnet er nog is.
"""
import pytest

pytestmark = pytest.mark.ui_agnostisch

STAP_NUL = 'x-show="step === 0"'
INLEIDING = "Lees dit eerst aandachtig."


def _maak(client, admin_headers, *, secties: int):
    """Een niet-anoniem formulier met een inleiding; ≥2 secties → wizard."""
    payload = {
        "title": "Enquête", "status": "open", "is_anonymous": False,
        "description": INLEIDING,
        "sections": [{"title": f"Stap {i + 1}", "position": i}
                     for i in range(secties)],
        "fields": [{"field_type": "text", "label": f"Vraag {i + 1}",
                    "required": True, "position": i, "section_index": i}
                   for i in range(secties)],
    }
    r = client.post("/api/v1/forms", json=payload, headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _open_tag(html: str, tag: str, merk: str) -> str:
    """De openingstag van het `tag`-element dat vlak vóór `merk` staat."""
    start = html.rindex(f"<{tag}", 0, html.index(merk))
    return html[start:html.index(">", start)]


def _velden_tussen_form_en_naam(html: str) -> str:
    return html[html.index("<form "):html.index('id="submitter_name"')]


# ── 1. De binding, niet de tekst ─────────────────────────────────────────────

def test_de_inleiding_hangt_aan_stap_nul(client, admin_headers):
    form = _maak(client, admin_headers, secties=2)
    html = client.get(f"/formulier/{form['share_token']}").text
    assert "formWizard(" in html, "dit hoort een wizard te zijn"

    tag = _open_tag(html, "p", INLEIDING)
    assert STAP_NUL in tag, f"de inleiding staat op elke stap: {tag}"


def test_de_naam_en_mailkaart_hangt_aan_stap_nul(client, admin_headers):
    form = _maak(client, admin_headers, secties=2)
    html = client.get(f"/formulier/{form['share_token']}").text

    # De slice loopt van de <form>-tag tot het naamveld. De stapdivs staan verderop
    # in het document en dragen zélf `x-show="step === 0"` op stap 0 — die kunnen
    # deze assertie dus niet per ongeluk groen maken.
    assert STAP_NUL in _velden_tussen_form_en_naam(html), (
        "de naam/e-mailkaart hangt niet aan stap 0 en blijft dus op elke stap staan")
    assert 'data-step="0"' in html[html.index('id="submitter_email"'):], (
        "de stappen horen ná de naam/e-mailkaart te komen; klopt dat niet, dan meet "
        "de assertie hierboven mogelijk de verkeerde binding")


def test_de_titel_blijft_op_elke_stap(client, admin_headers):
    """Bewust géén binding: de titel zegt waar je bent."""
    form = _maak(client, admin_headers, secties=2)
    html = client.get(f"/formulier/{form['share_token']}").text

    tag = _open_tag(html, "h1", "Enquête")
    assert STAP_NUL not in tag, tag


# ── 2. Zonder wizard verandert er niets ──────────────────────────────────────

def test_zonder_wizard_zijn_er_geen_stapbindingen(client, admin_headers):
    """Eén sectie → geen wizard. Zonder deze test zou "hang het altijd aan stap 0"
    ook slagen, en dan verdwijnt op een gewoon formulier de halve pagina."""
    form = _maak(client, admin_headers, secties=1)
    html = client.get(f"/formulier/{form['share_token']}").text

    assert "formWizard(" not in html
    assert STAP_NUL not in html
    assert INLEIDING in html


# ── 3. De val: `required` op een verborgen veld ──────────────────────────────

def test_in_wizardmodus_dragen_naam_en_mail_geen_native_required(client, admin_headers):
    """Anders faalt de browser bij verzenden met "An invalid form control is not
    focusable" en mislukt het verzenden geruisloos."""
    form = _maak(client, admin_headers, secties=2)
    html = client.get(f"/formulier/{form['share_token']}").text

    for veld in ("submitter_name", "submitter_email"):
        tag = _open_tag(html, "input", f'id="{veld}"')
        assert "required" not in tag, f"{veld} draagt nog native required: {tag}"


def test_zonder_wizard_houden_ze_hun_required(client, admin_headers):
    """De keerzijde: op een gewoon formulier is er niets verborgen, dus daar blijft
    de vriendelijke browsercontrole gewoon staan."""
    form = _maak(client, admin_headers, secties=1)
    html = client.get(f"/formulier/{form['share_token']}").text

    for veld in ("submitter_name", "submitter_email"):
        tag = _open_tag(html, "input", f'id="{veld}"')
        assert "required" in tag, f"{veld} verloor zijn required: {tag}"


def test_het_sterretje_blijft_staan(client, admin_headers):
    """Het veld is nog steeds verplicht; alleen het HTML-attribuut valt weg. Zonder
    het sterretje zou het scherm suggereren dat je het mag overslaan."""
    form = _maak(client, admin_headers, secties=2)
    html = client.get(f"/formulier/{form['share_token']}").text

    for veld in ("submitter_name", "submitter_email"):
        label_start = html.rindex("<label", 0, html.index(f'for="{veld}"'))
        label = html[label_start:html.index("</label>", label_start)]
        assert "*" in label, f"het verplicht-sterretje bij {veld} is weg"


# ── 4. Het vangnet eronder blijft ────────────────────────────────────────────

def test_verzenden_zonder_naam_wordt_nog_altijd_geweigerd(client, admin_headers,
                                                          db_session):
    """Het HTML-attribuut was de vriendelijke variant, niet de regel.

    Deze test is waarom het weghalen van `required` veilig is; valt hij weg, dan
    kan een niet-anonieme inzending zonder naam ongemerkt binnenkomen. We kijken
    daarom óók of er niets bewaard is: een foutbanner tonen én tóch opslaan zou
    er van buitenaf hetzelfde uitzien.
    """
    from app.domains.forms.models import FormSubmission

    form = _maak(client, admin_headers, secties=2)

    resp = client.post(f"/formulier/{form['share_token']}",
                       data={"submitter_name": "", "submitter_email": ""})
    assert resp.status_code == 200, resp.text
    assert "geldig e-mailadres" in resp.text.lower(), resp.text
    assert db_session.query(FormSubmission).filter(
        FormSubmission.form_id == form["id"]).count() == 0


def test_verzenden_met_een_ongeldig_mailadres_wordt_geweigerd(client, admin_headers):
    form = _maak(client, admin_headers, secties=2)

    resp = client.post(f"/formulier/{form['share_token']}",
                       data={"submitter_name": "Jan",
                             "submitter_email": "geen-adres"})
    assert resp.status_code == 200, resp.text
    assert "geldig e-mailadres" in resp.text.lower(), resp.text
