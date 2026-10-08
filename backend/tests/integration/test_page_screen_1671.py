"""The page screen as a record page of the kit (CR-17 phase 1, #1671,
slice 3).

The screen-level tests of the slice: what the author does on
`/admin/paginas/{id}` — save the document, publish it, go back to a
version, preview the draft — and what the visitor sees of each. The
service invariants (one history row per publish, restore into the draft)
stand in test_draft_publish_1671.py; here the ROUTES are the subject,
against a real HTTP client and the real templates.

Every test here can go red: the save-contract assertions fall over when
the 204-with-HX-Redirect becomes a fragment again, the site assertions
when a save reaches the published document, and the table test on the
old Trix screen, where a saved table came back flattened (measured,
CR-17's A1: Trix keeps no table).
"""

from __future__ import annotations

import html
import json
import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.cms.models import CmsPage
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _page(db, slug: str, title: str = "Een pagina", **fields) -> CmsPage:
    page = CmsPage(
        tenant_id=TENANT_MILLEGEM_ID,
        slug=slug,
        title=title,
        content=fields.pop("content", "<p>Oude tekst.</p>"),
        **{"is_published": True, "show_in_nav": False, **fields},
    )
    db.add(page)
    db.commit()
    return page


def _login(client) -> str:
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return session


def _picture(db) -> int:
    """A picture the picker offers (B1, #1734): an album photo with real
    bytes, of this tenant — the save checks the offer, so a test that posts
    an invented id tests the refusal, not the figure."""
    from app.domains.media.models import MediaAsset

    beeld = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    asset = MediaAsset(
        kind="activity_photo",
        title="Schermafdruk van de pagina",
        data=beeld,
        content_type="image/png",
        thumbnail=beeld,
        thumb_content_type="image/png",
        width=640,
        height=400,
        byte_size=len(beeld),
        sort_order=0,
        is_active=True,
    )
    db.add(asset)
    db.flush()
    return asset.id


def _save(client, session, page, document: dict, **extra) -> int:
    """Opslaan as the editor sends it: the document as JSON, the fields as
    fields. Title and slug are the page's own — the save really updates her."""
    response = client.post(
        f"/admin/paginas/{page.id}",
        data={
            "title": page.title,
            "slug": page.slug,
            "document": json.dumps(document),
            **extra,
        },
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    )
    return response.status_code


def _publish(client, session, page_id: int) -> int:
    return client.post(
        f"/admin/paginas/{page_id}/publiceren",
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    ).status_code


def _document(*blocks: dict) -> dict:
    return {"type": "doc", "content": list(blocks)}


def _deep_document(depth: int) -> dict:
    """A document nested `depth` levels deep (A4, #1734): one wrapper per
    level, a paragraph at the bottom."""
    node: dict = {"type": "paragraph", "content": [_paragraph("diep")]}
    for _ in range(depth):
        node = {"type": "doc", "content": [node]}
    return node


def _paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


#: The table exactly as the editor emits her (#1699's third look): the
#: cells carry her chrome (`colwidth`, `align` — the toolbar never offers
#: them, the site never shows them) and the ROWS carry no `section`; the
#: save adapter translates both to the stored document's dialect.
EDITOR_TABLE = {
    "type": "table",
    "content": [
        {
            "type": "tableRow",
            "content": [
                {
                    "type": "tableHeader",
                    "content": [_paragraph("Wat")],
                    "attrs": {"colwidth": [100], "align": "left"},
                }
            ],
        },
        {
            "type": "tableRow",
            "content": [{"type": "tableCell", "content": [_paragraph("Koffie")], "attrs": {}}],
        },
    ],
}


