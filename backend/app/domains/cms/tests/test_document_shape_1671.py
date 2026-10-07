"""The shape half of the schema (CR-17 phase 1, #1671; C6 test 2, built as
slice 2's first step).

Names were checked since slice 1; from the editor on, documents arrive from
a browser, so the server also decides where a node may sit, which attributes
must be present, and how many children a parent holds (Koen, 6 October 2026:
the border is the editor, not the API). Every test here went red on the
slice-1 validator — the violation it makes is named in the docstring.
"""

import pytest

from app.domains.cms.schema import (
    FIGURE_PLACEMENTS,
    InvalidShape,
    UnknownAttribute,
    UnknownBlock,
    validate_document,
)


def _doc(*blocks: dict) -> dict:
    return {"type": "doc", "content": list(blocks)}


def _par(text: str) -> dict:
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": text}],
    }


def test_text_straight_under_the_doc_is_refused():
    """B1's own example: a text node directly under the doc (no paragraph)
    validated in slice 1 — the renderer refused it later. Now the shape gate
    refuses it before anything is stored."""
    with pytest.raises(InvalidShape, match="text onder doc"):
        validate_document(_doc({"type": "text", "text": "los"}))


def test_a_figure_without_her_media_id_is_refused():
    """B1: a figure with only an alt validated in slice 1 — a picture
    without an image is no figure. The required attribute is named."""
    with pytest.raises(UnknownAttribute, match="figure.media_id"):
        validate_document(_doc({"type": "figure", "attrs": {"alt": "Het lokaal"}}))


def test_a_numeric_heading_level_is_refused():
    """B1's "a numeric label": True and 2.0 passed the membership test in
    slice 1 because bool is an int in Python and 2.0 == 2 — the two
    measured escapes; "2" and 4 were already refused by the tuple check.
    All four refuse with the attribute's name now."""
    for level in (True, 2.0, "2", 4):
        with pytest.raises(UnknownAttribute, match="heading.level"):
            validate_document(
                _doc(
                    {
                        "type": "heading",
                        "attrs": {"level": level},
                        "content": [{"type": "text", "text": "Kop"}],
                    }
                )
            )


def test_a_row_directly_under_the_doc_is_refused():
    """A tableRow is only a child of a table: under the doc she validated in
    slice 1 (names only). The refusal names the node and her place."""
    with pytest.raises(InvalidShape, match="tableRow onder doc"):
        validate_document(
            _doc({"type": "tableRow", "content": [{"type": "tableCell", "content": [_par("cel")]}]})
        )


def test_a_block_inside_an_inline_place_is_refused():
    """A paragraph holds inline nodes; a figure inside one validated in
    slice 1. The shape gate names the misplaced child."""
    with pytest.raises(InvalidShape, match="figure onder paragraph"):
        validate_document(
            _doc({"type": "paragraph", "content": [{"type": "figure", "attrs": {"media_id": 1}}]})
        )


def test_a_button_without_her_label_is_refused():
    """Required attributes are refused by name, also when the node sits in
    the right place (a button without her label)."""
    with pytest.raises(UnknownAttribute, match="button.label"):
        validate_document(_doc({"type": "button", "attrs": {"target": "/x", "variant": "primary"}}))


def test_marks_on_a_block_are_refused():
    """Marks belong to text; a paragraph carrying them validated in slice
    1 because nothing looked for them outside a text node."""
    with pytest.raises(UnknownAttribute, match="paragraph.marks"):
        validate_document(
            {"type": "doc", "content": [{"type": "paragraph", "marks": [{"type": "bold"}]}]}
        )


def test_a_flattened_text_node_is_refused():
    """The mistake a hand-rolled client makes: a paragraph with a "text"
    key instead of a child. Slice 1 stored her silently; the renderer showed
    nothing. Refused as a place, not a name — the block itself is known."""
    with pytest.raises(InvalidShape, match="tekst in paragraph"):
        validate_document(_doc({"type": "paragraph", "text": "platgevallen"}))


def test_a_table_with_no_rows_is_refused():
    """ "tableRow+" demands a row: an empty table validated in slice 1 and
    the renderer drew an empty <table>."""
    with pytest.raises(InvalidShape, match="Leeg blok: table"):
        validate_document(_doc({"type": "table", "content": []}))


def test_a_leaf_holds_no_children():
    """A figure has no content expression: she is a leaf. Children under her
    validated in slice 1 (never rendered, never refused)."""
    with pytest.raises(InvalidShape, match="onder figure"):
        validate_document(
            _doc({"type": "figure", "attrs": {"media_id": 1}, "content": [_par("bijschrift")]})
        )


def test_an_unknown_child_keeps_her_pinned_message():
    """The JSON door (test 18) pins the message: an unknown block is refused
    with "Onbekend blok: <name>" — also when her position is wrong first."""
    with pytest.raises(UnknownBlock, match="Onbekend blok: slider"):
        validate_document(_doc({"type": "slider"}))


def test_an_empty_document_still_validates():
    """The honest empty page (review 4, #1673): the migration's net produces
    a document with no blocks. This goes red the moment the root's minimum
    is enforced — the guard that keeps "empty" a valid answer."""
    assert validate_document({"type": "doc", "content": []}) == {"type": "doc", "content": []}


