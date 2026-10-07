"""The lossless migration of a page's HTML into a document (CR-17 phase 1,
#1671; C6 tests 1 and 12).

The honesty of "lossless" is a measurement: `render_document(parse_html(
content))` must equal what the page shows today (`render_cms_content` with
`on_page=True`). These tests pin that for the shapes Trix-era pages carry —
and for the shapes that do not convert, with F11's gentle draft as the
consequence. The comparison runs through `normalise_html` (ONE source, review
B4e): it collapses whitespace that contains a newline — layout between
blocks — and keeps a single space between inline tags, so a lost space turns
the measurement red (review A3, #1673).

Every test here can go red: remove the heading shift, the `del` spelling or
the space preservation and the comparisons fall over.
"""

import pytest

from app.domains.cms.parse import normalise_html, parse_html
from app.domains.cms.render import render_cms_content, render_document
from app.domains.cms.schema import validate_document


def _today(content):
    """What the page shows today: the old public path, called as `ui.py`."""
    return render_cms_content(content, None, on_page=True)


@pytest.mark.parametrize(
    "content",
    [
        # A plain paragraph.
        "<p>Welcome to the association.</p>",
        # Headings: stored as the author chose them (1-3), shown one level
        # down on a page (#1656).
        "<h1>Kop</h1><h2>Subkop</h2><h3>Kleine kop</h3><p>Tekst</p>",
        # Lists.
        "<ul><li>Eén</li><li>Twee</li></ul><ol><li>Eerst</li><li>Daarna</li></ol>",
        # Marks: bold, italic, strike (Trix spells strike as <del>), a link —
        # and the SPACE between two marks: content, not layout (review A3).
        "<p><strong>vet</strong> <em>cursief</em> <del>doorgehaald</del> "
        '<a href="https://example.test">een link</a></p>',
        # A hard line break inside a paragraph (Trix' break).
        "<p>Regel één<br>Regel twee</p>",
        # A table with a header row, as typed through the HTML door.
        "<table><thead><tr><th>Wat</th><th>Prijs</th></tr></thead>"
        "<tbody><tr><td>Koffie</td><td>€1,00</td></tr></tbody></table>",
        # The five configuration codes stay TEXT; the renderer replaces them
        # as it does today (the value block is phase 5, #1671).
        "<p>Het lidgeld bedraagt {{membership_price_full}} vanaf {{half_price_start}}.</p>",
        # A form button (#1567) still works: the code stays text and the
        # renderer builds the button around it.
        "<p>{{form:berichten|Schrijf ons}}</p>",
    ],
)
def test_the_migration_is_honest(content):
    """render(parse(html)) equals what the page shows today (C6 12)."""
    document = parse_html(content, on_page=True)
    assert document is not None, f"page does not convert: {content!r}"
    validate_document(document)
    assert normalise_html(render_document(document, None, on_page=True)) == normalise_html(
        _today(content)
    )


def test_a_lost_space_turns_the_measurement_red():
    """The space between two marks is content (review A3, #1673): dropping it
    from the document changes the rendered HTML, and the comparison sees it —
    proven by the very case that stayed green before, because the old
    `_normalise` collapsed it on both sides."""
    content = "<p><strong>vet</strong> <em>cursief</em></p>"
    document = parse_html(content, on_page=True)
    # The document carries the space as a text node.
    texts = [n["text"] for n in document["content"][0]["content"]]
    assert " " in texts, "the space between the marks is gone from the document"
    assert (
        render_document(document, None, on_page=True)
        == "<p><strong>vet</strong> <em>cursief</em></p>"
    )


def test_the_table_survives_an_edit():
    """C6 1: a table saved, reloaded, one cell changed, saved again — the
    documents differ in exactly that cell."""
    document = parse_html(
        "<table><thead><tr><th>Wat</th></tr></thead>"
        "<tbody><tr><td>Koffie</td></tr><tr><td>Thee</td></tr></tbody></table>"
    )
    table = document["content"][0]
    cell = table["content"][1]["content"][0]
    text = cell["content"][0]["content"][0]
    assert text["text"] == "Koffie"
    text["text"] = "Koffie met melk"
    assert render_document(document, None) == (
        "<table><thead><tr><th>Wat</th></tr></thead>"
        "<tbody><tr><td>Koffie met melk</td></tr><tr><td>Thee</td></tr></tbody></table>"
    )


def test_a_page_that_does_not_convert_keeps_her_html():
    """A quote is not in the schema (C4.2): the page does not convert
    losslessly — strict yields None, and the site keeps serving her HTML."""
    assert parse_html("<blockquote>Een citaat van iemand.</blockquote>", on_page=True) is None


def test_the_gentle_draft_keeps_the_words_in_both_orders():
    """F11: the lenient parse yields a draft with the page's words — before a
    paragraph (the old test) and after it (the case the review found lost,
    A2 #1673)."""
    for content in (
        "<blockquote>Een citaat van iemand.</blockquote><p>En een alinea.</p>",
        "<p>En een alinea.</p><blockquote>Een citaat van iemand.</blockquote>",
    ):
        document = parse_html(content, on_page=True, lenient=True)
        assert document is not None
        validate_document(document)
        words = render_document(document, None, target="text")
        assert "citaat van iemand" in words
        assert "En een alinea." in words


