"""The block schema of web content (CR-17 phase 1, #1671).

One source for everything that must agree (C6 test 2): the editor's
configuration (what the toolbar and "Blok invoegen ▾" offer, per set), the
validation of a document on save and import (an unknown node or attribute is
refused with its name, never stripped), and the JSON Schema served to an
outside writer (phase 4). The renderer dispatches on the same node names
(``cms/render.py``), and the parser produces them (``cms/parse.py``).

Why a schema module and not TipTap's own schema: the editor's schema lives in
the browser and dies with the tab; the document is stored as JSON against THIS
module, so the server decides what a document may hold — the editor is one
writer among three (the editor, the import, the API).

Block sets (C4.5): ``page`` (phase 1), ``letter`` and ``notes`` (phase 7).
A set names the nodes its toolbar and insert menu offer; an unknown set is a
``ValueError``. A node outside the schema is refused in every set.
"""

from __future__ import annotations

from typing import Any

#: The five configuration codes a value block can carry (C4.4). The labels and
#: the current values come from the renderer/service — this is the one place
#: that says WHICH codes exist, because the parser maps exactly these.
VALUE_CODES: tuple[str, ...] = (
    "membership_price_full",
    "membership_price_half",
    "half_price_start",
    "half_price_end",
    "next_year_from",
)

#: The figures a page can place (C4.2). ``legacy_*`` sizes only come out of the
#: migration: an existing page's picture renders byte-for-byte as it did, with
#: its own class, so the association's pages stay pixel-exact (R17, test 19).
#: A figure placed through the editor carries a placement and renders as the
#: kit's figure with the public radius and shadow (C4.8).
FIGURE_PLACEMENTS: tuple[str, ...] = ("left", "right", "full", "small")
LEGACY_FIGURE_SIZES: tuple[str, ...] = ("klein", "half", "vol")

#: The heading levels an author can choose: Kop, Subkop, Kleine kop — the same
#: three as today (#1656), stored as levels 1–3. The renderer picks the TAG
#: from where the document stands (h2–h4 under a page's title, h1–h3 in a
#: fragment such as the home intro), exactly as `render_cms_content(on_page=…)`
#: has done since #1656 (C4.2). An h4 typed through the old HTML door does not
#: convert losslessly and keeps its HTML (F11).
HEADING_LEVELS: tuple[int, ...] = (1, 2, 3)

#: Every node a document may hold, with its attributes (F1). Marks on ``text``:
#: bold, italic, strike, link. ``columns``, ``button``, ``callout``,
#: ``link_card``, ``cards`` and ``form`` are part of the schema from phase 1 —
#: the shape is fixed here — but no phase-1 set offers them in the toolbar
#: (phase 2 fills them in); a document holding one validates, the editor cannot
#: insert one yet.
NODES: dict[str, dict[str, Any]] = {
    "doc": {"content": "block+"},
    "paragraph": {"group": "block", "content": "inline*"},
    "heading": {"group": "block", "content": "inline*", "attrs": {"level": HEADING_LEVELS}},
    "bulletList": {"group": "block", "content": "listItem+"},
    "orderedList": {"group": "block", "content": "listItem+"},
    "listItem": {"content": "block+"},
    "table": {"group": "block", "content": "tableRow+"},
    "tableRow": {
        "content": "(tableHeader | tableCell)+",
        "attrs": {"section": ("head", "body")},
    },
    "tableHeader": {"content": "block+", "attrs": {"colspan": "int?"}},
    "tableCell": {"content": "block+", "attrs": {"colspan": "int?"}},
    "figure": {
        "group": "block",
        "attrs": {
            "media_id": "int",
            "alt": "str?",
            "placement": FIGURE_PLACEMENTS,
            "caption": "str?",
            "legacy_size": LEGACY_FIGURE_SIZES,
            "width": "int?",
            "height": "int?",
        },
    },
    "columns": {"group": "block", "content": "column{1,2}", "attrs": {"align": ("top", "middle")}},
    "column": {"content": "block+"},
    "button": {
        "group": "block",
        "attrs": {"label": "str", "target": "str", "variant": ("primary", "secondary")},
    },
    "callout": {"group": "block", "content": "inline*"},
    "linkCard": {
        "group": "block",
        "attrs": {"title": "str", "line": "str?", "href": "str", "page_id": "int?"},
    },
    "cards": {"group": "block", "content": "card+", "attrs": {"heading": "str?"}},
    "card": {"attrs": {"title": "str", "line": "str?", "href": "str", "page_id": "int?"}},
    "form": {"group": "block", "attrs": {"form_id": "int"}},
    "value": {"group": "inline", "inline": True, "atom": True, "attrs": {"code": VALUE_CODES}},
    "hardBreak": {"group": "inline", "inline": True},
    "text": {"group": "inline", "text": True, "marks": ("bold", "italic", "strike", "link")},
}

