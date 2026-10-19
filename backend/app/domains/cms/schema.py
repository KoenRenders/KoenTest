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
from collections.abc import Iterable
from typing import Any

from app.i18n import _

#: The codes a value block can carry (CR-32 R19, from CR-17 C4.4): the two
#: membership amounts, the three dates, the year the membership runs to, and
#: the platform's list of sites — the one value that renders a list. The labels
#: and the current values come from the renderer/service; this is the one place
#: that says WHICH codes exist, because the migration of `{{code}}` maps exactly
#: these (`{{tenants:<account>}}` and `{{form:…}}` stay typed text).
VALUE_CODES: tuple[str, ...] = (
    "membership_price_full",
    "membership_price_half",
    "half_price_start",
    "half_price_end",
    "next_year_from",
    "membership_valid_until",
    "tenants",
)

#: The figures a page can place (C4.2): a figure placed through the editor
#: carries a placement and renders as the kit's figure with the public radius
#: and shadow (C4.8). No legacy sizes (Koen, 6 October 2026: no legacy
#: baggage): a page whose picture carries a Trix-era size keeps her HTML —
#: her words stand in the draft, and the author places the picture anew.
#: The order is the DIALOG's order too (schema_for zips her with the words):
#: full first — the default and the most chosen — then the placements that
#: set her beside the text, then the small one.
FIGURE_PLACEMENTS: tuple[str, ...] = ("full", "left", "right", "small")

#: The heading levels an author can choose: Kop, Subkop, Kleine kop — stored
#: as the levels they SHOW, h2–h4 (CR-32 R21/F19, Koen, 15 October 2026: "Akkoord
#: om de pagina te laten opslaan wat ze renderen"). The page's title is the only
#: h1 (#1656); the renderer shifts nothing. A fourth level typed through the old
#: HTML door does not convert losslessly and keeps its HTML (F11).
HEADING_LEVELS: tuple[int, ...] = (2, 3, 4)

#: The tones of a section and of a page's hero (CR-32 R8, F1): a name, never a
#: colour. The pixels come from the tenant's brand tokens at render time.
TONES: tuple[str, ...] = ("plain", "tint", "accent")

#: The data blocks of the page set (CR-32 F13, F14): nodes whose data a module
#: supplies at render time. Each is named in the registry (`home_blocks`) by the
#: module that owns it, so the editor offers it, and the save accepts it, only
#: where that module is on (`service._check_references`).
DATA_BLOCKS: tuple[str, ...] = ("activities", "albums")

#: The fixed ratios of a columns block (CR-32 #2101): equal, wide then narrow (3fr 2fr),
#: narrow then wide (2fr 3fr). The first is what an absent attribute means.
COLUMN_RATIOS: tuple[str, ...] = ("equal", "wide-narrow", "narrow-wide")

#: Where a button and a card may lead: the four destinations, of which a
#: node carries exactly one (`_one_destination`).
_DESTINATION_ATTRS: dict[str, Any] = {
    "page_id": "int?",
    "href": "str?",
    "form_slug": "str?",
    "screen": ("lid-worden", None),
}

