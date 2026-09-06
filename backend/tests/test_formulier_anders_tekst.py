"""#683 — de tekst bij "Anders" verdween stil als het vinkje niet aan stond.

De tekst viel op **twee onafhankelijke plekken** weg, en dat is het hele punt:
één ervan repareren volstond niet.

1. `forms/ui.py` maakte pas een antwoord aan als er iets aangevinkt was, dus
   `{key}_other` werd nooit gelezen. De tekst zat wél in de post.
2. `forms/service.py` liet `other_text` niet meetellen in `has_value`, dus zelfs
   een antwoord dat de eerste hindernis passeerde werd als leeg overgeslagen.

En het invoerveld stond gewoon aan. Het scherm nodigde dus uit tot iets wat het
daarna twee keer weggooide, zonder melding.

**Deze tests kijken naar de OPGESLAGEN INZENDING, niet naar de statuscode.** Een
200 zegt hier niets: vandaag slaagt de submit ook, hij bewaart alleen niets. Dat
is dezelfde valkuil als bij #680, waar `assert status_code >= 400` elke 400 groen
maakte.
"""
import pytest

from app.domains.forms.models import FormSubmissionAnswer

pytestmark = pytest.mark.ui_agnostisch


def _payload(veldtype: str, *, verplicht: bool = False) -> dict:
    return {
        "title": f"Anders-test ({veldtype})",
        "status": "open",
        "fields": [
            {"field_type": veldtype, "label": "Waarom niet?", "position": 0,
             "required": verplicht,
             "options": [
                 {"label": "Geen tijd", "position": 0},
                 {"label": "Andere", "position": 1, "is_other": True},
             ]},
        ],
    }


def _bouw(client, admin_headers, veldtype: str, *, verplicht: bool = False):
    form = client.post("/api/v1/forms", json=_payload(veldtype, verplicht=verplicht),
                       headers=admin_headers).json()
    veld = form["fields"][0]
    anders = next(o for o in veld["options"] if o["is_other"])
    gewoon = next(o for o in veld["options"] if not o["is_other"])
    return form, veld, anders, gewoon


def _verstuur(client, form, veld, *, gekozen=None, tekst=None):
    """Post zoals het scherm het doet: `f{id}` en `f{id}_other`."""
    data = {"submitter_name": "Jan", "submitter_email": "jan@example.com"}
    if gekozen is not None:
        data[f"f{veld['id']}"] = str(gekozen)
    if tekst is not None:
        data[f"f{veld['id']}_other"] = tekst
    return client.post(f"/formulier/{form['share_token']}", data=data)


def _rijen(db, veld_id):
    return (db.query(FormSubmissionAnswer)
            .filter(FormSubmissionAnswer.field_id == veld_id).all())


# ── 1. Tekst zonder vinkje wordt bewaard ─────────────────────────────────────

@pytest.mark.parametrize("veldtype", ["checkbox", "radio"])
def test_alleen_de_anders_tekst_levert_een_antwoord_op(client, admin_headers,
                                                       db_session, veldtype):
    """Het gemelde geval: typen zonder aanvinken.

    De statuscode zou ook vóór #683 in orde geweest zijn — het gaat om wat er in
    de databank staat.
    """
    form, veld, anders, _gewoon = _bouw(client, admin_headers, veldtype)

    resp = _verstuur(client, form, veld, tekst="Op reis")
    assert resp.status_code == 200, resp.text

    rijen = _rijen(db_session, veld["id"])
    assert len(rijen) == 1, "de tekst is nergens bewaard"
    assert rijen[0].value_option_id == anders["id"], (
        "de bijhorende optie hoort mee opgeslagen te worden")
    assert rijen[0].value_text == "Op reis"


# ── 2. Bij een radio vervangt de tekst de eerdere keuze ──────────────────────

