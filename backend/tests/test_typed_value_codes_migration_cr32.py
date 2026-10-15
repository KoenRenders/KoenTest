"""CR-32 R19: migration 206 turns the typed codes of every stored document into
value nodes, proven on a snapshot (C6 test 17).

Broken on purpose (15 October 2026): the split skipping the text after the code
→ the words after a value are gone; the unknown-code branch converting
everything → `{{tenants:raak}}` and `{{form:…}}` stop being text.
"""

import importlib.util
from pathlib import Path

MIGRATION = next(
    (Path(__file__).parents[1] / "alembic" / "versions").glob("206_*_typed_value_codes_*.py")
)


def _load():
    spec = importlib.util.spec_from_file_location("typed_codes_206", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _text(text, marks=None):
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


SNAPSHOT = {
    "type": "doc",
    "content": [
        {
            "type": "paragraph",
            "content": [
                _text(
                    "Het lidgeld is {{membership_price_full}} per gezin, tot {{half_price_end}}."
                ),
                {"type": "hardBreak"},
                _text("Sites: {{tenants:raak}} en {{form:berichten|Contact}}, onbekend {{iets}}."),
            ],
        },
        {
            "type": "table",
            "content": [
                {
                    "type": "tableRow",
                    "attrs": {"section": "body"},
                    "content": [
                        {
                            "type": "tableCell",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [_text("{{tenants}}", [{"type": "bold"}])],
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    ],
}


def _inline(document, index=0):
    return document["content"][index]["content"]


def test_every_typed_code_of_the_list_becomes_a_value_node_around_its_words():
    migration = _load()
    stats = {"made": 0, "left": 0, "unmarked": 0}
    converted = migration.codes_to_nodes(SNAPSHOT, stats)
    first = _inline(converted)[:5]
    assert first == [
        _text("Het lidgeld is "),
        {"type": "value", "attrs": {"code": "membership_price_full"}},
        _text(" per gezin, tot "),
        {"type": "value", "attrs": {"code": "half_price_end"}},
        _text("."),
    ]
    cell = converted["content"][1]["content"][0]["content"][0]["content"][0]["content"]
    assert cell == [{"type": "value", "attrs": {"code": "tenants"}}]
    assert stats == {"made": 3, "left": 3, "unmarked": 1}


def test_what_is_not_in_the_list_stays_text_and_is_counted():
    migration = _load()
    stats = {"made": 0, "left": 0, "unmarked": 0}
    converted = migration.codes_to_nodes(SNAPSHOT, stats)
    last = _inline(converted)[-1]
    assert last == _text(
        "Sites: {{tenants:raak}} en {{form:berichten|Contact}}, onbekend {{iets}}."
    )


def test_the_input_is_not_touched_and_a_document_without_codes_is_equal():
    migration = _load()
    plain = {"type": "doc", "content": [{"type": "paragraph", "content": [_text("Geen code.")]}]}
    before = repr(SNAPSHOT)
    stats = {"made": 0, "left": 0, "unmarked": 0}
    assert migration.codes_to_nodes(plain, stats) == plain
    migration.codes_to_nodes(SNAPSHOT, stats)
    assert repr(SNAPSHOT) == before


def test_the_downgrade_writes_the_codes_back_as_text():
    migration = _load()
    stats = {"made": 0, "left": 0, "unmarked": 0}
    there = migration.codes_to_nodes(SNAPSHOT, stats)
    back = migration.nodes_to_codes(there)
    words = "".join(node.get("text", "") for node in _inline(back))
    assert words.startswith(
        "Het lidgeld is {{membership_price_full}} per gezin, tot {{half_price_end}}."
    )


def _links(node) -> list:
    found: list = []
    if isinstance(node, dict):
        for mark in node.get("marks") or []:
            if isinstance(mark, dict) and mark.get("type") == "link":
                found.append((node.get("text"), mark["attrs"]["href"]))
        for value in node.values():
            found += _links(value)
    elif isinstance(node, list):
        for item in node:
            found += _links(item)
    return found


LINKED = {
    "type": "doc",
    "content": [
        {
            "type": "paragraph",
            "content": [
                _text("Zie "),
                _text(
                    "{{membership_price_full}}",
                    [{"type": "link", "attrs": {"href": "https://example.test/tarief"}}],
                ),
                _text(" en "),
                _text(
                    "{{half_price_end}} met link",
                    [{"type": "link", "attrs": {"href": "/lid-worden"}}],
                ),
                _text(" en {{membership_price_half}} los."),
            ],
        }
    ],
}


def test_a_code_in_words_that_carry_a_link_stays_text_and_no_link_goes_missing():
    migration = _load()
    stats = {"made": 0, "left": 0, "unmarked": 0}
    converted = migration.codes_to_nodes(LINKED, stats)
    assert _links(converted) == _links(LINKED) and len(_links(LINKED)) == 2, "a link disappeared"
    inline = _inline(converted)
    assert _text("{{membership_price_full}}", LINKED["content"][0]["content"][1]["marks"]) in inline
    values = [n for n in inline if n.get("type") == "value"]
    assert values == [{"type": "value", "attrs": {"code": "membership_price_half"}}]
    assert stats["made"] == 1 and stats["left"] == 2, stats


def test_a_code_split_over_two_text_nodes_by_a_mark_stays_text_and_is_counted():
    migration = _load()
    split = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    _text("Lidgeld {{membership_", [{"type": "bold"}]),
                    _text("price_full}} per gezin"),
                    {"type": "hardBreak"},
                    _text("{{half_price_end}} gewoon"),
                ],
            }
        ],
    }
    stats = {"made": 0, "left": 0, "unmarked": 0}
    converted = migration.codes_to_nodes(split, stats)
    words = "".join(n.get("text", "") for n in _inline(converted))
    assert words.startswith("Lidgeld {{membership_price_full}} per gezin"), words
    assert stats["made"] == 1, "the whole code in its own run converts"
    assert stats["left"] == 1, "the split code is counted as staying text"
    assert _inline(converted)[0] == split["content"][0]["content"][0], (
        "the split halves are untouched"
    )