#: Every node a document may hold, with its attributes (F1). Marks on ``text``:
#: bold, italic, strike, large, link. Every node here is one the renderer walks
#: (`test_every_node_of_the_schema_renders`): the schema holds what a stored
#: document may hold today, not the shapes of a later phase.
NODES: dict[str, dict[str, Any]] = {
    "doc": {
        # A page that shows nothing is an honest document — the migration's
        # net produces her (review 4, #1673) — so the root may hold no block
        # at all; every other node keeps its minimum.
        #
        # A `section` stands at the root and nowhere else (CR-32 F2a): it is
        # not in the group `block`, so no `block+` container (a column, a list
        # item, a cell, a quotation, a section) can hold one — the grammar
        # refuses it with the container's name, and the root names it here.
        "content": "(block | section | " + " | ".join(DATA_BLOCKS) + ")*",
    },
    # A band of the page (CR-32): blocks on a tone, with an optional small line
    # above them. A div on the site (the sanitiser knows no `section`), root
    # only (see "doc").
    "section": {"content": "block+", "attrs": {"tone": TONES, "eyebrow": "str?"}},
    "paragraph": {"group": "block", "content": "inline*"},
    "heading": {"group": "block", "content": "inline*", "attrs": {"level": HEADING_LEVELS}},
    "bulletList": {"group": "block", "content": "listItem+"},
    "orderedList": {
        "group": "block",
        "content": "listItem+",
        # TipTap's ordered list carries her own `start` (and a `type` the
        # editor writes as null) — the B1 test of #1699 measured the
        # emission. The `start` is the author's own and the site renders
        # her (Koen, option 1); a `type` the site ignores may not hold a
        # value at all: only the null the editor emits validates
        # (`"null?"`, the decision on #1699 — an attribute accepted and
        # ignored is the gap this closes).
        "attrs": {"start": "int?", "type": "null?"},
    },
    "listItem": {"content": "block+"},
    # A quotation (#1985; the Trix editor had one): blocks, as a list item
    # and a column hold them — the editor's own quotation holds `block+` and
    # the server accepts what the editor writes.
    "blockquote": {"group": "block", "content": "block+"},
    "table": {"group": "block", "content": "tableRow+"},
    "tableRow": {
        "content": "(tableHeader | tableCell)+",
        # A bare row (a table typed without <thead>) carries no section and
        # renders bare — None in the tuple marks the attribute optional.
        "attrs": {"section": ("head", "body", None)},
    },
    # A merged cell is the author's own (Koen, 8 October 2026: what the
    # editor shows and the author means, the site shows too): `colspan`
    # and `rowspan` are content and survive the round trip. The editor's
    # other cell attributes — column widths and alignment, chrome our
    # toolbar never offers and the site never shows — the save adapter
    # drops before this validation sees them.
    "tableHeader": {"content": "block+", "attrs": {"colspan": "int?", "rowspan": "int?"}},
    "tableCell": {"content": "block+", "attrs": {"colspan": "int?", "rowspan": "int?"}},
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
    "columns": {
        "group": "block",
        "content": "column{1,2}",
        # The ratio of the two columns (CR-32 #2101): a name, written on the site as a
        # class (the sanitiser lets no data attributes through). Absent: equal.
        "attrs": {"align": ("top", "middle"), "ratio": (*COLUMN_RATIOS, None)},
    },
    # A column holds blocks and, in a columns block at the root, the data blocks
    # (#2101; the rule is in `_validate_node`: nowhere deeper).
    "column": {"content": "(block | " + " | ".join(DATA_BLOCKS) + ")+"},
    # Where a button (and a card) may lead (Koen, 11 October 2026: "c, maar
    # enkel \"lid worden\" als onderdeel van deze CR"): a page of the site
    # (page_id — a reference that survives a slug change), an outside
    # address (href, http(s) only, refused at the save), a form of the
    # tenant (form_slug, resolved through forms' own door), and ONE
    # application screen — Lid worden. Exactly one of the four is set; the
    # one resolver (render.py) serves the button and the card alike.
    "button": {
        "group": "block",
        "attrs": {
            "label": "str",
            "variant": ("primary", "secondary"),
            **_DESTINATION_ATTRS,
        },
    },
    "callout": {"group": "block", "content": "inline*"},
    # C4.9: a block of link cards — layout, not data. A lone link card is a
    # cards block with one card (Q20/Q23); there is no second node for it.
    # No heading of its own (Koen, 13 October 2026: "b"): a title over the
    # cards is the ordinary heading block above them.
    "cards": {"group": "block", "content": "card+"},
    # A card is a link: her title, one line, an icon of the kit OR a picture
    # of the library (never both), labels as plain text, and exactly one of
    # the button's four destinations — the same attributes, so the one
    # resolver serves both. The icon's names are the kit's own
    # (`app.ui.kit.icons`, read from the `icon` macro): no list is kept here.
    "card": {
        "attrs": {
            "title": "str",
            # CR-32 R4: a card with no destination is a text card — a number, a
            # heading and a paragraph that only say something. Not a second node.
            "number": "str?",
            "text": "str?",
            "line": "str?",
            "icon": "str?",
            "media_id": "int?",
            "labels": "strs?",
            **_DESTINATION_ATTRS,
        }
    },
    # CR-32 R20 (from CR-17 F5): one album of the photo page — an archived
    # activity with photos — shown as a grid of its photos. A leaf: the data (the
    # photos) is the media module's, supplied at render time; the service refuses
    # an activity that is not an album at the save (the validator knows no data).
    "gallery": {"group": "block", "attrs": {"activity_id": "int"}},
    # CR-17 phase 7 (F9): the letter's three blocks, replacing the markers of the
    # Trix era. One activity of the activities module — the mail shows its picture,
    # name, when and where, and the sign-up link, built at the moment of sending;
    # the calendar of the activities the letter's own choices name ("In de
    # kalender"); and the closing every letter ends with. Leaves, built by the
    # mail renderer (`newsletter`); a page renders them as nothing.
    "activity": {"group": "block", "attrs": {"activity_id": "int"}},
    "calendar": {"group": "block"},
    "closing": {"group": "block"},
    # CR-32 R15 (F14): the upcoming activities as the home page shows them, at most
    # `count` of them; the data is the activities module's.
    # In no group, like `section`: a data block stands at the root and nowhere else
    # (the page template gives it a container of its own, outside the prose).
    "activities": {"attrs": {"count": tuple(range(1, 51))}},
    # CR-32 R13, R14 (F13): ONE card that moves through the latest `albums` albums
    # of the photo page, showing at most `photos` photos of each, every `interval`
    # seconds (0: it stands still); the media module supplies the data.
    "albums": {
        "attrs": {
            "albums": tuple(range(1, 7)),
            "photos": tuple(range(1, 9)),
            "interval": (0, *range(2, 11)),
        }
    },
    # A value may be large (#2095): "Lidgeld €35 per gezin" with only the amount
    # large. The one mark a value carries; bold and the rest stay on text.
    "value": {
        "group": "inline",
        "inline": True,
        "atom": True,
        "attrs": {"code": VALUE_CODES},
        "marks": ("large",),
    },
    "hardBreak": {"group": "inline", "inline": True},
    "text": {
        "group": "inline",
        "text": True,
        "marks": ("bold", "italic", "strike", "large", "link"),
    },
}