def test_bij_een_radio_blijft_precies_een_optie_over(client, admin_headers, db_session):
    """De keuze is exclusief, dus typen in "Anders" vervángt een eerdere optie.

    Dat is wat het scherm doet — typen selecteert de "Anders"-radio, de browser
    ontvinkt de andere — en de server mag daar niet van afwijken: twee opties op
    een radioveld is een toestand die het formulier niet kent.
    """
    form, veld, anders, gewoon = _bouw(client, admin_headers, "radio")

    resp = _verstuur(client, form, veld, gekozen=gewoon["id"], tekst="Op reis")
    assert resp.status_code == 200, resp.text

    rijen = _rijen(db_session, veld["id"])
    assert len(rijen) == 1, "een radio hoort één antwoord te hebben"
    assert rijen[0].value_option_id == anders["id"]
    assert rijen[0].value_text == "Op reis"


def test_bij_een_checkbox_komt_de_anders_optie_erbij(client, admin_headers, db_session):
    """Het spiegelbeeld: aankruisen is niet exclusief, dus hier vervangt ze niet."""
    form, veld, anders, gewoon = _bouw(client, admin_headers, "checkbox")

    resp = _verstuur(client, form, veld, gekozen=gewoon["id"], tekst="Op reis")
    assert resp.status_code == 200, resp.text

    rijen = _rijen(db_session, veld["id"])
    assert {r.value_option_id for r in rijen} == {gewoon["id"], anders["id"]}
    tekst_rij = next(r for r in rijen if r.value_option_id == anders["id"])
    assert tekst_rij.value_text == "Op reis"


# ── 3. Leeg blijft leeg ──────────────────────────────────────────────────────

@pytest.mark.parametrize("tekst", ["", "   "])
def test_een_lege_anders_tekst_levert_geen_antwoord_op(client, admin_headers,
                                                       db_session, tekst):
    """Geen lege rijen. Zonder deze test zou "tekst telt mee" een veld met een
    spatie erin als beantwoord kunnen laten gelden."""
    form, veld, _anders, _gewoon = _bouw(client, admin_headers, "checkbox")

    resp = _verstuur(client, form, veld, tekst=tekst)
    assert resp.status_code == 200, resp.text
    assert _rijen(db_session, veld["id"]) == []


# ── 4. De verplicht-regel schuift mee, maar niet te ver ──────────────────────

def test_een_verplicht_veld_is_ingevuld_met_alleen_anders_tekst(client, admin_headers,
                                                                db_session):
    """`has_value` bepaalt óók of een verplicht veld ingevuld is. Nu de tekst
    meetelt, is een verplicht veld met alleen "Anders" geldig — en dat hoort."""
    form, veld, anders, _gewoon = _bouw(client, admin_headers, "checkbox",
                                        verplicht=True)

    resp = _verstuur(client, form, veld, tekst="Op reis")
    assert resp.status_code == 200, resp.text
    rijen = _rijen(db_session, veld["id"])
    assert len(rijen) == 1 and rijen[0].value_option_id == anders["id"]


def test_een_verplicht_veld_blijft_leeg_met_een_lege_anders_tekst(client, admin_headers,
                                                                  db_session):
    """De grens aan de andere kant. Zonder deze test zou "tekst telt mee" de
    verplicht-controle stilletjes kunnen uitschakelen."""
    form, veld, _anders, _gewoon = _bouw(client, admin_headers, "checkbox",
                                         verplicht=True)

    resp = _verstuur(client, form, veld, tekst="   ")
    assert "verplicht" in resp.text.lower(), resp.text
    assert _rijen(db_session, veld["id"]) == []


# ── 5. Tekst zonder "Anders"-optie is geen antwoord ──────────────────────────

