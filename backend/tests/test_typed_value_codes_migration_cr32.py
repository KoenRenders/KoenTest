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