#: How a page opens (CR-32 F4, B8.11): the title line, or a hero — the title
#: large on a band, with an eyebrow, a lead and up to two buttons.
OPENINGS: tuple[str, ...] = ("title_line", "hero")

#: What a hero carries besides its tone, and how long its words may be.
HERO_BUTTONS_MAX = 2
_HERO_LIMITS = {"eyebrow": 80, "lead": 400, "label": 60}


def validate_hero(hero: Any) -> dict:
    """The hero of a page (CR-32 F4): `{tone, eyebrow?, lead?, buttons?}`, a
    button being a label and exactly one of the button block's four
    destinations. A property of the page, so it is validated at the page's
    save, not as part of a document; refused with the name of what is wrong,
    like every attribute of the schema. Returns the hero unchanged."""
    if not isinstance(hero, dict):
        raise InvalidShape("Onjuiste vorm: de hero")
    for key in hero:
        if key not in ("tone", "eyebrow", "lead", "buttons"):
            raise UnknownAttribute(f"hero.{key}")
    if hero.get("tone") not in TONES:
        raise UnknownAttribute(f"hero.tone={hero.get('tone')!r}")
    for key in ("eyebrow", "lead"):
        value = hero.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > _HERO_LIMITS[key]):
            raise UnknownAttribute(f"hero.{key}")
    buttons = hero.get("buttons") or []
    if not isinstance(buttons, list):
        raise InvalidShape("Onjuiste vorm: de knoppen van de hero")
    if len(buttons) > HERO_BUTTONS_MAX:
        raise InvalidShape("Te veel onderdelen in hero: hooguit twee knoppen")
    for button in buttons:
        if not isinstance(button, dict):
            raise InvalidShape("Onjuiste vorm: een knop van de hero")
        for key in button:
            if key != "label" and key not in _DESTINATION_ATTRS:
                raise UnknownAttribute(f"hero.button.{key}")
        label = button.get("label")
        if not isinstance(label, str) or not label.strip() or len(label) > _HERO_LIMITS["label"]:
            raise UnknownAttribute("hero.button.label")
        _one_destination("hero.button", "een knop van de hero", button)
        if button.get("page_id") is not None and (
            isinstance(button["page_id"], bool)
            or not isinstance(button["page_id"], int)
            or button["page_id"] <= 0
        ):
            raise UnknownAttribute(f"hero.button.page_id={button['page_id']!r}")
        for key in ("href", "form_slug"):
            if button.get(key) is not None and not isinstance(button[key], str):
                raise UnknownAttribute(f"hero.button.{key}")
        if button.get("screen") is not None and button["screen"] not in ("lid-worden",):
            raise UnknownAttribute(f"hero.button.screen={button['screen']!r}")
    return hero