#: The attribute a mark may carry: only ``link`` has one, its target.
MARK_ATTRS: dict[str, dict[str, Any]] = {"link": {"href": "str"}}

#: The sets (C4.5). The toolbar and the insert menu offer exactly these; the
#: editor's configuration is generated from this, never hand-written in a
#: template (gate 14).
BLOCK_SETS: dict[str, dict[str, Any]] = {
    # `value` is NOT in any phase-1 set: a placeholder code stays text in the
    # document and the renderer replaces it as it does today; the value BLOCK
    # is phase 5 (revised assignment, #1671). The node's shape stands in NODES
    # so the schema is the whole design from the start.
    "page": {
        "marks": ("bold", "italic", "strike", "link"),
        "headings": HEADING_LEVELS,
        "lists": ("bulletList", "orderedList"),
        "insert": ("table", "figure"),
    },
    # Phase 7; the shape stands here so the one schema is the whole design.
    "letter": {
        "marks": ("bold", "italic", "link"),
        "headings": (),
        "lists": ("bulletList", "orderedList"),
        "insert": ("figure", "button", "activity", "calendar", "closing"),
    },
    "notes": {
        "marks": ("bold", "italic", "strike"),
        "headings": HEADING_LEVELS,
        "lists": ("bulletList", "orderedList"),
        "insert": ("table",),
    },
}


#: The languages a document may be written in are the LANGUAGE codes of
#: `mdm.language_codes` ("nl"), not the locale of the tenant setting
#: ("nl_BE" decides how a date reads; the label lookup takes the language
#: part, CR-12 §F8). One place that translates, so the migration and the
#: service cannot drift apart.
def locale_language(locale: str) -> str:
    """The language part of a locale: `nl_BE` -> `nl`."""
    return (locale or "nl_BE").replace("-", "_").split("_")[0]


class OnbekendBlok(ValueError):
    """A document holds a node outside the schema (C6 test 2).

    Refused with its name — never stripped, never silently kept.
    """


class OnbekendAttribuut(ValueError):
    """A node carries an attribute the schema does not name, with a value
    the schema does not allow. Refused with the node's and the attribute's
    name."""


def validate_document(document: Any, set_name: str = "page") -> dict:
    """Validate a TipTap-shaped JSON document against the schema.

    Returns the document unchanged (a dict) or raises ``OnbekendBlok`` /
    ``OnbekendAttribuut`` naming what was refused. ``set_name`` decides
    nothing here — a document that validates, validates; the set decides
    what the EDITOR may insert, not what a stored document may hold. An
    unknown set is still a ``ValueError``: a set name is an identifier.
    """
    if set_name not in BLOCK_SETS:
        raise ValueError(f"Unknown block set: {set_name}")
    if not isinstance(document, dict):
        raise OnbekendBlok(f"Onbekend blok: {type(document).__name__}")
    _validate_node(document, "doc")
    return document