def test_tekst_op_een_veld_zonder_anders_optie_wordt_genegeerd(client, admin_headers,
                                                               db_session):
    """Er is dan geen optie om de tekst aan te hangen.

    Zonder deze voorwaarde zou zo'n post `has_value` waar maken en verderop
    breken op `option_ids[0]` — een 500 in plaats van een genegeerd veld.
    """
    payload = {
        "title": "Zonder Anders", "status": "open",
        "fields": [{"field_type": "radio", "label": "Kies", "position": 0,
                    "options": [{"label": "A", "position": 0},
                                {"label": "B", "position": 1}]}],
    }
    form = client.post("/api/v1/forms", json=payload, headers=admin_headers).json()
    veld = form["fields"][0]

    resp = _verstuur(client, form, veld, tekst="iets")
    assert resp.status_code == 200, resp.text
    assert _rijen(db_session, veld["id"]) == []


# ── 6. Het scherm nodigt niet meer uit tot iets wat het weggooit ─────────────

def test_het_scherm_koppelt_de_tekst_aan_het_vinkje(client, admin_headers):
    """Typen vinkt aan, en zodra "Anders" niet meer gekozen is wist het veld zich.

    Een bronregel, want gedrag bewijst hier niets: de server neemt de optie sinds
    #683 tóch mee, dus een submit slaagt met of zonder deze JS. Wat ze toevoegt is
    dat het scherm en de server hetzelfde zeggen terwijl je zit te typen.
    """
    form, veld, _anders, _gewoon = _bouw(client, admin_headers, "checkbox")
    html = client.get(f"/formulier/{form['share_token']}").text

    assert 'x-ref="anders"' in html and 'x-ref="keuze"' in html
    assert "$refs.keuze.checked" in html, "typen vinkt niet aan"
    assert "$refs.anders.value = ''" in html, "uitvinken laat de tekst staan"


# ── 7. Het veld is breed genoeg om na te lezen (#687) ────────────────────────

def _anders_input(html: str, veld_id: int) -> str:
    """De <input>-tag van het "Anders"-veld, als losse string."""
    merk = f'id="f{veld_id}_other"'
    start = html.rindex("<input", 0, html.index(merk))
    return html[start:html.index(">", html.index(merk))]


@pytest.mark.parametrize("veldtype", ["checkbox", "radio"])
def test_het_anders_veld_vult_de_rest_van_de_rij(client, admin_headers, veldtype):
    """Een ontbrekende klasse, dus de UI-conventiegate vangt dit niet: die kijkt
    naar verboden klassen, niet naar afwezige. Zonder deze test verdwijnt de
    breedte bij de volgende bewerking van dit blok zonder dat iets rood wordt.

    Waarom het meer is dan opmaak: sinds #683 wordt die tekst écht bewaard, en
    "Anders" is de enige plek in het formulier waar het antwoord uit het hoofd van
    de invuller komt. Dat is het slechtste veld om te laten scrollen — je kunt niet
    nalezen wat je schreef vóór je verstuurt.

    Beide takken, want het is dezelfde regel twee keer (net als de twee lekken in
    #683 zelf).
    """
    form, veld, _anders, _gewoon = _bouw(client, admin_headers, veldtype)
    html = client.get(f"/formulier/{form['share_token']}").text

    tag = _anders_input(html, veld["id"])
    assert "flex-1" in tag, f"het veld groeit niet mee met de rij: {tag}"
    assert "min-w-0" in tag, (
        "zonder min-w-0 weigert een flex-item onder zijn intrinsieke breedte te "
        f"krimpen en loopt het alsnog over: {tag}")
    assert "<textarea" not in tag, "één regel per optie is de opzet van deze lijst"


@pytest.mark.parametrize("veldtype", ["checkbox", "radio"])
def test_de_optierij_mag_afbreken_op_een_smal_scherm(client, admin_headers, veldtype):
    """De keerzijde van een volle-breedte veld: een lang optielabel plus dat veld
    moet kunnen afbreken in plaats van buiten de kaart te lopen."""
    form, veld, _anders, _gewoon = _bouw(client, admin_headers, veldtype)
    html = client.get(f"/formulier/{form['share_token']}").text

    merk = f'id="f{veld["id"]}_other"'
    label_start = html.rindex("<label", 0, html.index(merk))
    label_tag = html[label_start:html.index(">", label_start)]
    assert "flex-wrap" in label_tag, label_tag