def hero_from_form(tone: str, eyebrow: str, lead: str, buttons: list[tuple[str, str, str]]) -> dict:
    """The hero the page screen's fields describe: `buttons` are `(label,
    destination, address)` per button, the destination one of `page:<id>`,
    `form:<slug>`, `screen:lid-worden` or `href` (the address then holds the
    outside address). A button with no label and no destination is no button;
    anything else half-filled reaches `validate_hero` as it is and is refused
    there by name."""
    hero: dict[str, Any] = {"tone": tone}
    if eyebrow.strip():
        hero["eyebrow"] = eyebrow.strip()
    if lead.strip():
        hero["lead"] = lead.strip()
    made = []
    for label, destination, address in buttons:
        if not label.strip() and not destination:
            continue
        button: dict[str, Any] = {"label": label.strip()}
        kind, _, value = destination.partition(":")
        if kind == "page" and value.isdigit():
            button["page_id"] = int(value)
        elif kind == "form" and value:
            button["form_slug"] = value
        elif kind == "screen" and value:
            button["screen"] = value
        elif destination == "href":
            button["href"] = address.strip()
        made.append(button)
    if made:
        hero["buttons"] = made
    return hero


def hero_form_values(hero: dict | None) -> dict[str, Any]:
    """What `hero_from_form` was given, read back from a stored hero: the
    values the page screen's fields show."""
    hero = hero or {}
    values: dict[str, Any] = {
        "tone": hero.get("tone") or "plain",
        "eyebrow": hero.get("eyebrow") or "",
        "lead": hero.get("lead") or "",
        "buttons": [],
    }
    buttons = hero.get("buttons") or []
    for index in range(HERO_BUTTONS_MAX):
        button = buttons[index] if index < len(buttons) else {}
        if button.get("page_id") is not None:
            destination, address = f"page:{button['page_id']}", ""
        elif button.get("form_slug"):
            destination, address = f"form:{button['form_slug']}", ""
        elif button.get("screen"):
            destination, address = f"screen:{button['screen']}", ""
        elif button.get("href") is not None:
            destination, address = "href", button["href"]
        else:
            destination, address = "", ""
        values["buttons"].append(
            {"label": button.get("label") or "", "destination": destination, "address": address}
        )
    return values


#: The attributes a mark may carry. ``link`` has five: her target address
#: (required, text — an ``<a href="">`` renders nothing) and the
#: ``target``, ``rel``, ``class`` and ``title`` TipTap's link writes with
#: her (the B1 test of #1699 measured the emission, attribute by
#: attribute). The renderer reads the address only — the site keeps
#: opening links as she always did; what a link's ``target`` means on the
#: site is a later, separate decision.
MARK_ATTRS: dict[str, dict[str, Any]] = {
    "link": {"href": "str", "target": "str?", "rel": "str?", "class": "str?", "title": "str?"}
}

#: The sets (C4.5). The toolbar and the insert menu offer exactly these; the
#: editor's configuration is generated from this, never hand-written in a
#: template (gate 14).
BLOCK_SETS: dict[str, dict[str, Any]] = {
    # `value` is in the page set since CR-32 phase 4: the editor's Code item
    # inserts the node (a chip with the current value) and the migration turned
    # the typed `{{code}}` of every stored document into one.
    "page": {
        "marks": ("bold", "italic", "strike", "large", "link"),
        "headings": HEADING_LEVELS,
        "lists": ("bulletList", "orderedList"),
        # A block the toolbar turns on and off, as a list (#1985).
        "blocks": ("blockquote",),
        # C4.13's menu order: Tabel · Afbeelding · Kolommen · Knop · Kader ·
        # Kaarten.
        "insert": (
            "table",
            "figure",
            "columns",
            "button",
            "callout",
            "cards",
            "section",
            "gallery",
            "activities",
            "albums",
            "value",
        ),
    },
    # The letter (phase 7, F9): text, a picture, a button, an activity, the
    # calendar and the closing; the mail renderer gives it the letter's look.
    "letter": {
        "marks": ("bold", "italic", "link"),
        # One heading: a mail has one look for every level (`HEADING_STYLE`), so a
        # second and a third button would promise a difference the reader never sees.
        "headings": (2,),
        "lists": ("bulletList", "orderedList"),
        "blocks": (),
        "insert": ("figure", "button", "activity", "calendar", "closing"),
    },
    "notes": {
        "marks": ("bold", "italic", "strike"),
        "headings": HEADING_LEVELS,
        "lists": ("bulletList", "orderedList"),
        "blocks": (),
        "insert": ("table",),
    },
}


#: The table menu of the editor (CR-17 phase 2, #1679): what the author may
#: do to a table, in the order the menu shows her — the header row is the
#: organiser's own choice and rows and columns come and go in the editor
#: (C4.13). The words are UI copy behind `_()` and travel in the
#: configuration like every word the editor shows; the ids are TableKit's
#: command names, the only ones the pinned bundle ships.
TABLE_MENU: tuple[tuple[str, str], ...] = (
    ("addRowBefore", _("Rij boven toevoegen")),
    ("addRowAfter", _("Rij onder toevoegen")),
    ("addColumnBefore", _("Kolom links toevoegen")),
    ("addColumnAfter", _("Kolom rechts toevoegen")),
    ("deleteRow", _("Rij verwijderen")),
    ("deleteColumn", _("Kolom verwijderen")),
    ("toggleHeaderRow", _("Koprij aan of uit")),
    ("deleteTable", _("Tabel verwijderen")),
)