def test_the_record_page_carries_the_kit_s_screen(client, db_session):
    """The page screen is a record page: header with title and address, the
    document editor, the actions of the assignment — and no Trix anymore
    (her toolbar, her source toggle and her hand-built detail fragment
    left with her)."""
    _login(client)
    page = _page(db_session, "record-1671")

    # A page without a draft has nothing to publish — the button waits for
    # the first save; with a draft the head carries HER exact route.
    from app.domains.cms.api import save_document

    html = client.get(f"/admin/paginas/{page.id}").text
    assert "data-record-head" in html, "the kit's record header"
    assert 'href="/record-1671"' in html, "the page's address as a fact"
    assert "data-document-editor" in html, "the document editor"
    assert f'hx-post="/admin/paginas/{page.id}/publiceren"' not in html, (
        "a page without a draft carries a publish button"
    )
    save_document(db_session, page.id, _document(_paragraph("Eerste tekst.")))
    html = client.get(f"/admin/paginas/{page.id}").text
    assert f'hx-post="/admin/paginas/{page.id}/publiceren"' in html, "Publiceren"
    assert "/voorbeeld" in html, "Voorbeeld"
    assert "Geschiedenis" in html
    # The element, not the name: Trix stays in the SHELL for the newsletter
    # and the notes until phase 7, and her chrome may name her anywhere.
    assert "<trix-editor" not in html, "Trix left the page screen with slice 3"
    # The figure dialog travels with the macro: the picker of the kit, the
    # alternative text, the caption and the four placements of the set.
    assert "/admin/media/kiezer?" in html, "the kit's media picker"
    for word in ("Alternatieve tekst", "Bijschrift", "Plaatsing"):
        assert word in html, f"the figure dialog lost her {word}"
    # The placement words are the dialog's own buttons — not words anywhere
    # on the page (the review's B6, #1734).
    dialog = html[html.index("Plaatsing") : html.index("Op een smal scherm")]
    for placement in ("Vol", "Links", "Rechts", "Klein"):
        assert f">{placement}</button>" in dialog, f"the dialog lost the placement {placement}"
    # B5: the browser's prompt is gone from the link flow — the words of
    # the dialog are the kit's.
    assert "raak-link-edit" in client.get(f"/admin/paginas/{page.id}").text


def test_a_table_survives_the_save_and_reaches_the_site(client, db_session):
    """C6 1, red on the old screen: a table typed through the editor saves,
    comes back as a table, and publishes as one — with her header row.
    The posted shape is the editor's own emission, so this also proves the
    save adapter on the real route."""
    session = _login(client)
    page = _page(db_session, "tabel-1671")

    assert _save(client, session, page, _document(EDITOR_TABLE)) == 204

    editor = client.get(f"/admin/paginas/{page.id}").text
    # The stored document keeps the table — as the RECORD shows her to the
    # author (the hidden input carries the document the editor opens).
    hidden = re.search(r'id="cp-document-input"[^>]*value="([^"]*)"', editor)
    assert hidden, "the editor's hidden input is gone from the record page"
    # The attribute carries the document HTML-escaped; unescape before parsing.
    document = json.loads(html.unescape(hidden.group(1)))
    (table,) = document["content"]
    assert table["type"] == "table"
    head, body = table["content"]
    assert head["attrs"]["section"] == "head", "the adapter derived the header row"
    assert "colwidth" not in json.dumps(table), "the editor's chrome was dropped"

    assert _publish(client, session, page.id) == 204
    site = client.get("/tabel-1671").text
    assert "<table" in site and "<th>Koffie</th>" not in site
    assert "<th>Wat</th>" in site, "the header row reached the visitor"


def test_a_save_changes_nothing_on_the_site(client, db_session):
    """C6 4: Opslaan writes the draft. The site keeps her published
    document (or her stored HTML, before the first publish), and both the
    list and the record say 'concept gewijzigd'."""
    session = _login(client)
    page = _page(db_session, "concept-1671", content="<p>De oude woorden.</p>")

    assert _save(client, session, page, _document(_paragraph("De nieuwe woorden."))) == 204

    assert "De nieuwe woorden" not in client.get("/concept-1671").text, (
        "the site shows a word that was only saved"
    )
    assert "De oude woorden" in client.get("/concept-1671").text
    assert "concept gewijzigd" in client.get("/admin/paginas").text.lower(), (
        "the list lost her changed-draft badge"
    )
    record = client.get(f"/admin/paginas/{page.id}").text
    assert "Concept gewijzigd" in record, "the record lost her badge"
    assert "De nieuwe woorden" in record, "the editor opens the saved draft"

    assert _publish(client, session, page.id) == 204
    assert "De nieuwe woorden" in client.get("/concept-1671").text, (
        "publishing did not make the draft live"
    )


def test_the_preview_shows_the_draft_not_the_site(client, db_session):
    """C6 5: Voorbeeld is what the visitor WILL see — the draft, even while
    the site still shows the published words."""
    session = _login(client)
    page = _page(db_session, "voorbeeld-1671", content="<p>Wat er staat.</p>")

    _save(client, session, page, _document(_paragraph("Wat er komen gaat.")))
    _publish(client, session, page.id)
    _save(client, session, page, _document(_paragraph("Wat er straks staat.")))

    preview = client.get(f"/admin/paginas/{page.id}/voorbeeld").text
    assert "Wat er straks staat." in preview, "the preview shows the published words"
    assert "Wat er komen gaat." not in preview
    # The SITE keeps the published document — the draft never reaches her
    # without a publish.
    site = client.get("/voorbeeld-1671").text
    assert "Wat er komen gaat." in site, "the site lost her published words"
    assert "Wat er straks staat." not in site, "the site changed without a publish"


