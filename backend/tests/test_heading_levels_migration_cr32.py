"""CR-32 R21/F19: a page stores the heading levels it shows (h2–h4).

Migration 204 rewrites every stored document once, h1→h2, h2→h3, h3→h4. The
proof is on a snapshot: a document the way the editor stored it before, with
headings at every depth (in a column, a list-free cell, a quotation), and the
same document after — and back again, so the downgrade is the exact reverse.

Broken on purpose (15 October 2026), each red for its own reason: a `step` of
0 → nothing moves, the first assertion fails; the walk skipping `content` of a
nested node → the heading in the column stays at its old level; the guard
dropped → a stray level 4 becomes 5 and the range assertion fails.
"""

import importlib.util
from pathlib import Path

MIGRATION = next(
    (Path(__file__).parents[1] / "alembic" / "versions").glob("204_*_pages_store_the_heading_*.py")
)


def _load():
    spec = importlib.util.spec_from_file_location("heading_levels_204", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _heading(level: int, text: str) -> dict:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


SNAPSHOT = {
    "type": "doc",
    "content": [
        _heading(1, "Kop"),
        {"type": "paragraph", "content": [{"type": "text", "text": "Tekst"}]},
        _heading(2, "Subkop"),
        {
            "type": "columns",
            "content": [{"type": "column", "content": [_heading(3, "Kleine kop")]}],
        },
        {"type": "blockquote", "content": [_heading(1, "In een citaat")]},
    ],
}


def _levels(node) -> list[int]:
    found: list[int] = []
    if isinstance(node, dict):
        if node.get("type") == "heading":
            found.append(node["attrs"]["level"])
        for value in node.values():
            found += _levels(value)
    elif isinstance(node, list):
        for item in node:
            found += _levels(item)
    return found


def test_every_heading_moves_one_level_down_at_every_depth():
    shift = _load().shift_headings
    before = _levels(SNAPSHOT)
    assert before == [1, 2, 3, 1], "the snapshot carries what the editor stored"
    shifted, changed = shift(SNAPSHOT, +1)
    assert changed is True
    assert _levels(shifted) == [2, 3, 4, 2]
    assert _levels(SNAPSHOT) == before, "the input is not touched"


def test_the_downgrade_is_the_exact_reverse():
    shift = _load().shift_headings
    there, _ = shift(SNAPSHOT, +1)
    back, _ = shift(there, -1)
    assert back == SNAPSHOT


def test_a_document_without_headings_is_reported_unchanged():
    shift = _load().shift_headings
    document = {"type": "doc", "content": [{"type": "paragraph", "content": []}]}
    assert shift(document, +1) == (document, False)


def test_a_level_the_move_cannot_arrive_at_is_left_alone():
    shift = _load().shift_headings
    stray = {"type": "doc", "content": [_heading(4, "al h4")]}
    assert shift(stray, +1) == (stray, False), "h5 does not exist"
    low = {"type": "doc", "content": [_heading(1, "al h1")]}
    assert shift(low, -1) == (low, False), "h0 does not exist"
