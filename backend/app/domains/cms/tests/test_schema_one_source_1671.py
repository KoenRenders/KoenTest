"""The schema is one source (CR-17 phase 1, slice 1, #1671; C6 test 2 and the
HTML half of 19).

The gate is proven by violations made during the build (noted in the
docstrings): a `schema_for("web")` call refused as an unknown set, a document
with the block "slider" refused with its name, and an attribute outside the
schema with "node.attribute".
"""

import pytest

from app.domains.cms import schema
from app.domains.cms.api import get_translation, list_pages, render_cms_content, render_document
from app.domains.cms.models import CmsPageHistory
from app.domains.cms.parse import normalise_html, parse_html

SEED_SLUGS = ("home-intro", "site-footer")


def test_schema_for_names_exactly_the_page_set():
    """The `page` set of phase 1: table and figure in the insert menu, NO
    value block (phase 5), the three heading levels, today's marks."""
    config = schema.schema_for("page")
    assert config["insert"] == ["table", "figure"]
    assert [h["level"] for h in config["headings"]] == [1, 2, 3]
    assert set(config["marks"]) == {"bold", "italic", "strike", "link"}
    assert config["nodes"] == sorted(schema.NODES)


def test_every_set_offers_only_nodes_the_schema_has():
    """Review B3 (#1673): a set may not offer what `validate_document`
    refuses — the letter set's phase-7 nodes join when phase 7 adds their
    shapes. This went red on `activity`, `calendar` and `closing`."""
    for set_name, config in schema.BLOCK_SETS.items():
        offered = set(config["insert"]) | set(config["lists"])
        unknown = offered - set(schema.NODES)
        assert not unknown, f"set {set_name} offers unknown nodes: {unknown}"


def test_an_unknown_set_is_an_error():
    """A set name is an identifier — an unknown set refuses, not a silent
    empty toolbar (C6 9's beginning)."""
    with pytest.raises(ValueError, match="web"):
        schema.schema_for("web")
    with pytest.raises(ValueError, match="web"):
        schema.validate_document({"type": "doc", "content": []}, "web")


def test_an_unknown_attribute_is_refused_with_its_name():
    """An attribute outside the schema refuses with the names of node and
    attribute (proven: a `placement="schuin"` refused as `figure.placement`)."""
    with pytest.raises(ValueError, match="figure.placement"):
        schema.validate_document(
            {
                "type": "doc",
                "content": [
                    {
                        "type": "figure",
                        "attrs": {"media_id": 1, "placement": "schuin"},
                    }
                ],
            }
        )


def test_the_seeded_pages_render_the_same_from_the_document(db_session):
    """The HTML half of C6 19: for every seeded page, the HTML from the
    document (migration 198's) equals the HTML from `content` on the old
    path — whitespace aside. A page that did not convert keeps her HTML and
    has no `published_json`; her draft holds her words."""
    pages = list(list_pages(db_session))
    assert pages, "no seeded pages found to measure the migration against"
    measured, equal, kept = 0, 0, 0
    for page in pages:
        measured += 1
        translation = get_translation(db_session, page)
        on_page = page.slug not in SEED_SLUGS
        today = normalise_html(render_cms_content(page.content or "", db_session, on_page=on_page))
        if translation is None or translation.published_json is None:
            kept += 1
            # The draft exists (F11) and holds the page's words.
            assert translation is not None and translation.draft_json is not None
            continue
        from_document = normalise_html(
            render_document(translation.published_json, db_session, on_page=on_page)
        )
        assert from_document == today, (
            f"page {page.slug}: the HTML from the document differs from today"
        )
        equal += 1
    # At least one page must have gone through the comparison — otherwise
    # this test measures nothing (the "it looks nowhere" trap).
    assert equal >= 1, "not a single page was measured as lossless"
    assert measured == equal + kept


def test_the_migration_wrote_a_history_row_for_each_published_page(db_session):
    """Review C2 (#1673): the version the migration publishes carries a
    history row, so the first "Terugzetten" has something to go back to."""
    published = [
        page
        for page in list_pages(db_session)
        if get_translation(db_session, page).published_json is not None
    ]
    assert published, "no published seeded pages to check"
    for page in published:
        rows = db_session.query(CmsPageHistory).filter(CmsPageHistory.page_id == page.id).all()
        assert rows, f"page {page.slug} is published without a history row"


def test_a_div_page_falls_back_to_her_html_with_her_words_in_the_draft():
    """No legacy flags (Koen, 6 October 2026): Trix <div> paragraphs do not
    convert byte-equal, so the page keeps her HTML - the visitor sees today's
    page - and her words stand in the draft for the editor."""
    content = "<div>Eerste alinea.</div><div>Tweede alinea.</div>"
    assert parse_html(content, on_page=True) is None, "a div page converts"
    draft = parse_html(content, on_page=True, lenient=True)
    assert "Eerste alinea." in render_document(draft, None, target="text")


def test_a_script_only_page_converts_to_empty_and_is_reported(db_session):
    """Review 4 (Koen, 7 October 2026): a page whose entire content the
    sanitiser drops converts to an EMPTY document — the visitor saw nothing
    either — and the migration's report names her, instead of silently
    filling the draft with script text.

    What this test proves (fifth look, #1673): the page converts through
    the NORMAL branch — the converter succeeds on the empty page, so the
    net is never called for her (measured: zero calls). The red proof here
    is the report: dropping the `empty` list from the counts fails this
    test. The raw-fallback red proof lives where the net itself runs, in
    `test_the_net_gives_an_empty_document_when_the_sanitiser_shows_nothing`.
    """
    import importlib.util
    import pathlib

    from app.domains.cms.models import CmsPage, CmsPageTranslation

    seeded = db_session.query(CmsPage).first()
    assert seeded, "no seeded page to take a tenant from"
    page = CmsPage(
        tenant_id=seeded.tenant_id,
        title="Script-only",
        slug="script-only-1671",
        content="<script>alert(1)</script>",
        is_published=False,
    )
    db_session.add(page)
    db_session.flush()

    versions = pathlib.Path(__file__).resolve().parents[4] / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "migration_200", versions / "200_2026_10_06_195129_pages_as_documents.py"
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    counts = migration._convert_pages(db_session.get_bind())
    assert f"{page.id} (script-only-1671)" in counts["empty"], "the report does not name her"
    translation = db_session.query(CmsPageTranslation).filter_by(page_id=page.id).one()
    assert translation.draft_json == {"type": "doc", "content": []}
    assert translation.published_json is None
