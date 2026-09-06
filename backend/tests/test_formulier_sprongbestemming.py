"""#699 — de sprongbestemming hoort in één keuzelijst.

Er stonden twee bedieningen voor één beslissing: een `<select>` met secties plus een
los vakje "einde". De vraag is er één — waar gaat dit naartoe — met drie antwoorden:
gewone volgorde, een latere sectie, of het einde.

**Het splitsen maakte een onmogelijke toestand mogelijk, en dat is geen theorie.**
`update_option` schreef beide kolommen zonder ze tegen elkaar af te wegen. Kies een
sectie én vink "einde" aan, en beide werden bewaard — waarna `_target()` in
`formulier.html` het einde stil liet winnen (`if (sk.end) return 'end';` staat vóór
de sectiecontrole). De beheerder zag zijn sectie staan en het formulier deed iets
anders.

**Test 1 hieronder is daarom de belangrijkste: ze kijkt naar de OPGESLAGEN
TOESTAND** na een post die allebei meestuurt. Een test op het formulier alleen
bewijst niets over wat de server bewaart, en daar ging het stil mis.

De keuzelijst biedt alleen látere secties aan — niet aanbieden wat verboden is, is
beter dan het achteraf weigeren. De servercontrole blijft er wél: het scherm maakt
de fout onmogelijk, de service weigert hem alsnog. Dat is geen dubbelop maar de twee
lagen uit de architectuurregel: vorm bij de ingang, betekenis in de service.
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
        "title": "Sprong", "status": "draft",
        "sections": [{"title": "Een", "position": 0},
                     {"title": "Twee", "position": 1},
                     {"title": "Drie", "position": 2}],
        "fields": [{"field_type": "radio", "label": "Kies", "position": 0,
                    "section_index": 0,
                    "options": [{"label": "A", "position": 0},
                                {"label": "B", "position": 1}]}],
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _optie(form, label):
    return next(o for o in form["fields"][0]["options"] if o["label"] == label)


def _lees(client, admin_headers, form_id):
    return client.get(f"/api/v1/forms/{form_id}", headers=admin_headers).json()


# ── 1. De opgeslagen toestand ───────────────────────────────────────────────

def test_de_service_weigert_sectie_en_einde_tegelijk(client, admin_headers,
                                                     db_session):
    """De onmogelijke toestand, getoetst op wat er in de databank staat.

    De keuzelijst kan dit niet meer versturen, maar de regel hoort in de service:
    de JSON-import spreekt diezelfde twee kolommen, en die komt niet langs het
    scherm.
    """
    from app.domains.forms.api import FormulierFout, update_option
    from app.domains.forms.models import Form, FormFieldOption

    form_json = _formulier(client, admin_headers)
    a = _optie(form_json, "A")
    derde = sorted(form_json["sections"], key=lambda s: s["position"])[2]
    form = db_session.get(Form, form_json["id"])

    with pytest.raises(FormulierFout):
        update_option(db_session, form, a["id"], label="A",
                      skip_to_section_id=str(derde["id"]), skip_to_end=True)

    # Géén `db_session.rollback()`: de testsessie draait op een savepoint, dus een
    # rollback wist óók de fixture — dezelfde val als in #681. De service werpt
    # vóór ze iets wegschrijft, dus er is niets terug te draaien.
    db_session.expire_all()
    bewaard = db_session.get(FormFieldOption, a["id"])
    assert bewaard.skip_to_section_id is None and bewaard.skip_to_end is False, (
        "er is een onmogelijke toestand bewaard")


def test_via_het_scherm_kan_er_maar_een_bestemming_zijn(client, admin_headers,
                                                        db_session):
    """Wat het scherm post is één waarde, dus de combinatie kan niet ontstaan."""
    from app.domains.forms.models import FormFieldOption

    form = _formulier(client, admin_headers)
    csrf = _login(client)
    a = _optie(form, "A")
    derde = sorted(form["sections"], key=lambda s: s["position"])[2]

    resp = client.post(f"/admin/formulieren/{form['id']}/opties/{a['id']}",
                       data={"label": "A", "bestemming": str(derde["id"])},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200, resp.text[:300]

    db_session.expire_all()
    bewaard = db_session.get(FormFieldOption, a["id"])
    assert bewaard.skip_to_section_id == derde["id"]
    assert bewaard.skip_to_end is False, "het einde staat er óók bij"


def test_einde_kiezen_wist_een_eerdere_sectie(client, admin_headers, db_session):
    """De omgekeerde volgorde: van een sectie naar het einde mag geen restant
    achterlaten dat later stil de doorslag geeft."""
    from app.domains.forms.models import FormFieldOption

    form = _formulier(client, admin_headers)
    csrf = _login(client)
    a = _optie(form, "A")
    derde = sorted(form["sections"], key=lambda s: s["position"])[2]

    client.post(f"/admin/formulieren/{form['id']}/opties/{a['id']}",
                data={"label": "A", "bestemming": str(derde["id"])},
                headers={"X-CSRF-Token": csrf})
    client.post(f"/admin/formulieren/{form['id']}/opties/{a['id']}",
                data={"label": "A", "bestemming": "end"},
                headers={"X-CSRF-Token": csrf})

    db_session.expire_all()
    bewaard = db_session.get(FormFieldOption, a["id"])
    assert bewaard.skip_to_end is True
    assert bewaard.skip_to_section_id is None, "de oude sectie staat er nog"


def test_gewone_volgorde_wist_allebei(client, admin_headers, db_session):
    from app.domains.forms.models import FormFieldOption

    form = _formulier(client, admin_headers)
    csrf = _login(client)
    a = _optie(form, "A")

    client.post(f"/admin/formulieren/{form['id']}/opties/{a['id']}",
                data={"label": "A", "bestemming": "end"},
                headers={"X-CSRF-Token": csrf})
    client.post(f"/admin/formulieren/{form['id']}/opties/{a['id']}",
                data={"label": "A", "bestemming": ""},
                headers={"X-CSRF-Token": csrf})

    db_session.expire_all()
    bewaard = db_session.get(FormFieldOption, a["id"])
    assert bewaard.skip_to_end is False and bewaard.skip_to_section_id is None


# ── 2. Hetzelfde één niveau hoger ───────────────────────────────────────────

def test_een_sectie_kent_dezelfde_ene_bestemming(client, admin_headers, db_session):
    """Anders is de bouwer op twee plekken verschillend voor hetzelfde begrip."""
    from app.domains.forms.models import FormSection

    form = _formulier(client, admin_headers)
    csrf = _login(client)
    secties = sorted(form["sections"], key=lambda s: s["position"])

    resp = client.post(
        f"/admin/formulieren/{form['id']}/secties/{secties[0]['id']}",
        data={"title": "Een", "bestemming": "end"},
        headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200, resp.text[:300]

    db_session.expire_all()
    bewaard = db_session.get(FormSection, secties[0]["id"])
    assert bewaard.next_is_end is True and bewaard.next_section_id is None


# ── 3. Wat de keuzelijst aanbiedt ───────────────────────────────────────────

def test_de_lijst_biedt_alleen_latere_secties_aan(client, admin_headers):
    """Niet aanbieden wat verboden is. Het veld staat in sectie 1, dus alleen 2 en 3
    horen erin te staan — en "einde"."""
    form = _formulier(client, admin_headers)
    _login(client)
    html = client.get(f"/admin/formulieren/{form['id']}").text
    secties = sorted(form["sections"], key=lambda s: s["position"])

    start = html.index('name="bestemming"')
    lijst = html[start:html.index("</select>", start)]
    assert f'value="{secties[0]["id"]}"' not in lijst, "de eigen sectie staat erin"
    assert f'value="{secties[1]["id"]}"' in lijst
    assert f'value="{secties[2]["id"]}"' in lijst
    assert 'value="end"' in lijst


def test_er_is_geen_los_einde_vakje_meer(client, admin_headers):
    form = _formulier(client, admin_headers)
    _login(client)
    html = client.get(f"/admin/formulieren/{form['id']}").text

    assert 'name="skip_to_end"' not in html, "het losse vakje staat er nog"
    assert 'name="next_is_end"' not in html, "en bij de sectie ook"


# ── 4. De optierij is inline ────────────────────────────────────────────────

def test_de_optierij_heeft_geen_bewerktoggle_meer(client, admin_headers):
    """Drie klikken voor één handeling, en een rij die er in twee toestanden anders
    uitzag. De velden staan nu altijd zichtbaar."""
    form = _formulier(client, admin_headers)
    _login(client)
    html = client.get(f"/admin/formulieren/{form['id']}").text

    assert "oedit" not in html, "de bewerktoggle van de optierij staat er nog"
    assert 'aria-label="Optie bewerken"' not in html
    # De velden staan er wél, en dus zonder x-show eromheen.
    assert 'name="label"' in html and 'name="is_other"' in html


def test_er_wordt_niet_automatisch_bewaard_bij_change(client, admin_headers):
    """Bewust niet: elke post rendert `#fb-detail` opnieuw, dus bij het verlaten van
    een tekstveld zou de focus springen en de scroll verschuiven. Dat vraagt eerst
    een gerichter swapdoel, en dat is een andere wijziging."""
    form = _formulier(client, admin_headers)
    _login(client)
    html = client.get(f"/admin/formulieren/{form['id']}").text

    start = html.index('name="bestemming"')
    vorm = html[html.rindex("<form", 0, start):html.index("</form>", start)]
    assert 'hx-trigger="change' not in vorm, vorm[:200]