def test_a_bare_table_row_and_a_placementless_figure_validate():
    """Optional attributes stay optional (None in the enum tuple): a bare
    row renders bare rows, a converted figure is placed full width — both
    exactly as today. This goes red if optionality is dropped."""
    validate_document(
        _doc(
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableCell",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "cel"}],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {"type": "figure", "attrs": {"media_id": 7}},
        )
    )


def test_a_full_page_document_validates():
    """The positive half: a document with every block the page set offers
    passes the shape gate — the gate refuses mistakes, not the design."""
    validate_document(
        _doc(
            {
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": "Kop"}],
            },
            _par("Een alinea."),
            {
                "type": "bulletList",
                "content": [{"type": "listItem", "content": [_par("punt")]}],
            },
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "attrs": {"section": "head"},
                        "content": [{"type": "tableHeader", "content": [_par("Wat")]}],
                    },
                    {
                        "type": "tableRow",
                        "attrs": {"section": "body"},
                        "content": [{"type": "tableCell", "content": [_par("Koffie")]}],
                    },
                ],
            },
            {
                "type": "figure",
                "attrs": {
                    "media_id": 3,
                    "placement": FIGURE_PLACEMENTS[0],
                    "caption": "Het lokaal",
                },
            },
        )
    )


# ── The first review of the PR (#1699): refused with a name, never a crash ────


def _par_words(node: dict) -> dict:
    return {"type": "paragraph", "content": [node]}


def test_attributes_that_are_not_a_map_are_refused():
    """A2 of the review: `attrs` as a string or a list crashed the validator
    (`AttributeError` on `.items()`) on 1c8473ea. A malformed document is
    refused with a name — the node's — never an exception."""
    for attrs in ("vet", ["vet"], 5):
        with pytest.raises(InvalidShape, match="paragraph"):
            validate_document({"type": "doc", "content": [{"type": "paragraph", "attrs": attrs}]})


def test_content_that_is_not_a_list_is_refused():
    """A2: `content` as a number raised a TypeError on 1c8473ea. Refused as
    a shape, named after the node that holds it."""
    with pytest.raises(InvalidShape, match="doc"):
        validate_document({"type": "doc", "content": 5})


def test_a_deeply_nested_document_is_refused_not_recursed_to_death():
    """A2: a list nested 2000 deep exhausted the stack (RecursionError) on
    1c8473ea. The position check refuses her early; the depth cap is the
    backstop for a future content expression that allows deeper nesting.
    What is measured: a named refusal, quickly, never a crash."""
    deep = {"type": "paragraph"}
    for _ in range(2000):
        deep = {"type": "paragraph", "content": [deep]}
    with pytest.raises((UnknownBlock, UnknownAttribute, InvalidShape)):
        validate_document({"type": "doc", "content": [deep]})


def test_a_link_without_her_target_is_refused():
    """A3: a link whose href is a number, or missing, validated on 1c8473ea
    and rendered `<a href="">` — nothing. The mark's attributes are typed
    like every node's."""
    with pytest.raises(UnknownAttribute, match="link.href"):
        validate_document(
            _doc(_par_words({"type": "text", "text": "link", "marks": [{"type": "link"}]}))
        )
    with pytest.raises(UnknownAttribute, match="link.href"):
        validate_document(
            _doc(
                _par_words(
                    {
                        "type": "text",
                        "text": "link",
                        "marks": [{"type": "link", "attrs": {"href": 5}}],
                    }
                )
            )
        )


def test_a_text_node_without_words_is_refused():
    """A3: a text node without a `text` key, or with an empty one, validated
    on 1c8473ea. Text carries words; nothing else is text. She sits inside
    her paragraph here — the place check would catch her under the doc
    before her own shape could speak."""
    for text_node in ({"type": "text"}, {"type": "text", "text": ""}):
        with pytest.raises(InvalidShape, match="inhoud"):
            validate_document(
                {"type": "doc", "content": [{"type": "paragraph", "content": [text_node]}]}
            )


def test_a_root_that_is_no_document_is_refused():
    """A3: a paragraph (or a text node) as the root validated on 1c8473ea.
    The stored shape is a document; a client that posts a bare node is
    refused before anything reads a child."""
    with pytest.raises(InvalidShape, match="wortel"):
        validate_document(_par("los"))


def test_an_id_of_nothing_is_refused():
    """A3: `figure.media_id` 0 and −1 validated on 1c8473ea, while the PR
    and the editor's insert promised the server refuses a figure without
    her image. An id is a row that exists; 0 and negatives are "nothing"."""
    for media_id in (0, -1):
        with pytest.raises(UnknownAttribute, match="figure.media_id"):
            validate_document(_doc({"type": "figure", "attrs": {"media_id": media_id}}))
    with pytest.raises(UnknownAttribute, match="form.form_id"):
        validate_document(_doc({"type": "form", "attrs": {"form_id": 0}}))


def test_an_ordered_list_with_her_own_start_validates():
    """The B1 test of the review (#1699) measured what the editor really
    writes: TipTap's orderedList carries `start` (and a `type` she sets to
    null). The schema knows them — an editor emission the server refuses
    would make the B1 promise a lie for anything but the declared table."""
    validate_document(
        _doc(
            {
                "type": "orderedList",
                "attrs": {"start": 1, "type": None},
                "content": [{"type": "listItem", "content": [_par("eerst")]}],
            }
        )
    )