def test_the_gentle_draft_keeps_a_loose_tail():
    """A2 (#1673): text after the last closed block belongs in the draft —
    before the final flush it was lost."""
    document = parse_html("<p>Een alinea.</p>Losse staart", on_page=True, lenient=True)
    words = render_document(document, None, target="text")
    assert "Losse staart" in words


def test_a_code_stays_text_and_is_replaced_anyway():
    """The document keeps the code as text (the value block is phase 5); the
    renderer replaces it with the current value, as today."""
    document = parse_html("<p>Het lidgeld: {{membership_price_full}}</p>", on_page=True)
    texts = [node["text"] for node in document["content"][0]["content"] if node["type"] == "text"]
    assert any("{{membership_price_full}}" in t for t in texts), "the code is not text"
    html = render_document(document, None, on_page=True)
    assert "{{membership_price_full}}" not in html
    assert "€" in html


def test_a_fragment_without_the_heading_shift():
    """The home-intro block renders without `on_page`: the heading keeps its
    own level — the document stores the choice, the place picks the tag
    (C4.2, one shift source: `headings_one_level_down`)."""
    assert render_document(parse_html("<h1>Kop</h1>", on_page=False), None) == "<h1>Kop</h1>"
    assert (
        render_document(parse_html("<h1>Kop</h1>", on_page=True), None, on_page=True)
        == "<h2>Kop</h2>"
    )


def test_the_text_rendering_gives_words():
    """The chatbot reads a page as text (C2 cms, Readers): no tags, a code its
    value, a figure its alt text."""
    document = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": "Kop"}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Het lidgeld: {{membership_price_full}}"}],
            },
            {
                "type": "figure",
                "attrs": {"media_id": 3, "alt": "Het lokaal", "placement": "full"},
            },
        ],
    }
    text = render_document(document, None, target="text")
    assert "<" not in text
    assert "Kop" in text
    assert "Het lokaal" in text
    assert "€" in text
    assert "{{" not in text


def test_a_div_page_keeps_her_html_and_her_words_in_the_draft():
    """No legacy flags (Koen, 6 October 2026): a Trix <div> paragraph renders
    as a <p> in the document, so the page is not byte-equal - strict refuses
    and the site keeps serving her HTML; the gentle draft holds her words."""
    content = "<div>Eerste alinea.</div><div>Tweede alinea.</div>"
    assert parse_html(content, on_page=True) is None
    document = parse_html(content, on_page=True, lenient=True)
    words = render_document(document, None, target="text")
    assert "Eerste alinea." in words
    assert "Tweede alinea." in words


def test_a_picture_page_keeps_her_html_and_gets_a_draft():
    """No legacy sizes: a Trix-era picture carries a class the kit does not
    render, so the page keeps her HTML; the gentle draft still describes the
    figure by its media id."""
    content = (
        '<figure data-trix-attachment="{&quot;contentType&quot;:&quot;image/png&quot;,'
        "&quot;url&quot;:&quot;/api/v1/media/12&quot;,&quot;width&quot;:800,"
        "&quot;height&quot;:600,&quot;alt&quot;:&quot;Het lokaal&quot;,"
        '&quot;size&quot;:&quot;half&quot;}"><img src="/api/v1/media/12" '
        'width="800" height="600"></figure>'
    )
    assert parse_html(content, on_page=True) is None
    document = parse_html(content, on_page=True, lenient=True)
    assert document is not None
    assert document["content"][0]["type"] == "figure"
    assert document["content"][0]["attrs"]["media_id"] == 12


def test_the_gentle_draft_loses_no_word_after_a_block_inside_a_div():
    """The two A2 edges of the second review (#1673): text that follows a
    block INSIDE a div left the gentle draft. The plain-text net catches both
    - a draft with fewer words than the page falls back to her words."""
    for content in (
        "<div><h2>Kop</h2><ul><li>a</li></ul>tekst</div>",
        "<div>buiten<div>binnen</div>staart</div>",
    ):
        document = parse_html(content, on_page=True, lenient=True)
        words = render_document(document, None, target="text")
        assert "tekst" in words or "staart" in words, f"words lost from: {content}"
        for word in ("Kop", "a", "buiten", "binnen"):
            if word in content:
                assert word in words, f"{word} lost from: {content}"


def test_plain_text_document_keeps_every_word_per_block():
    """The net itself (the master CLI's advice, #1673): plain text cannot
    fail - every block's words become one plain paragraph."""
    from app.domains.cms.parse import plain_text_document

    document = plain_text_document("<h2>Kop</h2><p>Een alinea.</p>rest tekst")
    texts = [n["content"][0]["text"] for n in document["content"]]
    assert texts == ["Kop", "Een alinea.", "rest tekst"]


def test_plain_text_document_joins_no_words_across_an_unclosed_block():
    """The net sanitises its input before it splits (review 3, #1673).

    Broken on purpose before the fix, exactly on the reviewer's input: the
    migration's guard hands the net RAW content, and with ``drie`` inside an
    unclosed ``<li>`` nothing separated it from ``vier`` — the draft held
    "drievier". Sanitising first, like ``parse_html`` does, balances the
    HTML, so every block keeps its own words.
    """
    from app.domains.cms.parse import plain_text_document

    document = plain_text_document("<p>Een <b>twee</p><ul><li>drie</ul>vier &amp; vijf")
    texts = [n["content"][0]["text"] for n in document["content"]]
    assert texts == ["Een twee", "drie", "vier & vijf"]
