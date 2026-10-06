"""Concept, gepubliceerd, geschiedenis — de toestanden van een pagina (CR-17
fase 1, snede 1, #1671; C6 tests 2, 4 en 6).

Snede 1 is de datalaag: op het scherm verandert niets, maar Opslaan onder de
nog zittende Trix-editor leidt de documenten opnieuw af uit `content`, zodat
ze niet verouderen. De kerninvarianten staan hier op serviceniveau: opslaan
schrijft het concept en niets anders; publiceren schrijft precies één
geschiedenisrij en maakt live; terugzetten schrijft alleen het concept.

Elke test hier kan rood worden: verplaats één toewijzing van `draft_json`
naar `published_json` en ze vallen om.
"""

import json

from app.domains.cms.api import (
    create_page,
    get_page_by_id,
    get_translation,
    publish,
    restore,
    save_draft,
    update_page,
    versions,
)
from app.domains.cms.models import CmsPageHistory
from app.schemas.cms import CmsPageCreate, CmsPageUpdate


def _pagina(db_session, **velden):
    standaard = dict(title="Testpagina", slug="testpagina-1671", is_published=False)
    standaard.update(velden)
    return create_page(db_session, CmsPageCreate(**standaard))


def _document(tekst="Hallo"):
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": tekst}],
            }
        ],
    }


def test_opslaan_schrijft_het_concept_en_niet_de_site(db_session):
    """C6 4: Opslaan laat `published_json` onveranderd."""
    page = _pagina(db_session, is_published=True)
    publish(db_session, page.id, by="eerste@admins")
    live = get_translation(db_session, page).published_json

    save_draft(db_session, page.id, _document("Gewijzigd"), by="redacteur@admins")

    translation = get_translation(db_session, page)
    assert translation.draft_json["content"][0]["content"][0]["text"] == "Gewijzigd"
    assert translation.published_json == live, "Opslaan heeft de live pagina veranderd"
    assert len(versions(db_session, page.id)) == 1, "Opslaan heeft een geschiedenisrij geschreven"


def test_publiceren_schrijft_precies_een_geschiedenisrij(db_session):
    """C4.3: Publiceren kopieert concept → gepubliceerd, met precies één
    geschiedenisrij — de vorige versie blijft terugzetbaar."""
    page = _pagina(db_session)
    save_draft(db_session, page.id, _document(), by="redacteur@admins")
    publish(db_session, page.id, by="redacteur@admins")

    rijen = db_session.query(CmsPageHistory).filter(CmsPageHistory.page_id == page.id).all()
    assert len(rijen) == 1
    assert rijen[0].action == "published"
    assert rijen[0].by == "redacteur@admins"
    assert get_page_by_id(db_session, page.id).is_published


def test_terugzetten_schrijft_het_concept_en_niet_de_site(db_session):
    """C6 6: Terugzetten zet een versie terug in het CONCEPT — de live pagina
    verandert pas na Publiceren."""
    page = _pagina(db_session)
    save_draft(db_session, page.id, _document("Versie één"), by="redacteur@admins")
    publish(db_session, page.id, by="redacteur@admins")
    save_draft(db_session, page.id, _document("Versie twee"), by="redacteur@admins")
    publish(db_session, page.id, by="redacteur@admins")
    live = get_translation(db_session, page).published_json

    oudste = versions(db_session, page.id)[-1]
    restore(db_session, page.id, oudste.id, by="redacteur@admins")

    translation = get_translation(db_session, page)
    assert translation.draft_json["content"][0]["content"][0]["text"] == "Versie één"
    assert translation.published_json == live, "Terugzetten heeft de live pagina veranderd"
    acties = [v.action for v in versions(db_session, page.id)]
    assert acties.count("restored") == 1


def test_een_onbekend_blok_wordt_met_naam_geweigerd(db_session):
    """C6 2, de poort bewezen met een overtreding: een document met een blok
    buiten het schema wordt geweigerd met de naam van het blok — nooit
    gestript, nooit stilletjes bewaard. (Dit is letterlijk AC10's "slider".)"""
    page = _pagina(db_session)
    document = {
        "type": "doc",
        "content": [{"type": "slider", "attrs": {"beelden": [1, 2]}}],
    }
    try:
        save_draft(db_session, page.id, document, by="redacteur@admins")
    except ValueError as exc:
        assert "slider" in str(exc), f"de naam van het blok ontbreekt in: {exc}"
    else:
        raise AssertionError("een onbekend blok is bewaard")
    # Het concept is onaangeroerd: niets is gestript of bewaard.
    assert get_translation(db_session, page).draft_json != document


def test_een_opslag_onder_trix_leidt_de_documenten_opnieuw_af(db_session):
    """Snede 1 (herziene opdracht, #1671): zolang Trix de pagina-editor is,
    leidt elke opslag het document opnieuw af uit `content` — de documenten
    kunnen niet verouderen. `published_json` volgt waar de pagina live staat;
    een code blijft tekst in het document."""
    page = _pagina(db_session, is_published=True, content="<p>Eerste tekst.</p>")
    update_page(
        db_session,
        page.id,
        CmsPageUpdate(content="<p>Tweede tekst met een {{membership_price_full}}.</p>"),
    )
    translation = get_translation(db_session, page)
    teksten = [
        n["text"] for n in translation.draft_json["content"][0]["content"] if n["type"] == "text"
    ]
    assert any("Tweede tekst" in t for t in teksten)
    assert any("{{membership_price_full}}" in t for t in teksten), "de code is geen tekst"
    assert translation.published_json is not None, "een live pagina volgt mee"


def test_een_niet_zuivere_opslag_krijgt_alleen_een_concept(db_session):
    """F11 onder de oude editor: content met een citaat zet niet verliesvrij
    om — het concept bewaart de woorden, `published_json` blijft leeg en de
    site blijft de HTML tonen tot een redacteur het concept publiceert."""
    page = _pagina(db_session, is_published=True, content="<p>Eerste tekst.</p>")
    update_page(
        db_session,
        page.id,
        CmsPageUpdate(content="<blockquote>Een citaat.</blockquote><p>En een alinea.</p>"),
    )
    translation = get_translation(db_session, page)
    assert translation.draft_json is not None
    assert translation.published_json is None


def test_het_concept_aanvaardt_zowel_json_string_als_dict(db_session):
    """De editor draagt het document als JSON-string; de service aanvaardt
    beide vormen zonder ze te vermengen."""
    page = _pagina(db_session)
    save_draft(db_session, page.id, json.dumps(_document()), by="redacteur@admins")
    assert get_translation(db_session, page).draft_json["type"] == "doc"


def test_titelwijziging_volgt_de_vertaalrij(db_session):
    """De vertaalrij is de bron van de titel; de paginakolom is zijn schaduw
    die meebeweegt zolang hij bestaat (C2 cms, één release)."""
    page = _pagina(db_session)
    update_page(db_session, page.id, CmsPageUpdate(title="Nieuwe titel"))
    translation = get_translation(db_session, page)
    assert translation.title == "Nieuwe titel"
    assert get_page_by_id(db_session, page.id).title == "Nieuwe titel"