#: The cards menu of the editor (CR-17, C4.9): what the author does to the
#: card she stands on. The ids are the script's own commands.
CARDS_MENU: tuple[tuple[str, str], ...] = (
    ("edit", _("Kaart bewerken")),
    ("add", _("Kaart toevoegen")),
    ("forward", _("Naar voren")),
    ("back", _("Naar achteren")),
    ("remove", _("Kaart verwijderen")),
)


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
    if document.get("type") != "doc":
        # The root is the document itself; a paragraph (or a text node) at
        # the top is a client's mistake, not a document (review A3, #1699).
        raise InvalidShape(f"Onjuiste wortel: {document.get('type')}")
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
        allowed = set()
        for part in (p.strip() for p in selector[1:-1].split("|")):
            if part in ("block", "inline"):
                allowed |= {t for t, spec in NODES.items() if spec.get("group") == part}
            else:
                allowed.add(part)
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


#: How deep a document may nest before the validator refuses her — the
#: schema's own deepest path is five (doc/table/row/cell/paragraph); the cap
#: is generous but finite, so a hostile or looping client cannot recurse the
#: validator to death (review A2, #1699).
MAX_DEPTH = 64


def destinations_set(attrs: dict) -> list[str]:
    """The destinations a button or a card carries: the kinds of
    `_DESTINATION_ATTRS` that hold a value. ONE rule for "has a destination"
    (CR-32 Z1): an empty address is no destination — the validator counts
    with it, the renderer decides *text card or link* with it, and the editor
    is handed the kinds (`schema_for`) and reads its cards by the same rule,
    so a card cannot be a text card to one and a link to another."""
    return [k for k in _DESTINATION_ATTRS if attrs.get(k) not in (None, "")]


def _one_destination(node_type: str, word: str, attrs: dict, *, optional: bool = False) -> None:
    """Koen's four destinations (11 October 2026) are a shape rule of the
    button and of the card alike: exactly one of them is set — two is a
    document the resolver cannot resolve, none a link that leads nowhere. An
    outside address is http(s) only and one unbroken word — a space inside is
    refused here and in the dialog, by the same rule (C4.11: nothing is
    stripped at render; review of 12 October 2026: `https://a b` passed both
    ends, which agreed on the start only). `word` is the block's name in the
    refusal ("een knop", "een kaart")."""
    targets = destinations_set(attrs)
    if optional and not targets:
        return
    if len(targets) != 1:
        raise InvalidShape(
            f"Onjuiste vorm: {word} wijst naar precies één bestemming"
            + (f" (nu {', '.join(targets)})" if len(targets) > 1 else "")
        )
    if "href" in targets:
        href = attrs["href"]
        if (
            not isinstance(href, str)
            or not href.startswith(("http://", "https://"))
            or any(ch.isspace() for ch in href)
        ):
            raise UnknownAttribute(f"{node_type}.href={href!r}")