def _validate_node(node: Any, path: str) -> None:
    node_type = node.get("type") if isinstance(node, dict) else None
    if node_type not in NODES:
        raise OnbekendBlok(f"Onbekend blok: {node_type}")
    spec = NODES[node_type]
    for attr, value in (node.get("attrs") or {}).items():
        if attr not in spec.get("attrs", {}):
            raise OnbekendAttribuut(f"{node_type}.{attr}")
        allowed = spec["attrs"][attr]
        if isinstance(allowed, tuple):
            if value not in allowed:
                raise OnbekendAttribuut(f"{node_type}.{attr}={value!r}")
        elif allowed == "int" and not isinstance(value, int):
            raise OnbekendAttribuut(f"{node_type}.{attr}={value!r}")
        elif (
            allowed in ("int?", "str?")
            and value is not None
            and not isinstance(value, str if allowed == "str?" else int)
        ):
            raise OnbekendAttribuut(f"{node_type}.{attr}={value!r}")
    if spec.get("text"):
        if not isinstance(node.get("text", ""), str):
            raise OnbekendBlok(f"Onbekend blok: {node_type}")
        for mark in node.get("marks") or []:
            mark_type = mark.get("type") if isinstance(mark, dict) else None
            if mark_type not in spec.get("marks", ()):  # pragma: no cover - inline marks
                raise OnbekendBlok(f"Onbekend blok: {mark_type}")
            for attr in mark.get("attrs") or {}:
                if attr not in MARK_ATTRS.get(mark_type, {}):
                    raise OnbekendAttribuut(f"{mark_type}.{attr}")
    for child in node.get("content") or []:
        _validate_node(child, f"{path}/{node_type}")


def schema_for(set_name: str) -> dict[str, Any]:
    """The editor's configuration for one set, as data for the macro.

    Everything the browser needs to build the toolbar and the insert menu:
    the marks, the heading levels with their labels, the lists and the insert
    blocks, plus the value codes with their current labels and values (the
    chip shows what the visitor will see). Generated from the same schema the
    validation uses — that is the whole point of test 2.
    """
    if set_name not in BLOCK_SETS:
        raise ValueError(f"Unknown block set: {set_name}")
    from app.domains.cms.render import PLACEHOLDER_LABELS

    return {
        "set": set_name,
        "marks": list(BLOCK_SETS[set_name]["marks"]),
        "headings": [
            {"level": level, "label": label}
            for level, label in zip(
                BLOCK_SETS[set_name]["headings"],
                ("Kop", "Subkop", "Kleine kop"),
                strict=False,
            )
        ],
        "lists": list(BLOCK_SETS[set_name]["lists"]),
        "insert": list(BLOCK_SETS[set_name]["insert"]),
        "values": [
            {"code": code, "label": PLACEHOLDER_LABELS[code], "value": _value_of(code)}
            for code in VALUE_CODES
        ]
        if "value" in BLOCK_SETS[set_name]["insert"]
        else [],
        "nodes": sorted(NODES),
    }


def _value_of(code: str) -> str:
    """The current value of one code, for the editor's chip (no db: the
    configuration values are app settings, like the public renderer's)."""
    from app.domains.cms.render import _values

    return _values().get(code, "")


def json_schema() -> dict[str, Any]:
    """The schema of a document as JSON Schema (phase 4 serves it; built from
    the same source so it can never disagree, C6 test 2)."""

    def node_ref(name: str) -> dict[str, Any]:
        spec = NODES[name]
        props: dict[str, Any] = {"type": {"const": name}}
        if spec.get("text"):
            props["text"] = {"type": "string"}
        if spec.get("attrs"):
            props["attrs"] = {
                "type": "object",
                "properties": {
                    attr: _attr_schema(allowed) for attr, allowed in spec["attrs"].items()
                },
                "additionalProperties": False,
            }
        if spec.get("content"):
            props["content"] = {
                "type": "array",
                "items": {"$ref": "#/$defs/node"},
            }
        return {"type": "object", "properties": props, "additionalProperties": False}

    def _attr_schema(allowed: Any) -> dict[str, Any]:
        if isinstance(allowed, tuple):
            return {"enum": list(allowed)}
        if allowed == "int":
            return {"type": "integer"}
        if allowed == "str":
            return {"type": "string"}
        if allowed == "int?":
            return {"type": ["integer", "null"]}
        return {"type": ["string", "null"]}

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Raak web content document (CR-17)",
        "type": "object",
        "$defs": {
            "node": {"anyOf": [node_ref(name) for name in sorted(NODES)]},
        },
        "$ref": "#/$defs/node",
        "properties": {"type": {"const": "doc"}},
    }