def test_restoring_writes_the_draft_and_not_the_site(client, db_session):
    """C6 6: Terugzetten puts the chosen version into the DRAFT; the site
    keeps the newer published document until the author publishes the
    restored draft."""
    session = _login(client)
    page = _page(db_session, "terug-1671", content="<p>Versie nul.</p>")

    _save(client, session, page, _document(_paragraph("Eerste versie.")))
    assert _publish(client, session, page.id) == 204
    _save(client, session, page, _document(_paragraph("Tweede versie.")))
    assert _publish(client, session, page.id) == 204
    assert "Tweede versie." in client.get("/terug-1671").text

    record = client.get(f"/admin/paginas/{page.id}").text
    version_ids = [int(vid) for vid in re.findall(r"/terugzetten/(\d+)", record)]
    assert sorted(version_ids) == sorted(set(version_ids)) and len(version_ids) == 2, (
        f"the history lost her rows: {version_ids}"
    )
    oldest = min(version_ids)

    restore = client.post(
        f"/admin/paginas/{page.id}/terugzetten/{oldest}",
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    )
    assert restore.status_code == 204

    assert "Tweede versie." in client.get("/terug-1671").text, "a restore changed the live page"
    record = client.get(f"/admin/paginas/{page.id}").text
    assert "Eerste versie." in record, "the draft did not become the restored version"
    assert "Concept gewijzigd" in record, "the record lost her restored-draft badge"


def test_a_figure_through_the_picker_reaches_the_site(client, db_session):
    """C6 7: a figure chosen in the dialog (the picker's media id, the
    alternative text, the caption, the placement) saves as a figure block
    and publishes with her placement class and her caption — the sanitiser
    keeps the wrapper (widened in this slice)."""
    session = _login(client)
    page = _page(db_session, "figuur-1671", title="Figuurtest")
    picture = _picture(db_session)

    figure = {
        "type": "figure",
        "attrs": {
            "media_id": picture,
            "alt": "Het lokaal",
            "placement": "right",
            "caption": "Ons lokaal",
        },
    }
    assert _save(client, session, page, _document(_paragraph("Tekst"), figure)) == 204
    assert _publish(client, session, page.id) == 204

    site = client.get("/figuur-1671").text
    assert "prose-figure--right" in site, "the placement class did not reach the site"
    assert "Ons lokaal</figcaption>" in site, "the caption did not reach the site"
    assert 'alt="Het lokaal"' in site, "the alternative text did not reach the site"
    # The reference, not a new media row: the page counts as a use of the
    # picture (CR-15 §C4.4) — deleting her is refused with this page named.
    from app.domains.media.api import uses_of

    uses = {use.label for use in uses_of(db_session, picture)}
    assert any("Figuurtest" in label for label in uses), (
        f"the figure is not a use of the picture: {uses}"
    )


# ── The review's findings on #1734, each pinned by its own test ────────────────


def test_a_json_update_no_longer_overwrites_the_documents(client, db_session):
    """A1: slice 1's derivation — documents re-made from `content` on every
    JSON update — left with Trix. A JSON call that flips `is_published` may
    still do that, but it may not replace what the editor saved."""
    session = _login(client)
    page = _page(db_session, "json-deur-1671")
    _save(client, session, page, _document(_paragraph("Wat de redacteur schreef.")))
    _publish(client, session, page.id)

    from app.domains.cms.api import draft_document, update_page
    from app.schemas.cms import CmsPageUpdate

    update_page(db_session, page.id, CmsPageUpdate(is_published=True))
    db_session.expire_all()
    draft = draft_document(db_session, db_session.get(CmsPage, page.id))
    assert "Wat de redacteur schreef." in json.dumps(draft), (
        "a JSON update replaced the editor's document with a parse of the old content"
    )


