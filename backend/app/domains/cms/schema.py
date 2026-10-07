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

import re
from typing import Any

from app.i18n import _

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

#: The figures a page can place (C4.2): a figure placed through the editor
#: carries a placement and renders as the kit's figure with the public radius
#: and shadow (C4.8). No legacy sizes (Koen, 6 October 2026: no legacy
#: baggage): a page whose picture carries a Trix-era size keeps her HTML —
#: her words stand in the draft, and the author places the picture anew.
FIGURE_PLACEMENTS: tuple[str, ...] = ("left", "right", "full", "small")

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
    "doc": {
        # A page that shows nothing is an honest document — the migration's
        # net produces her (review 4, #1673) — so the root may hold no block
        # at all; every other node keeps its minimum.
        "content": "block*"
    },
    "paragraph": {"group": "block", "content": "inline*"},
    "heading": {"group": "block", "content": "inline*", "attrs": {"level": HEADING_LEVELS}},
    "bulletList": {"group": "block", "content": "listItem+"},
    "orderedList": {"group": "block", "content": "listItem+"},
    "listItem": {"content": "block+"},
    "table": {"group": "block", "content": "tableRow+"},
    "tableRow": {
        "content": "(tableHeader | tableCell)+",
        # A bare row (a table typed without <thead>) carries no section and
        # renders bare — None in the tuple marks the attribute optional.
        "attrs": {"section": ("head", "body", None)},
    },
    "tableHeader": {"content": "block+", "attrs": {"colspan": "int?"}},
    "tableCell": {"content": "block+", "attrs": {"colspan": "int?"}},
    "figure": {
        "group": "block",
        "attrs": {
            "media_id": "int",
            "alt": "str?",
            # Optional: a converted figure carries no placement and the
            # renderer places her full width (None marks the attribute
            # optional, like the row's section).
            "placement": (*FIGURE_PLACEMENTS, None),
            "caption": "str?",
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
        # Phase 7's activity, calendar and closing nodes do not exist yet; a set
        # may not offer what the schema refuses (review B3, #1673) - they join
        # when phase 7 adds their shapes.
        "insert": ("figure", "button"),
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


class UnknownBlock(ValueError):
    """A document holds a node outside the schema (C6 test 2).

    Refused with its name — never stripped, never silently kept.
    """


class UnknownAttribute(ValueError):
    """A node carries an attribute the schema does not name, with a value
    the schema does not allow. Refused with the node's and the attribute's
    name."""


class InvalidShape(ValueError):
    """A node sits where the schema does not allow it (C6 test 2, the shape
    half — built as slice 2's first step: from the editor on, documents
    arrive from a browser).

    Refused with the names the author needs — the node and where it was
    put. The message is UI copy (Dutch), like the other refusals.
    """


def validate_document(document: Any, set_name: str = "page") -> dict:
    """Validate a TipTap-shaped JSON document against the schema.

    Returns the document unchanged (a dict) or raises ``UnknownBlock`` /
    ``UnknownAttribute`` / ``InvalidShape`` naming what was refused.

    Names AND shape (Koen, 6 October 2026: the border is the editor, not the
    API — slice 2's editor saves documents from the browser, so the server
    decides what a document may hold): a node must be one the schema knows,
    an attribute one it lists with a value of the allowed kind, a required
    attribute present, and every child where its parent's content expression
    allows it. The root may be empty — a page that shows nothing is honest.
    ``set_name`` decides nothing here — a document that validates, validates;
    the set decides what the EDITOR may insert, not what a stored document
    may hold. An unknown set is still a ``ValueError``: a set name is an
    identifier.
    """
    if set_name not in BLOCK_SETS:
        raise ValueError(f"Unknown block set: {set_name}")
    if not isinstance(document, dict):
        raise UnknownBlock(f"Onbekend blok: {type(document).__name__}")
    _validate_node(document, "doc")
    return document


#: The content expressions this schema uses. The parser below reads them
#: from ``NODES`` — one source: a new expression must teach it, not bypass
#: it (an unsupported one is a loud error, never a silent pass).
_CONTENT_EXPR = re.compile(r"(\([^)]+\)|[a-zA-Z]+)([+*]|\{\d+,\d+\})")


def _content_rule(node_type: str) -> tuple[set[str], int, int | None] | None:
    """The children a node may hold: ``(allowed child types, minimum,
    maximum)``, read from the content expression in ``NODES``. ``None`` marks
    a leaf: no children at all.
    """
    expression = NODES[node_type].get("content")
    if not expression:
        return None
    match = _CONTENT_EXPR.fullmatch(expression)
    if not match:
        raise ValueError(f"Unsupported content expression: {node_type}: {expression}")
    selector, quantifier = match.group(1), match.group(2)
    if selector.startswith("("):
        allowed = {part.strip() for part in selector[1:-1].split("|")}
    elif selector in ("block", "inline"):
        allowed = {t for t, spec in NODES.items() if spec.get("group") == selector}
    else:
        allowed = {selector}
    if quantifier == "+":
        return allowed, 1, None
    if quantifier == "*":
        return allowed, 0, None
    low, high = quantifier[1:-1].split(",")
    return allowed, int(low), int(high)


def _validate_node(node: Any, path: str) -> None:
    node_type = node.get("type") if isinstance(node, dict) else None
    if node_type not in NODES:
        raise UnknownBlock(f"Onbekend blok: {node_type}")
    spec = NODES[node_type]
    attrs = node.get("attrs") or {}
    for attr, value in attrs.items():
        if attr not in spec.get("attrs", {}):
            raise UnknownAttribute(f"{node_type}.{attr}")
        allowed = spec["attrs"][attr]
        if isinstance(allowed, tuple):
            # None in the tuple marks the attribute optional: absent (or
            # None) is "not set" — a bare table row carries no section, a
            # converted figure no placement. An int-tuple refuses 2.0 and
            # True on top of that — bool is an int in Python, and both pass
            # a bare membership test (review B1's "a numeric label").
            if value is None:
                if None not in allowed:
                    raise UnknownAttribute(f"{node_type}.{attr}={value!r}")
            elif all(
                isinstance(member, int) and not isinstance(member, bool)
                for member in allowed
                if member is not None
            ):
                if isinstance(value, bool) or not isinstance(value, int) or value not in allowed:
                    raise UnknownAttribute(f"{node_type}.{attr}={value!r}")
            elif not isinstance(value, str) or value not in allowed:
                raise UnknownAttribute(f"{node_type}.{attr}={value!r}")
        elif allowed in ("int", "int?"):
            if isinstance(value, bool) or not isinstance(value, int):
                if allowed == "int" or value is not None:
                    raise UnknownAttribute(f"{node_type}.{attr}={value!r}")
        elif allowed in ("str", "str?"):
            if not isinstance(value, str):
                if allowed == "str" or value is not None:
                    raise UnknownAttribute(f"{node_type}.{attr}={value!r}")
    # Required attributes (the shape half of B1): a figure without her
    # media id, a button without her label refused — not just names. A "?"
    # type or a None inside an enum tuple marks the attribute optional.
    for attr, allowed in spec.get("attrs", {}).items():
        optional = (isinstance(allowed, str) and allowed.endswith("?")) or (
            isinstance(allowed, tuple) and None in allowed
        )
        if optional:
            continue
        if attr not in attrs or attrs[attr] is None:
            raise UnknownAttribute(f"{node_type}.{attr}")
    if spec.get("text"):
        if not isinstance(node.get("text", ""), str):
            raise UnknownBlock(f"Onbekend blok: {node_type}")
        for mark in node.get("marks") or []:
            if not isinstance(mark, dict):
                raise UnknownBlock(f"Onbekend blok: {mark}")
            mark_type = mark.get("type")
            if mark_type not in spec.get("marks", ()):  # pragma: no cover - inline marks
                raise UnknownBlock(f"Onbekend blok: {mark_type}")
            for attr in mark.get("attrs") or {}:
                if attr not in MARK_ATTRS.get(str(mark_type), {}):
                    raise UnknownAttribute(f"{mark_type}.{attr}")
    elif isinstance(node.get("text"), str):
        # A flattened text node (a paragraph with a "text" key) is the
        # mistake a hand-rolled client makes; refuse it as a place, not a
        # name — the block itself is known.
        raise InvalidShape(f"Onjuiste plaats: tekst in {node_type}")
    if node.get("marks") and not spec.get("text"):
        raise UnknownAttribute(f"{node_type}.marks")
    # The shape half (B1): every child where its parent allows it, and the
    # parent holding what her expression demands. The child's own name is
    # checked FIRST — an unknown block keeps her pinned message, whatever
    # her position (the JSON door, test 18).
    rule = _content_rule(node_type)
    children = node.get("content") or []
    if rule is None:
        if children:
            raise InvalidShape(f"Onjuiste plaats: onder {node_type}")
        return
    allowed_children, minimum, maximum = rule
    for child in children:
        child_type = child.get("type") if isinstance(child, dict) else None
        if child_type not in NODES:
            raise UnknownBlock(f"Onbekend blok: {child_type}")
        if child_type not in allowed_children:
            raise InvalidShape(f"Onjuiste plaats: {child_type} onder {node_type}")
        _validate_node(child, f"{path}/{node_type}")
    if len(children) < minimum:
        raise InvalidShape(f"Leeg blok: {node_type}")
    if maximum is not None and len(children) > maximum:
        raise InvalidShape(f"Te veel onderdelen in {node_type}")


#: The toolbar's words, one per node and command the editor offers. UI copy
#: behind `_()` — a translator owns these (the codes gate's question), the
#: same way the macro's own words stand in the templates; the JS takes them
#: from `schema_for` and never writes its own.
def _toolbar_label(command_id: str) -> str:
    return {
        "bold": _("Vet"),
        "italic": _("Cursief"),
        "strike": _("Doorgehaald"),
        "link": _("Link"),
        "bulletList": _("Lijst"),
        "orderedList": _("Genummerde lijst"),
        "table": _("Tabel"),
        "figure": _("Afbeelding"),
    }.get(command_id, command_id)


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
        # The toolbar, as the browser builds her from this configuration
        # (slice 2): the words are UI copy behind `_()` and live HERE, not
        # in the JS.
        "toolbar": {
            "marks": [
                {"id": mark, "label": _toolbar_label(mark)}
                for mark in BLOCK_SETS[set_name]["marks"]
            ],
            "lists": [
                {"id": name, "label": _toolbar_label(name)}
                for name in BLOCK_SETS[set_name]["lists"]
            ],
            "insertMenu": _("Blok invoegen"),
            "insert": [
                {"id": name, "label": _toolbar_label(name)}
                for name in BLOCK_SETS[set_name]["insert"]
            ],
        },
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
