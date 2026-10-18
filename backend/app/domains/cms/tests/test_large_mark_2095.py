"""The mark "Groot": words made large inside an ordinary line (#2095).

A heading is a whole line; "Lidgeld €35 per gezin" with only the amount large
needs a mark. It renders as a `span` with one class and never as a heading,
so the page keeps its one `h1` (#1656).

Broken on purpose (18 October 2026), each put back by the reverse edit: the
mark taken out of `_mark_html` → the render tests red; the parser not reading
the span → the round trip red; `large` left out of the text node's marks →
the schema tests red.
"""

import pytest

from app.domains.cms.parse import parse_html
from app.domains.cms.render import LARGE_CLASS, render_document
from app.domains.cms.schema import UnknownBlock, validate_document


def _doc(*inline: dict) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": list(inline)}]}


def _words(text: str, *marks: str) -> dict:
    node: dict = {"type": "text", "text": text}
    if marks:
        node["marks"] = [{"type": mark} for mark in marks]
    return node


def test_the_mark_renders_a_span_with_one_class_and_no_heading():
    doc = _doc(_words("Lidgeld "), _words("€35", "large"), _words(" per gezin"))
    html = render_document(doc)
    assert html == f'<p>Lidgeld <span class="{LARGE_CLASS}">€35</span> per gezin</p>'
    assert "<h" not in html


def test_a_document_without_the_mark_renders_as_before():
    doc = _doc(_words("Gewoon "), _words("vet", "bold"), _words(" en "), _words("schuin", "italic"))
    assert render_document(doc) == "<p>Gewoon <strong>vet</strong> en <em>schuin</em></p>"


def test_the_mark_nests_with_bold():
    doc = _doc(_words("€35", "bold", "large"))
    assert render_document(doc) == f'<p><span class="{LARGE_CLASS}"><strong>€35</strong></span></p>'


def test_a_value_node_can_be_large():
    doc = _doc(
        _words("Lidgeld "),
        {"type": "value", "attrs": {"code": "membership_price_full"}, "marks": [{"type": "large"}]},
    )
    validate_document(doc)
    html = render_document(doc)
    assert f'<span class="{LARGE_CLASS}">' in html
    assert html.endswith("</span></p>")


def test_a_value_node_refuses_every_other_mark():
    doc = _doc(
        {"type": "value", "attrs": {"code": "membership_price_full"}, "marks": [{"type": "bold"}]}
    )
    with pytest.raises(UnknownBlock):
        validate_document(doc)


def test_the_round_trip_holds():
    doc = _doc(_words("Lidgeld "), _words("€35", "large"), _words(" per gezin"))
    first = parse_html(render_document(doc))
    assert first == doc
    assert parse_html(render_document(first)) == first


def test_another_span_or_class_is_not_the_mark():
    assert parse_html('<p>a <span class="iets-anders">b</span></p>') is None
    assert parse_html('<p>a <span style="font-size:9rem">b</span></p>') is None


def test_a_span_that_is_not_the_mark_does_not_close_the_one_around_it():
    html = f'<p><span class="{LARGE_CLASS}">groot <span>binnen</span> nog groot</span> gewoon</p>'
    assert parse_html(html) is None


def test_the_schema_refuses_an_unknown_mark_still():
    with pytest.raises(UnknownBlock):
        validate_document(_doc(_words("x", "huge")))


def test_the_schema_refuses_a_class_on_a_node():
    doc = {"type": "doc", "content": [{"type": "paragraph", "attrs": {"class": LARGE_CLASS}}]}
    with pytest.raises(Exception):  # noqa: B017 - any refusal, the name varies by shape
        validate_document(doc)
