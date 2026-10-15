"""The quotation block of the page editor, in the schema and in the
conversion of a page that came from Trix (#1985).

The Trix editor had a quotation; the page editor of CR-17 had none, so a
Trix page's quotation became a plain paragraph once its draft was published
(the comparison with the Trix editor, 14 October 2026). Koen, 14 October
2026, to "Moet het citaat als blok terug vóór de tag van v2.17 (a), of mag
het weg (b)?": "a, v2.17".

`TRIX_PIECES` is Trix's own output: twenty pieces typed in the meeting notes
(the one Trix editor left in the back office) with the keyboard and Trix's
own toolbar buttons — the link through Trix's API — and read from Trix's
hidden input, Trix 2.1.15, 14 October 2026. Trix writes a quotation's words
straight in the `<blockquote>`, with a `<br>` where the author pressed
Enter, and a paragraph as a `<div>`. Before the quotation block three of the
twenty converted (a heading and the two plain lists); with it, seven.

Broken on purpose (14 October 2026), each put back by the reverse edit: the
quotation taken out of the conversion's containers (`blockquote` no longer
opened as one) → 6 red, the four quotation pieces no longer convert; the
renderer's line break between a quotation's paragraphs left out → 4 red,
the three Trix quotations no longer convert; the node renamed in the schema
→ 6 red, a document with a quotation refused.
"""

import pytest

from app.domains.cms.parse import parse_html
from app.domains.cms.render import render_document
from app.domains.cms.schema import InvalidShape, UnknownAttribute, validate_document

TRIX_PIECES = {
    "paragraph": "<div>Een alinea.</div>",
    "two paragraphs": "<div>Eerste alinea.<br><br>Tweede alinea.</div>",
    "one Enter": "<div>Eerste regel.<br>Tweede regel.</div>",
    "marks": "<div><strong>vet</strong>&nbsp;<em>cursief</em>&nbsp;<del>doorgehaald</del></div>",
    "link": '<div>Lees <a href="https://example.test/pagina">een link</a>.</div>',
    "soft break": "<div>Regel een<br>Regel twee</div>",
    "heading": "<h1>Een kop</h1>",
    "heading then paragraph": "<h1>Een kop</h1><div>Een alinea.</div>",
    "quotation": "<blockquote>Een citaat.</blockquote>",
    "quotation with a soft break": "<blockquote>Regel een<br>Regel twee</blockquote>",
    "quotation, Enter inside": "<blockquote>Eerste regel.<br>Tweede regel.</blockquote>",
    "paragraph, quotation, paragraph": "<div>Voor.<br><br></div><blockquote>Een citaat.</blockquote><div>Na.</div>",
    "code block": "<pre>code in een blok</pre>",
    "quotation then code block": "<blockquote>Een citaat.</blockquote><pre>code in een blok</pre>",
    "bullet list": "<ul><li>Een</li><li>Twee</li></ul>",
    "numbered list": "<ol><li>Eerst</li><li>Daarna</li></ol>",
    "list in a list": "<ul><li>Een<ul><li>Onder een</li><li>Ook onder een</li></ul></li></ul>",
    "list inside a quotation": "<blockquote><ul><li>Een</li><li>Twee</li></ul></blockquote>",
    "quotation inside a list": "<ul><li>Een</li><li><blockquote>Een citaat in de lijst</blockquote></li></ul>",
    "a code in text": "<div>Het lidgeld is {{membership_price_full}}.</div>",
}

#: What converts strictly with the quotation block — the measurement decides.
CONVERTING = {
    "heading",
    "quotation",
    "quotation with a soft break",
    "quotation, Enter inside",
    "bullet list",
    "numbered list",
    "list inside a quotation",
}


def _doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def _par(text):
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def test_a_document_with_a_quotation_validates():
    quotation = {
        "type": "blockquote",
        "content": [
            _par("Een citaat."),
            {
                "type": "bulletList",
                "content": [{"type": "listItem", "content": [_par("Een punt.")]}],
            },
        ],
    }
    validate_document(_doc(quotation))
    shown = render_document(_doc(quotation), None)
    assert shown.count("<blockquote>") == 1 and "Een citaat." in shown, shown


def test_a_quotation_refuses_an_attribute_and_an_empty_body():
    with pytest.raises(UnknownAttribute, match="blockquote.cite"):
        validate_document(
            _doc({"type": "blockquote", "attrs": {"cite": "x"}, "content": [_par("Een.")]})
        )
    with pytest.raises(InvalidShape):
        validate_document(_doc({"type": "blockquote", "content": []}))
    with pytest.raises(InvalidShape, match="text onder blockquote"):
        validate_document(
            _doc({"type": "blockquote", "content": [{"type": "text", "text": "los"}]})
        )


def test_the_trix_pieces_that_convert():
    converting = {name for name, html in TRIX_PIECES.items() if parse_html(html) is not None}
    assert converting == CONVERTING, (
        f"converts now and did not: {sorted(converting - CONVERTING)}; "
        f"no longer converts: {sorted(CONVERTING - converting)}"
    )


@pytest.mark.parametrize(
    "name", ["quotation", "quotation with a soft break", "quotation, Enter inside"]
)
def test_a_trix_quotation_is_one_quotation_block_with_its_words_whole(name):
    document = parse_html(TRIX_PIECES[name])
    assert document is not None, f"{name} does not convert"
    validate_document(document)
    [block] = document["content"]
    assert block["type"] == "blockquote", document
    shown = render_document(document, None)
    assert shown.count("<blockquote>") == 1, shown
    words = render_document(document, None, target="text")
    for word in ("Een citaat.", "Regel een", "Regel twee", "Eerste regel.", "Tweede regel."):
        if word in TRIX_PIECES[name]:
            assert word in words, f"{word!r} lost: {words!r}"


def test_a_list_inside_a_quotation_nests():
    document = parse_html(TRIX_PIECES["list inside a quotation"])
    assert document is not None
    [quotation] = document["content"]
    assert quotation["type"] == "blockquote"
    assert [child["type"] for child in quotation["content"]] == ["bulletList"], quotation


def test_the_draft_keeps_a_quotation_inside_a_list_and_beside_paragraphs():
    """Neither converts (a Trix paragraph; an item whose first block is a
    quotation, which the editor's list item cannot hold first), so the page
    keeps her HTML — and her draft keeps the quotation as a block."""
    for name in ("quotation inside a list", "paragraph, quotation, paragraph"):
        draft = parse_html(TRIX_PIECES[name], lenient=True)
        validate_document(draft)
        shown = render_document(draft, None)
        assert shown.count("<blockquote>") == 1, f"{name}: {shown}"
