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

    html = client.get(f"/admin/paginas/{page.id}").text
    assert "data-record-head" in html, "the kit's record header"
    assert 'href="/record-1671"' in html, "the page's address as a fact"
    assert "data-document-editor" in html, "the document editor"
    assert 'hx-post="/admin/paginas/' in html and "publiceren" in html, "Publiceren"
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
    for placement in ("Vol", "Links", "Rechts", "Klein"):
        assert placement in html, f"the dialog lost the placement {placement}"
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

    figure = {
        "type": "figure",
        "attrs": {
            "media_id": 3,
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

    uses = {use.label for use in uses_of(db_session, 3)}
    assert any("Figuurtest" in label for label in uses), (
        f"the figure is not a use of the picture: {uses}"
    )