def _validate_node(node: Any, path: str) -> None:
    if path.count("/") >= MAX_DEPTH:
        raise InvalidShape("Te diep genest: het document heeft te veel niveaus")
    node_type = node.get("type") if isinstance(node, dict) else None
    if node_type not in NODES:
        raise UnknownBlock(f"Onbekend blok: {node_type}")
    spec = NODES[node_type]
    # A malformed document is refused with a name, never a crash (review A2,
    # #1699): attributes and children that are not the shape the schema
    # reads — a string, a number — are named, not iterated.
    raw_attrs = node.get("attrs")
    if raw_attrs is None:
        attrs = {}
    elif isinstance(raw_attrs, dict):
        attrs = raw_attrs
    else:
        raise InvalidShape(f"Onjuiste kenmerken: {node_type}")
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
            # An id is a row that exists: 0 and negatives are "no image",
            # "no form" — refused (review A3, #1699; the PR's own promise).
            # A list's `start` is her number, and a merged cell spans at
            # least one row and one column: whole numbers of one or more
            # (the decision on #1699 and the table's, of 8 October).
            elif (
                value is not None
                and (attr.endswith("_id") or attr in ("start", "colspan", "rowspan"))
                and value <= 0
            ):
                raise UnknownAttribute(f"{node_type}.{attr}={value!r}")
        elif allowed == "null?":
            # Only the null the editor emits (the ordered list's `type`,
            # #1699): a value the site ignores may not be stored.
            if value is not None:
                raise UnknownAttribute(f"{node_type}.{attr}={value!r}")
        elif allowed in ("str", "str?"):
            if not isinstance(value, str):
                if allowed == "str" or value is not None:
                    raise UnknownAttribute(f"{node_type}.{attr}={value!r}")
        elif allowed == "strs?":
            # A list of short texts (a card's labels): every one a text with
            # words in it — an empty label renders a lone middle dot.
            if value is not None and (
                not isinstance(value, list)
                or any(not isinstance(item, str) or not item.strip() for item in value)
            ):
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
    if node_type == "button":
        _one_destination("button", "een knop", attrs)
    if node_type == "card":
        # A card without a destination is a text card (CR-32 R4); two are
        # still refused — the resolver could not choose.
        _one_destination("card", "een kaart", attrs, optional=True)
        # A title is words, not an empty string: the whole card is the link
        # and the title is what it is called.
        if not attrs["title"].strip():
            raise UnknownAttribute("card.title")
        if attrs.get("icon") is not None and attrs.get("media_id") is not None:
            raise InvalidShape(
                "Onjuiste vorm: een kaart heeft een icoon of een afbeelding, niet beide"
            )
        if attrs.get("icon") is not None:
            from app.ui.kit.icons import icon_names

            if attrs["icon"] not in icon_names():
                raise UnknownAttribute(f"card.icon={attrs['icon']!r}")
    if spec.get("text") or spec.get("marks"):
        if spec.get("text"):
            # A text node carries words: the key is there and the string is not
            # empty (review A3, #1699) — an empty text node renders nothing and
            # means nothing.
            text = node.get("text")
            if not isinstance(text, str) or not text:
                raise InvalidShape("Tekst zonder inhoud")
        raw_marks = node.get("marks")
        if raw_marks is None:
            marks: list[Any] = []
        elif isinstance(raw_marks, list):
            marks = raw_marks
        else:
            raise InvalidShape(f"Onjuiste markeringen: {node_type}")
        for mark in marks:
            if not isinstance(mark, dict):
                raise UnknownBlock(f"Onbekend blok: {mark}")
            mark_type = mark.get("type")
            if mark_type not in spec.get("marks", ()):  # pragma: no cover - inline marks
                raise UnknownBlock(f"Onbekend blok: {mark_type}")
            # A mark's attributes are a map, typed like every node's (A2's
            # last crash and the second look's typing, #1699): a list here
            # crashed, a number in a ``str?`` stayed valid — both refused
            # with the mark's and the attribute's name now.
            raw_mark_attrs = mark.get("attrs")
            if raw_mark_attrs is None:
                mark_attrs: dict[str, Any] = {}
            elif isinstance(raw_mark_attrs, dict):
                mark_attrs = raw_mark_attrs
            else:
                raise InvalidShape(f"Onjuiste kenmerken: {mark_type}")
            for attr in mark_attrs:
                if attr not in MARK_ATTRS.get(str(mark_type), {}):
                    raise UnknownAttribute(f"{mark_type}.{attr}")
            # A link without her target renders `<a href="">` — nothing;
            # the optional attributes are typed too, not just named.
            for attr, allowed_kind in MARK_ATTRS.get(str(mark_type), {}).items():
                value = mark_attrs.get(attr)
                if allowed_kind == "str" and (not isinstance(value, str) or not value):
                    raise UnknownAttribute(f"{mark_type}.{attr}={value!r}")
                if allowed_kind == "str?" and value is not None and not isinstance(value, str):
                    raise UnknownAttribute(f"{mark_type}.{attr}={value!r}")
    elif isinstance(node.get("text"), str):
        # A flattened text node (a paragraph with a "text" key) is the
        # mistake a hand-rolled client makes; refuse it as a place, not a
        # name — the block itself is known.
        raise InvalidShape(f"Onjuiste plaats: tekst in {node_type}")
    if node.get("marks") and not (spec.get("text") or spec.get("marks")):
        raise UnknownAttribute(f"{node_type}.marks")
    # The shape half (B1): every child where its parent allows it, and the
    # parent holding what her expression demands. The child's own name is
    # checked FIRST — an unknown block keeps her pinned message, whatever
    # her position (the JSON door, test 18).
    rule = _content_rule(node_type)
    raw_children = node.get("content")
    if raw_children is None:
        children: list[Any] = []
    elif isinstance(raw_children, list):
        children = raw_children
    else:
        raise InvalidShape(f"Onjuiste inhoud: {node_type}")
    if rule is None:
        if children:
            raise InvalidShape(f"Onjuiste plaats: onder {node_type}")
        return
    allowed_children, minimum, maximum = rule
    for child in children:
        child_type = child.get("type") if isinstance(child, dict) else None
        if child_type not in NODES:
            if isinstance(child, dict):
                raise UnknownBlock(f"Onbekend blok: {child_type}")
            raise UnknownBlock(f"Onbekend blok: {type(child).__name__}")
        if child_type not in allowed_children:
            raise InvalidShape(f"Onjuiste plaats: {child_type} onder {node_type}")
        if node_type == "column" and child_type == "columns":
            # The design review's B5 (#1679): a column holds blocks, not a
            # second columns block that breaks out of her column.
            raise InvalidShape("Onjuiste plaats: kolommen in een kolom")
        if node_type == "column" and child_type in DATA_BLOCKS and path != "doc/doc/columns":
            # #2101: a data block stands at the root, or in a column of a columns
            # block that stands at the root — not in a section, a quotation or a cell.
            raise InvalidShape(f"Onjuiste plaats: {child_type} onder kolom buiten de wortel")
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
        "large": _("Groot"),
        "link": _("Link"),
        "bulletList": _("Lijst"),
        "orderedList": _("Genummerde lijst"),
        "blockquote": _("Citaat"),
        "table": _("Tabel"),
        "figure": _("Afbeelding"),
        "columns": _("Kolommen"),
        "button": _("Knop"),
        "callout": _("Kader"),
        "cards": _("Kaarten"),
        "section": _("Sectie"),
        "gallery": _("Galerij"),
        "activity": _("Activiteit"),
        "calendar": _("Kalender"),
        "closing": _("Afsluiting"),
        "activities": _("Activiteiten"),
        "albums": _("Albumkaart"),
        "value": _("Code"),
    }.get(command_id, command_id)


