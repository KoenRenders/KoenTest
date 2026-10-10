"""On a public CMS page the page's title is the only h1 (#1656; CR-11 Q87).

Koen, 6 October 2026, on the page Werking on HDEV: the headings in the text
("Vergadering", "Activiteiten") stood as tall as the page's title. The editor
writes an `<h1>` for its highest heading, so a page with two headings had three
h1's — and the shell's page-title rule (40 px, an id in its selector) won from
the content rule (24 px, a class).

The renderer shows every heading of a page BODY one level down — h1 as h2, h2
as h3, h3 as h4 — and touches nothing else; the stored text keeps what the
editor wrote. The three levels stay three levels, under the page's title. The
editor's buttons read Kop · Subkop · Kleine kop (measured in the browser:
`tests_e2e/test_cms_page_headings.py`).

Broken on purpose (6 October 2026), each red for its own reason: `on_page` not
passed by the page route → three h1's on the page; the shift done level by
level instead of in one pass → an h1 arrives as an h4; the closing tag left
alone → `<h2>…</h1>`; `on_page` made the default → the home intro and the JSON
answer lose their h1; an h4 shifted too → no heading stays in the allowed range.
"""

import re

import pytest

from app.domains.cms.models import CmsPage
from app.domains.cms.render import headings_one_level_down, render_cms_content

pytestmark = pytest.mark.ui_serverrendered

BODY = (
    "<h1>Vergadering</h1><div>Elke maand.</div>"
    '<h1 class="x" id="act"><strong>Activiteiten</strong> en meer</h1><div>Het hele jaar.</div>'
    "<h2>Samen meer beleven</h2><div>Voor iedereen.</div>"
    "<h3>Praktisch</h3><div>Breng je fiets mee.</div>"
)


@pytest.mark.parametrize(
    ("html", "shown"),
    [
        ("<h1>Kop</h1>", "<h2>Kop</h2>"),
        ("<h2>Subkop</h2>", "<h3>Subkop</h3>"),
        ("<h3>Kleine kop</h3>", "<h4>Kleine kop</h4>"),
        # one pass: each level moves ONE step, whatever stands beside it
        ("<h1>A</h1><h2>B</h2><h3>C</h3>", "<h2>A</h2><h3>B</h3><h4>C</h4>"),
        ('<h1 class="x" id="y">Kop</h1>', '<h2 class="x" id="y">Kop</h2>'),
        (
            "<h1><strong>Vet</strong> en <em>schuin</em></h1>",
            "<h2><strong>Vet</strong> en <em>schuin</em></h2>",
        ),
        ("<H1>Kop</H1>", "<h2>Kop</h2>"),
        # what stays what it is
        ("<h4>Al klein</h4>", "<h4>Al klein</h4>"),
        (
            "<div>De h1 van de pagina, en &lt;h1&gt; in een zin.</div>",
            "<div>De h1 van de pagina, en &lt;h1&gt; in een zin.</div>",
        ),
        ("<h10>x</h10><h1x>y</h1x>", "<h10>x</h10><h1x>y</h1x>"),
        ("<div>Geen kop.</div>", "<div>Geen kop.</div>"),
    ],
)
def test_every_heading_is_shown_one_level_down_and_nothing_else_changes(html, shown):
    assert headings_one_level_down(html) == shown


def test_the_renderer_does_it_only_for_a_page_body_and_leaves_the_source(db_session):
    source = BODY
    on_page = render_cms_content(source, db_session, on_page=True)
    assert "<h1" not in on_page and "</h1>" not in on_page
    assert (on_page.count("<h2"), on_page.count("<h3"), on_page.count("<h4")) == (2, 1, 1)
    assert "<strong>Activiteiten</strong> en meer</h2>" in on_page, "what stands in it is kept"
    # rendering again starts from the source again: it does not shift twice
    assert render_cms_content(source, db_session, on_page=True) == on_page
    # not a page body: the home intro, the JSON answer, a block
    assert render_cms_content(source, db_session).count("<h1") == 2
    assert source == BODY and source.count("<h1") == 2, "the stored text is never touched"


def test_the_level_the_shift_arrives_at_is_allowed_in_the_output():
    """The sanitiser runs BEFORE the shift, on what was stored: an h4 need not be
    allowed as input for a Kleine kop to arrive as one."""
    assert "<h4>Klein</h4>" in render_cms_content("<h3>Klein</h3>", on_page=True)


def _page(db, slug: str, body: str = BODY, published: bool = True) -> CmsPage:
    page = CmsPage(title="Werking", slug=slug, content=body, is_published=published)
    db.add(page)
    db.commit()
    return page


def _main(html: str) -> str:
    return html[html.index("<main") : html.index("</main>")]


def test_the_public_page_has_one_h1_its_title(client, db_session):
    """Red on master: three — the title and the two headings of the text."""
    _page(db_session, "werking-1656")

    main = _main(client.get("/werking-1656").text)

    assert re.findall(r"<h1[^>]*>(.*?)</h1>", main, re.S) == ["Werking"]
    heads = re.findall(r"<(h[2-4])[^>]*>(.*?)</\1>", main, re.S)
    assert [(tag, re.sub(r"<[^>]+>", "", text)) for tag, text in heads] == [
        ("h2", "Vergadering"),
        ("h2", "Activiteiten en meer"),
        ("h3", "Samen meer beleven"),
        ("h4", "Praktisch"),
    ]
    assert 'class="prose-raak cms-page"' in main, "the page body does not carry its class"
    db_session.expire_all()
    stored = db_session.query(CmsPage).filter_by(slug="werking-1656").one().content
    assert stored == BODY, "showing the page changed what is stored"


def test_a_page_without_headings_is_rendered_as_it_was(client, db_session):
    body = "<div>Een alinea.</div><ul><li>Punt</li></ul><table><tbody><tr><td>cel</td></tr></tbody></table>"
    _page(db_session, "zonder-1656", body)
    main = _main(client.get("/zonder-1656").text)
    assert main.count("<h1") == 1
    assert render_cms_content(body, db_session, on_page=True) == render_cms_content(
        body, db_session
    )
    assert "<div>Een alinea.</div><ul><li>Punt</li></ul>" in main
