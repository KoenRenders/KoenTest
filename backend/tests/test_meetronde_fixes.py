"""Batch 1 van de meetronde-opvolging (#996 — reviewronde 2 op #785).

De zes door Koen goedgekeurde punten: twee gemeten bugs (F2 draaitabel,
F25 kitpagina-breedte), drie afwerkingsfixes (F24 contactzin, F30
conceptbadge, F34 ledensamenvatting) en F3 (lidgeld zichtbaar op Word-lid).
"""

import re

import pytest
pytestmark = pytest.mark.ui_serverrendered

from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, make_session_value


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def test_F2_subtotaalrij_vult_tot_de_totaalkolom(client):
    """Gemeten bug: de subtotaalrij droeg geen cellen voor de jaarkolommen,
    dus het groepstotaal (37) rendert onder "2025". Na de fix telt de rij
    evenveel datacellen als de kolommen vragen: 1 opvuller (colspan) +
    2 lege jaarcellen + 1 totaal = 4. Vóór de fix waren het er 2 —
    rood-bewijsbaar door de opvulling weer weg te halen."""
    _login(client)
    html = client.get("/admin/design-system").text
    rij = re.search(r"<tr[^>]*>(?:(?!</tr>).)*Subtotaal — Mol(?:(?!</tr>).)*</tr>",
                    html, re.S)
    assert rij, "subtotaalrij van de kitdemo niet gevonden"
    assert rij.group(0).count("<td") == 4


def test_F25_kitdemo_tabel_zit_in_een_scrollcontainer(client):
    """Gemeten bug: dit voorbeeld stond zonder overflow-container en rekte de
    kitpagina op mobiel tot 601px op — §2.3 geldt ook voor de kit zelf."""
    _login(client)
    html = client.get("/admin/design-system").text
    assert 'id="ds-lijst" class="mt-3 overflow-x-auto"' in html


def test_F30_conceptbadge_is_grijs():
    """Concept is een ontwerpstatus, geen openstaande handeling (§2.5)."""
    from pathlib import Path

    # Sinds F15 draagt de recordkop de statusbadge.
    bron = (Path(__file__).resolve().parents[1] / "app" / "domains" / "forms"
            / "templates" / "_fb_recordkop.html").read_text()
    assert '_("concept"), "gray"' in bron
    assert '_("concept"), "yellow"' not in bron


def test_F34_samenvatting_zonder_adres_en_met_enkelvoud(client, db_session):
    """Een gezin zonder adres toonde " , · " en één lid heette "1 personen"."""
    from app.domains.mdm.api import Member, MemberPerson, Person

    m = Member()
    db_session.add(m); db_session.flush()
    p = Person(first_name="Rita", last_name="Solo")
    db_session.add(p); db_session.flush()
    db_session.add(MemberPerson(member_id=m.id, person_id=p.id,
                                relation_type="HOOFDLID"))
    db_session.commit()
    _login(client)

    html = client.get("/admin/leden").text
    assert "1 persoon<" in html
    assert "1 personen" not in html
    # Geen wees-leestekens uit een leeg adres.
    assert " , " not in html


def test_F3_word_lid_toont_lidgeld_en_geldigheid(client, db_session):
    """Wie rechtstreeks binnenkomt zag nergens het tarief; nu staan bedrag en
    geldigheid bij de betaalkeuze — uit dezelfde helpers als de aanrekening."""
    from app.domains.payment.api import membership_price_for_date

    html = client.get("/lid-worden").text
    assert "Lidgeld" in html
    assert f"€ {membership_price_for_date()}".replace(".", ",") in html
    assert "geldig tot en met" in html
    # Ook op een foutpad (StrictUndefined): het sjabloon rendert opnieuw.
    from app.domains.auth.api import csrf_token_for

    waarde = make_session_value("x@example.com")
    r = client.post("/lid-worden", data={})
    assert r.status_code == 200
    assert "Lidgeld" in r.text


def test_F24_migratie_vervangt_de_contactzin(db_session):
    """De geseedde introtekst verwees naar een contactformulier dat de
    homepage niet heeft. De datastap vervangt alleen de exacte oude zin en
    laat een herschreven intro met rust; hij meldt het aantal geraakte
    rijen, zodat 'nul geraakt' nooit stil als succes doorgaat."""
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa

    pad = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
           / "132_home_intro_contact_button.py")
    spec = importlib.util.spec_from_file_location("migratie_132", pad)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    bind = db_session.connection()
    bind.execute(sa.text(
        "UPDATE cms.cms_pages SET content = :c WHERE slug = 'home-intro'"
    ).bindparams(c="<p>Eigen intro.</p>" + m.OUD))
    geraakt = m.vervang(bind)
    assert geraakt >= 1
    inhoud = bind.execute(sa.text(
        "SELECT content FROM cms.cms_pages WHERE slug = 'home-intro'")).scalar()
    assert m.OUD not in inhoud and m.NIEUW in inhoud
    assert inhoud.startswith("<p>Eigen intro.</p>")  # omliggende tekst blijft
    # Idempotent: nog eens draaien raakt niets meer.
    assert m.vervang(bind) == 0


def test_F15_formulier_heeft_recordtabs(client, db_session):
    """De twee grote navigatiekaarten zijn recordtabs geworden (golf-8-
    patroon): Formulier · Inzendingen N · Resultaten, op alle drie de
    pagina's; een htmx-verzoek naar de tabroutes blijft het kale fragment
    krijgen (de verwijder-swap hangt daarvan af)."""
    from app.domains.forms.api import Form

    f = Form(title="Tabtest", share_token="tabtest-token-xyz")
    db_session.add(f); db_session.commit()
    _login(client)

    basis = f"/admin/formulieren/{f.id}"
    bouwer = client.get(basis).text
    assert f'href="{basis}/inzendingen"' in bouwer and "Resultaten" in bouwer
    assert "Toon inzendingen" not in bouwer  # de oude kaarten zijn weg

    pagina = client.get(f"{basis}/inzendingen").text
    assert "Tabtest" in pagina and f'href="{basis}/resultaten"' in pagina
    fragment = client.get(f"{basis}/inzendingen",
                          headers={"HX-Request": "true"}).text
    assert "Resultaten" not in fragment  # kaal fragment, geen tabs/kop

    resultaten = client.get(f"{basis}/resultaten").text
    assert f'href="{basis}/inzendingen"' in resultaten