def schema_for(
    set_name: str,
    *,
    albums: "list[tuple[int, str]] | None" = None,
    letter_activities: "list[tuple[int, str]] | None" = None,
    data_blocks: "Iterable[str] | None" = None,
) -> dict[str, Any]:
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

    # The data blocks the caller's tenant may use (its modules): the others are
    # left out of the menu and of the nodes the editor registers.
    offered = set(DATA_BLOCKS) if data_blocks is None else set(data_blocks)
    insert = [
        name
        for name in BLOCK_SETS[set_name]["insert"]
        if name not in DATA_BLOCKS or name in offered
    ]

    return {
        "set": set_name,
        "marks": list(BLOCK_SETS[set_name]["marks"]),
        "headings": [
            {"level": level, "label": label}
            for level, label in zip(
                BLOCK_SETS[set_name]["headings"],
                # UI copy behind `_()` — a translator owns these (review C,
                # #1699), like the toolbar's words.
                (_("Kop"), _("Subkop"), _("Kleine kop")),
                strict=False,
            )
        ],
        "lists": list(BLOCK_SETS[set_name]["lists"]),
        "blocks": list(BLOCK_SETS[set_name]["blocks"]),
        "insert": insert,
        # The data blocks of this set the caller's tenant may use: the editor's
        # document node lets exactly these stand at the root, beside the sections.
        "dataBlocks": [name for name in DATA_BLOCKS if name in insert],
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
            "blocks": [
                {"id": name, "label": _toolbar_label(name)}
                for name in BLOCK_SETS[set_name]["blocks"]
            ],
            "insertMenu": _("Blok invoegen"),
            "insert": [{"id": name, "label": _toolbar_label(name)} for name in insert],
            # The table menu (phase 2, #1679): the commands the author gets
            # on a table, generated here like the rest of the toolbar. The
            # menu appears in the editor when the cursor stands in a table;
            # `None` for a set that offers no table (the menu belongs to
            # the sets that do — `page` and `notes`).
            "tableMenu": (
                {
                    "label": _("Tabel"),
                    "items": [{"id": cmd, "label": label} for cmd, label in TABLE_MENU],
                }
                if "table" in BLOCK_SETS[set_name]["insert"]
                else None
            ),
            # The cards menu, the same way: shown while a card is selected.
            "cardsMenu": (
                {
                    "label": _("Kaarten"),
                    "items": [{"id": cmd, "label": label} for cmd, label in CARDS_MENU],
                }
                if "cards" in BLOCK_SETS[set_name]["insert"]
                else None
            ),
        },
        "values": [
            {"code": code, "label": PLACEHOLDER_LABELS[code], "value": _value_of(code)}
            for code in VALUE_CODES
        ]
        if "value" in BLOCK_SETS[set_name]["insert"]
        else [],
        # The figure dialog and the editor's figure (slice 3): the placements
        # the author chooses between — the same set the validation accepts,
        # generated here like the toolbar — and the address every picture is
        # served under. Media owns that shape (`media_url_prefix`, CR-15
        # §C4.6): the editor's preview asks here, so the browser carries no
        # URL of her own. `None` for a set without the figure block: the
        # dialog and the figure button belong to the sets that offer her.
        "figure": (
            {
                "placements": [
                    {"id": placement, "label": label}
                    for placement, label in zip(
                        FIGURE_PLACEMENTS,
                        # UI copy behind `_()` — a translator owns these
                        # (review C, #1699), like every word the editor
                        # shows. The words follow the PLACEMENTS' order —
                        # a misaligned pair was measured in the browser
                        # ("Rechts" carried the id "full").
                        (_("Vol"), _("Links"), _("Rechts"), _("Klein")),
                        strict=False,
                    )
                ],
                "mediaUrl": _media_url_prefix(),
            }
            if "figure" in BLOCK_SETS[set_name]["insert"]
            else None
        ),
        # The card dialog's choice of icons: the kit's own names, asked of
        # the kit (`app.ui.kit.icons`) — the same list the validation asks.
        "cards": (
            {"icons": list(_icon_names()), "destinations": list(_DESTINATION_ATTRS)}
            if "cards" in BLOCK_SETS[set_name]["insert"]
            else None
        ),
        # The words of the album card's settings, in the block itself (CR-32 R13).
        "albumCard": (
            {
                "albums": _("Albums"),
                "photos": _("Foto's per album"),
                "interval": _("Seconden (0 = staat stil)"),
            }
            if "albums" in insert
            else None
        ),
        # The gallery's dialog (CR-32 R20): the albums the author may choose between
        # — `(activity id, label)` from the caller, who owns the data; none when
        # there is no album, and then the menu offers no gallery.
        "gallery": (
            {
                "albums": [{"id": album_id, "label": label} for album_id, label in albums],
                "albumLabel": _("Album"),
            }
            if albums and "gallery" in BLOCK_SETS[set_name]["insert"]
            else None
        ),
        # The letter's activity dialog (CR-17 phase 7): the activities the letter
        # features — `(activity id, label)` from the caller, who owns the data.
        "activity": (
            {
                "activities": [{"id": i, "label": label} for i, label in (letter_activities or [])],
                "activityLabel": _("Activiteit"),
                "emptyLabel": _("Kies eerst uitgelichte activiteiten bovenaan de brief."),
            }
            if "activity" in BLOCK_SETS[set_name]["insert"]
            else None
        ),
        # The section's tone choice, in words (CR-32): the same names the
        # validation accepts.
        "section": (
            {
                "tones": [
                    {"id": tone, "label": label}
                    for tone, label in zip(
                        TONES, (_("Neutraal"), _("Tint"), _("Accent")), strict=True
                    )
                ],
                "toneLabel": _("Tint van de sectie"),
                "eyebrowLabel": _("Bovenkopje"),
                "removeLabel": _("Sectie verwijderen"),
            }
            if "section" in BLOCK_SETS[set_name]["insert"]
            else None
        ),
        # The ratio choice of a columns block (#2101), in words.
        "columns": (
            {
                "ratios": [
                    {"id": ratio, "label": label}
                    for ratio, label in zip(
                        COLUMN_RATIOS,
                        (_("Gelijk"), _("Breed – smal"), _("Smal – breed")),
                        strict=True,
                    )
                ],
                "ratioLabel": _("Verhouding van de kolommen"),
            }
            if "columns" in BLOCK_SETS[set_name]["insert"]
            else None
        ),
        "nodes": sorted(NODES),
    }


def _icon_names() -> tuple[str, ...]:
    from app.ui.kit.icons import icon_names

    return icon_names()


def _media_url_prefix() -> str:
    """The picture address without her id — media's facade, lazily imported
    (media imports this facade back for `uses_by_asset`'s questions)."""
    from app.domains.media.api import media_url_prefix

    return media_url_prefix()


def _value_of(code: str) -> str:
    """The current value of one code, for the editor's chip (no db: the
    configuration values are app settings, like the public renderer's)."""
    from app.domains.cms.render import _values, sites_in_words

    if code == "tenants":
        return sites_in_words(None)
    return _values().get(code, "")