def test_a_refused_save_saves_nothing_and_keeps_the_authors_words(client, db_session):
    """A3: one save for the whole form. A document the schema refuses saves
    no fields either, and the screen re-opens with what the author POSTED —
    her words are not replaced by the stored draft."""
    session = _login(client)
    page = _page(db_session, "weigering-1671", title="Oudetitel", show_in_footer=False)

    refused = {"type": "doc", "content": [{"type": "slider"}]}
    response = client.post(
        f"/admin/paginas/{page.id}",
        data={
            "title": "Nieuwetitel",
            "slug": "weigering-1671",
            "document": json.dumps(refused),
            "show_in_footer": "1",
        },
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    )
    assert response.status_code == 200, "a refusal does not redirect"
    assert "Onbekend blok: slider" in response.text, "the refusal lost her name"
    db_session.expire_all()
    page = db_session.get(CmsPage, page.id)
    assert page.title == "Oudetitel", "the fields were saved despite the refusal"
    assert page.show_in_footer is False, "the switches were saved despite the refusal"
    # The editor re-opens the POSTED document, not the stored draft — read
    # her from the hidden input (her value is HTML-escaped in the attribute).
    hidden = re.search(r'id="cp-document-input"[^>]*value="([^"]*)"', response.text)
    assert hidden, "the editor's hidden input left the re-render"
    assert "slider" in html.unescape(hidden.group(1)), (
        "the author's posted document is gone from the screen"
    )

    # A document that does not even parse reads a readable refusal.
    response = client.post(
        f"/admin/paginas/{page.id}",
        data={"title": "Oudetitel", "slug": "weigering-1671", "document": "{geen json"},
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    )
    assert "Ongeldige documentopmaak." in response.text, response.text[:200]
    assert "Expecting" not in response.text, "the author reads Python's English"


