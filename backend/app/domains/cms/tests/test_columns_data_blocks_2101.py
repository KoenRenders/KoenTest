"""CR-32 #2101: the activities and the album card in a column, and the ratio of two columns.

Broken on purpose (18 October 2026), each red for its own reason: the column's content
expression without the data blocks → a data block in a root column is refused; the path rule
of `_validate_node` taken out (additive: a section > columns > column > activities then
validates) → the refusals fail; `_holds_data_block` always false → the data block stays in the
prose and the parts test fails; the ratio dropped from the attributes → an unknown ratio is no
longer refused; the modifier class left out → the prose test fails.
"""

import pytest

from app.domains.cms.render import flat_html, render_document, render_document_parts
from app.domains.cms.schema import InvalidShape, UnknownAttribute, validate_document
from tests.integration.test_album_card_cr32 import _album

pytestmark = pytest.mark.ui_serverrendered

ACTIVITIES = {"type": "activities", "attrs": {"count": 4}}
ALBUMS = {"type": "albums", "attrs": {"albums": 3, "photos": 4, "interval": 3}}


def _par(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _columns(left: list, right: list, **attrs) -> dict:
    return {
        "type": "columns",
        "attrs": {"align": "top", **attrs},
        "content": [
            {"type": "column", "content": left},
            {"type": "column", "content": right},
        ],
    }


def _doc(*nodes: dict) -> dict:
    return {"type": "doc", "content": list(nodes)}


def test_a_data_block_may_stand_in_a_column_of_a_root_columns_block():
    validate_document(_doc(_columns([ACTIVITIES], [ALBUMS])))
    validate_document(_doc(_columns([_par("Tekst"), ACTIVITIES], [ALBUMS, _par("Na")])))


def test_a_data_block_does_not_stand_deeper():
    in_section = {
        "type": "section",
        "attrs": {"tone": "plain"},
        "content": [_columns([ACTIVITIES], [_par("x")])],
    }
    with pytest.raises(InvalidShape, match="activities onder kolom buiten de wortel"):
        validate_document(_doc(in_section))
    quotation = {"type": "blockquote", "content": [_columns([_par("x")], [ALBUMS])]}
    with pytest.raises(InvalidShape, match="albums onder kolom buiten de wortel"):
        validate_document(_doc(quotation))
    cell = {
        "type": "table",
        "content": [
            {
                "type": "tableRow",
                "attrs": {"section": "body"},
                "content": [{"type": "tableCell", "content": [_columns([ALBUMS], [_par("x")])]}],
            }
        ],
    }
    with pytest.raises(InvalidShape, match="albums onder kolom buiten de wortel"):
        validate_document(_doc(cell))


def test_the_ratio_is_one_of_three_names_and_may_be_absent():
    for ratio in ("equal", "wide-narrow", "narrow-wide"):
        validate_document(_doc(_columns([_par("a")], [_par("b")], ratio=ratio)))
    validate_document(_doc(_columns([_par("a")], [_par("b")])))
    with pytest.raises(UnknownAttribute, match="columns.ratio"):
        validate_document(_doc(_columns([_par("a")], [_par("b")], ratio="half")))


def test_columns_without_a_data_block_stay_in_the_prose_as_before(db_session):
    document = _doc(_par("Voor"), _columns([_par("a")], [_par("b")]), _par("Na"))
    parts = render_document_parts(document, db_session)
    assert [kind for kind, *_rest in parts] == ["prose"]
    assert parts[0][1] == (
        "<p>Voor</p>"
        '<div class="prose-columns"><div class="prose-column"><p>a</p></div>'
        '<div class="prose-column"><p>b</p></div></div><p>Na</p>'
    )
    assert render_document(document, db_session) == parts[0][1]


def test_a_ratio_is_written_as_a_modifier_class_in_the_prose(db_session):
    html = render_document(
        _doc(_columns([_par("a")], [_par("b")], ratio="wide-narrow")), db_session
    )
    assert 'class="prose-columns prose-columns--wide-narrow"' in html
    equal = render_document(_doc(_columns([_par("a")], [_par("b")], ratio="equal")), db_session)
    assert 'class="prose-columns"' in equal


def test_columns_that_hold_data_blocks_are_a_part_of_their_own(db_session):
    _album(db_session, "Beweging", 2020, 3)
    document = _doc(
        _par("Voor"),
        _columns([_par("Links"), ACTIVITIES], [ALBUMS], ratio="wide-narrow"),
        _par("Na"),
    )
    parts = render_document_parts(document, db_session, preview=True)
    assert [part[0] for part in parts] == ["prose", "columns", "prose"]
    _kind, ratio, cells = parts[1]
    assert ratio == "wide-narrow" and len(cells) == 2
    assert [kind for kind, _html in cells[0]] == ["prose", "data"]
    assert "Links" in cells[0][0][1]
    assert [kind for kind, _html in cells[1]] == ["data"]
    assert "data-photo-card" in cells[1][0][1]
    # The album card is the module's own markup, outside the prose styling.
    assert "prose-raak" not in cells[1][0][1]


def test_an_equal_ratio_is_no_modifier_and_empty_columns_draw_nothing(db_session):
    only_albums = _doc(_columns([ALBUMS], [ALBUMS], ratio="equal"))
    assert render_document_parts(only_albums, db_session) == [], "no album: no columns"
    _album(db_session, "Beweging", 2020, 3)
    parts = render_document_parts(only_albums, db_session)
    assert parts[0][0] == "columns" and parts[0][1] is None


def test_the_flat_html_draws_the_columns_with_the_prose_grid(db_session):
    _album(db_session, "Beweging", 2020, 3)
    html = render_document(_doc(_columns([_par("L")], [ALBUMS], ratio="narrow-wide")), db_session)
    assert html.startswith('<div class="prose-columns prose-columns--narrow-wide">')
    assert html.count('class="prose-column"') == 2 and "data-photo-card" in html
    assert flat_html([("prose", "<p>x</p>")]) == "<p>x</p>"
