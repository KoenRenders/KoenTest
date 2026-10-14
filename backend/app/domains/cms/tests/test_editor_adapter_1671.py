"""The save adapter — what the editor sends becomes a stored document (CR-17
#1671, slice 3; the table decision of 8 October 2026, Koen).

What the author sees and means survives the round trip: a merged cell's
spans and a header row. What only the editor's software notes — column
widths and alignment, chrome our toolbar never offers and the site never
shows — the adapter drops. The editor's own words for a header row (header
CELLS) become the stored document's words (a section on the row).

Every red proof stands against e3f5d30b's tip, where the editor's table
emission was refused outright.
"""

from app.domains.cms.schema import validate_document
from app.domains.cms.service import document_from_editor

# What TipTap really writes for a table (the B1 test of #1699 measured it):
# chrome on every cell, no section on any row, and a header row expressed
# in the cell types.
EDITOR_TABLE = {
    "type": "doc",
    "content": [
        {
            "type": "table",
            "content": [
                {
                    "type": "tableRow",
                    "content": [
                        {
                            "type": "tableHeader",
                            "attrs": {"colspan": 1, "rowspan": 1, "colwidth": [120], "align": None},
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Wat"}],
                                }
                            ],
                        }
                    ],
                },
                {
                    "type": "tableRow",
                    "content": [
                        {
                            "type": "tableCell",
                            "attrs": {"colspan": 2, "rowspan": 1, "colwidth": None, "align": None},
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Koffie"}],
                                }
                            ],
                        }
                    ],
                },
            ],
        }
    ],
}


def test_the_editors_table_validates_after_the_adapter():
    """The B1 gap of #1699 closed: the editor's whole table emission —
    chrome, no sections, all of it — passes the server's gate once the
    adapter has translated her words. Red on the tip before this slice:
    the same JSON was refused (tableCell.colwidth)."""
    validate_document(document_from_editor(EDITOR_TABLE))


def test_the_chrome_nobody_sees_is_dropped():
    """Column widths and alignment never reach the stored document — the
    toolbar offers neither, the site shows neither. Measured by the
    adapter's output: the cell carries her spans and nothing else."""
    stored = document_from_editor(EDITOR_TABLE)
    cell = stored["content"][0]["content"][1]["content"][0]
    assert cell["attrs"] == {"colspan": 2, "rowspan": 1}


def test_a_header_row_is_said_in_the_stored_words():
    """The editor says 'these are header cells'; the stored document says
    'this row is the header section'. The adapter translates, so the
    header survives the round trip (before: the section was lost on every
    load-and-save, the measured B1 gap)."""
    stored = document_from_editor(EDITOR_TABLE)
    rows = stored["content"][0]["content"]
    assert rows[0]["attrs"] == {"section": "head"}
    assert rows[1]["attrs"] == {"section": "body"}


def test_a_merged_cell_renders_her_spans():
    """What the author sees and means, the site shows (Koen, 8 October
    2026): a merged cell renders her colspan. Red on the tip before this
    slice: the renderer wrote a bare <td>."""
    from app.domains.cms.render import render_document

    stored = document_from_editor(EDITOR_TABLE)
    assert '<td colspan="2">' in render_document(stored, None)


def test_an_ordinary_table_keeps_today_html():
    """The other half of the promise: an ordinary cell — spans of 1, the
    editor's defaults — renders exactly as today's <td>, and a table
    without merged cells changes the HTML of no existing page."""
    from copy import deepcopy

    from app.domains.cms.render import render_document

    plain = deepcopy(EDITOR_TABLE)
    for row in plain["content"][0]["content"]:
        for cell in row["content"]:
            cell["attrs"]["colspan"] = 1
    html = render_document(document_from_editor(plain), None)
    assert 'colspan="' not in html and "<td>" in html