@pytest.mark.parametrize(
    "document, naam",
    [
        # A4: the adapter ran before the validator and crashed on shapes the
        # validator refuses by name — a cell whose attrs is a list.
        (
            {
                "type": "doc",
                "content": [
                    {
                        "type": "table",
                        "content": [
                            {
                                "type": "tableRow",
                                "content": [
                                    {
                                        "type": "tableCell",
                                        "content": [_paragraph("Koffie")],
                                        "attrs": ["list"],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            "attrs",
        ),
        # A4: a document nested deeper than the cap — a RecursionError
        # before, a named refusal now.
        (_deep_document(2000), "Te diep genest"),
    ],
)
def test_a_malformed_document_is_refused_by_name_not_a_crash(client, db_session, document, naam):
    session = _login(client)
    page = _page(db_session, "misvormd-1671")
    response = client.post(
        f"/admin/paginas/{page.id}",
        data={"title": "Misvormd", "slug": "misvormd-1671", "document": json.dumps(document)},
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    )
    assert response.status_code == 200, "a named refusal, not a crash"
    assert naam in response.text, f"the refusal does not name her: {response.text[:200]}"


def test_a_picture_the_picker_does_not_offer_is_refused(client, db_session):
    """B1: the save checks the offer — a media id the picker would not show
    this tenant (here: a number nothing owns) publishes no broken picture."""
    session = _login(client)
    page = _page(db_session, "beeld-deur-1671")
    figure = {"type": "figure", "attrs": {"media_id": 987654, "alt": "Niets"}}

    response = client.post(
        f"/admin/paginas/{page.id}",
        data={
            "title": "Beeldduur",
            "slug": "beeld-deur-1671",
            "document": json.dumps(_document(figure)),
        },
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    )
    assert "Onbekende afbeelding: 987654" in response.text, response.text[:200]
    db_session.expire_all()
    # A3 with B1: the refusal saves NOTHING — the posted title did not land.
    assert db_session.get(CmsPage, page.id).title == "Een pagina", (
        "the fields were saved despite the refusal"
    )


def test_the_authors_markup_never_reaches_the_visitor_raw(client, db_session):
    """B6's pin: the author's hand in a link's address, in a figure's alt
    and caption — saved, published, and the visitor sees none of it raw."""
    session = _login(client)
    page = _page(db_session, "opmaak-1671")
    picture = _picture(db_session)
    document = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "marks": [{"type": "link", "attrs": {"href": "javascript:alert(1)"}}],
                        "text": "Een gevaarlijke link",
                    },
                    {"type": "text", "text": " en <b>rauwe</b> tekst."},
                ],
            },
            {
                "type": "figure",
                "attrs": {
                    "media_id": picture,
                    "alt": 'Het "lokaal" <i>van</i> de vereniging',
                    "caption": "Bijschrift met <b>opmaak</b>",
                },
            },
        ],
    }
    assert _save(client, session, page, document) == 204
    assert _publish(client, session, page.id) == 204

    site = client.get("/opmaak-1671").text
    body = site[site.index("cms-content") :]
    assert "javascript:" not in body, "the link's address reached the visitor"
    # The sanitiser may spell an attribute's value her own way (a `<` is
    # legal inside a quoted one and no markup to the browser); what the
    # visitor READS as the page's text may carry no raw markup. So: strip
    # the attributes' carriers (img tags) and demand clean text.
    text_only = re.sub(r"<img[^>]*>", "", body)
    assert "<b>rauwe</b>" not in text_only and "<b>opmaak</b>" not in text_only, (
        "the author's markup reached the visitor's text raw"
    )
    assert "&lt;b&gt;rauwe&lt;/b&gt;" in body, "the words survived, escaped"
    # And the alt cannot break OUT of her attribute: no unescaped quote of
    # her own stands inside the value.
    alt = re.search(r'alt="([^"]*)"', body)
    assert alt and 'alt="' not in alt.group(1), "the alt can break out of her attribute"


def test_offline_halen_takes_the_page_off_the_site_and_keeps_everything(client, db_session):
    """Koen's decision 1a on #1734: a live page leaves the site by her own
    action — the page, her draft and her published document all stay, and
    Publiceren puts her back with the same words. The confirmation says
    what she keeps (her own text: she is not a delete)."""
    session = _login(client)
    page = _page(db_session, "offline-1671")
    picture = _picture(db_session)
    figure = {"type": "figure", "attrs": {"media_id": picture, "alt": "Het lokaal"}}
    _save(client, session, page, _document(_paragraph("Tekst"), figure))
    _publish(client, session, page.id)
    record = client.get(f"/admin/paginas/{page.id}").text

    # The action stands in the head's menu, only on a live page, with her
    # own confirmation that names what she keeps.
    assert f'hx-post="/admin/paginas/{page.id}/offline-halen"' in record
    assert "Deze pagina van de site halen? De pagina zelf en haar concept blijven staan." in record

    response = client.post(
        f"/admin/paginas/{page.id}/offline-halen",
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    )
    assert response.status_code == 204

    db_session.expire_all()
    page = db_session.get(CmsPage, page.id)
    assert page.is_published is False, "the flag still stands"
    assert client.get("/offline-1671").status_code == 404, "the visitor still sees her"
    from app.domains.cms.api import draft_document, get_translation, publish

    assert "Tekst" in json.dumps(draft_document(db_session, page)), "the draft was lost"
    assert get_translation(db_session, page).published_json is not None, (
        "the published document was destroyed"
    )
    record = client.get(f"/admin/paginas/{page.id}").text
    assert "Offline" in record, "the record does not say she is offline"
    # The action waits until she is live again — an offline page has none.
    assert f'hx-post="/admin/paginas/{page.id}/offline-halen"' not in record

    # Publiceren puts her back with the same words.
    publish(db_session, page.id)
    db_session.expire_all()
    assert client.get("/offline-1671").status_code == 200, "she did not come back"
    site = client.get("/offline-1671").text
    assert "Tekst" in site and "prose-figure" in site, "she came back without her words"


def test_a_page_that_was_never_live_has_no_offline_action(client, db_session):
    """Decision 1a's counterpart: the action belongs to a LIVE page — a
    concept has nothing to take off the site."""
    _login(client)
    page = _page(db_session, "nooit-live-1671", is_published=False)
    record = client.get(f"/admin/paginas/{page.id}").text
    assert f'hx-post="/admin/paginas/{page.id}/offline-halen"' not in record


def test_the_json_update_refuses_content_and_the_flag(client, db_session, admin_headers):
    """Koen's decision 2a on #1734: the JSON door may no longer write the
    old HTML or the publication flag — the editor writes documents,
    publishing is the screen's action. A caller who still sends them is
    REFUSED (422), not silently ignored."""
    from app.domains.cms.api import create_page
    from app.schemas.cms import CmsPageCreate

    page = create_page(
        db_session,
        CmsPageCreate(title="Jsondeur", slug="jsondeur-1671", content="<p>Oude tekst.</p>"),
    )

    for forbidden in ({"content": "<p>nieuwe tekst</p>"}, {"is_published": False}):
        response = client.put(f"/api/v1/pages/{page.id}", json=forbidden, headers=admin_headers)
        assert response.status_code == 422, (
            f"{list(forbidden)[0]} rode along instead of being refused"
        )
        db_session.expire_all()
        assert db_session.get(CmsPage, page.id).content == "<p>Oude tekst.</p>", (
            "the refused field still wrote"
        )

    # The fields she may still write, write.
    response = client.put(
        f"/api/v1/pages/{page.id}", json={"title": "Jsondeur 2"}, headers=admin_headers
    )
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(CmsPage, page.id).title == "Jsondeur 2"
