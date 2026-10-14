"""The draft of a page that came from the Trix editor keeps her blocks apart
(CR-17, #1770).

The comparison with the Trix editor (14 October 2026) published the draft of
a page with everything Trix can store and read the public page back: the
quotation and the code block had become ONE paragraph, their words glued
("Een citaat.code in een blok"), and the list inside a list was flat — three
items in a row.

The document has no code block, so the draft keeps one as a paragraph of
its own; since #1985 it has a quotation block, and the draft keeps a
quotation as one. A list inside a list it can keep: a list item holds
blocks.

The HTML below is what Trix writes for these blocks — a paragraph as a
`<div>`, a quotation as `<blockquote>`, a code block as `<pre>`, a nested
list inside its parent's `<li>` — written out here, not captured from a
browser in this test.

Broken on purpose (14 October 2026), each put back by the reverse edit: the
loose words not closed off where a quotation or a code block opens → "two
blocks' words are glued", and the loose words before a quotation are glued to
it; an inner list closed into the page instead of into its item → "the inner
list left its item"; the loose words after an inner list not closed off with
their item → they are gone from the item.
"""

from app.domains.cms.parse import parse_html
from app.domains.cms.render import render_document
from app.domains.cms.schema import validate_document

NESTED = "<ul><li>Eén<ul><li>Onder één</li><li>Ook onder één</li></ul></li><li>Twee</li></ul>"
TRIX_PAGE = (
    "<div>Een alinea.</div>"
    "<blockquote>Een citaat.</blockquote>"
    "<pre>code in een blok</pre>"
    "<blockquote>Nog een citaat.</blockquote>" + NESTED
)


def _words(node: dict) -> str:
    """The text of one block, its own and its children's."""
    if node.get("type") == "text":
        return node.get("text", "")
    return "".join(_words(child) for child in node.get("content") or [])


def _shape(node: dict):
    """A list as nested Python lists of its items' words; a paragraph as its
    words."""
    if node["type"] in ("bulletList", "orderedList"):
        return [[_shape(block) for block in item["content"]] for item in node["content"]]
    return _words(node)


def test_a_block_the_document_cannot_carry_is_a_paragraph_of_its_own():
    assert parse_html(TRIX_PAGE, on_page=True) is None, "a div page converts — the test's premise"
    draft = parse_html(TRIX_PAGE, on_page=True, lenient=True)
    validate_document(draft)
    blocks = draft["content"]
    assert [block["type"] for block in blocks] == [
        "paragraph",
        "blockquote",
        "paragraph",
        "blockquote",
        "bulletList",
    ], [(block["type"], _words(block)) for block in blocks]
    assert [_words(block) for block in blocks[:4]] == [
        "Een alinea.",
        "Een citaat.",
        "code in een blok",
        "Nog een citaat.",
    ], "two blocks' words are glued"
    shown = render_document(draft, None, on_page=True)
    assert "citaat.code" not in shown and "blokNog" not in shown, shown


def test_a_list_inside_a_list_stays_nested_in_the_draft():
    draft = parse_html(TRIX_PAGE, on_page=True, lenient=True)
    nested = draft["content"][-1]
    assert _shape(nested) == [
        ["Eén", [["Onder één"], ["Ook onder één"]]],
        ["Twee"],
    ], f"the inner list left its item: {_shape(nested)}"


def test_loose_words_before_a_quotation_are_not_glued_to_it():
    content = "<div>Alinea.</div>Losse woorden<blockquote>Een citaat.</blockquote>"
    draft = parse_html(content, on_page=True, lenient=True)
    validate_document(draft)
    assert [_words(block) for block in draft["content"]] == [
        "Alinea.",
        "Losse woorden",
        "Een citaat.",
    ]


def test_words_after_an_inner_list_stay_in_their_item():
    content = (
        "<div>Alinea.</div><ul><li>Eén<ul><li>Onder één</li></ul>en verder</li><li>Twee</li></ul>"
    )
    draft = parse_html(content, on_page=True, lenient=True)
    validate_document(draft)
    assert _shape(draft["content"][-1]) == [["Eén", [["Onder één"]], "en verder"], ["Twee"]]


def test_a_page_with_only_a_nested_list_keeps_her_html_and_nests_in_the_draft():
    """Such a page does not convert: rendered back, an item's words and its
    inner list stand with a line break between them, which today's page does
    not have — the measurement decides, not the parser. Her draft nests."""
    assert parse_html(NESTED, on_page=True) is None
    draft = parse_html(NESTED, on_page=True, lenient=True)
    validate_document(draft)
    assert _shape(draft["content"][0]) == [
        ["Eén", [["Onder één"], ["Ook onder één"]]],
        ["Twee"],
    ]
