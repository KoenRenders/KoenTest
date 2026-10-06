"""HTML → document, the lossless migration of existing pages (CR-17 phase 1,
#1671; C4.12, test 12).

An existing page's content is stored HTML from the Trix era. This module turns
it into a block document — or refuses, page by page: the proof of "lossless"
is a measurement, not a hope. The parser builds the document, renders it back
with the same renderer the site will use, and compares that against what the
page shows today (``render_cms_content``, sanitised, with the same
heading shift). Equal → the document stands; unequal → the page keeps its HTML
and appears on the list of pages that did not migrate (F11).

What it accepts is exactly what the sanitiser allows AND the schema names:
paragraph, headings, the two lists, links, bold/italic/strike, a line break, a
table, and a picture (a Trix attachment lifted onto its ``<img>``). A
placeholder code stays TEXT in the document - the renderer replaces the
codes as it does today; the value BLOCK is phase 5 (revised assignment,
#1671). Anything
else — a quote, a pre block, a bare ``<hr>``, a fifth heading level, an
inline image — flags the page, and that is deliberate: a page the parser
cannot prove byte-equal is a page the site keeps serving exactly as it does
today (R17).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Optional

from app.domains.cms.render import (
    _blocks_html,
    headings_one_level_down,
    image_attributes_from_attachment,
    sanitize_cms_html,
)

_MARK_FOR = {
    "b": "bold",
    "strong": "bold",
    "i": "italic",
    "em": "italic",
    "s": "strike",
    "del": "strike",
}
_BLOCK_TAGS = {
    "p",
    "br",
    "h1",
    "h2",
    "h3",
    "h4",
    "ul",
    "ol",
    "li",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "img",
    "blockquote",
    "pre",
    "hr",
    "div",
    "span",
    "h5",
    "h6",
    "figure",
    "figcaption",
    "caption",
}
_TEXTUAL = re.compile(r"\S")


def _normalise(html_text: str) -> str:
    """Whitespace-insensitive comparison: what stands between tags does not
    matter, what stands inside a text run does (kept as-is)."""
    return re.sub(r">\s+<", "><", html_text.strip())


def parse_html(
    content: Optional[str], *, on_page: bool = True, lenient: bool = False
) -> Optional[dict]:
    """A page's stored HTML as a document — or None when it does not render
    back to what the page shows today.

    ``on_page`` mirrors the public render call the page gets (``R17``: the
    comparison must be with what the VISITOR sees, and a page body shows its
    headings one level down).

    ``lenient`` (F11, the draft of a page that does not convert losslessly):
    never returns None — an unknown tag degrades to its words instead of
    failing the page, a fourth heading level becomes Kleine kop. The result
    is a DRAFT for the editor to compare with the live page, not a document
    the site serves; publishing it is the author's decision.

    The comparison deliberately skips the substitutions (the configuration
    codes, the sites cards, a form button): both sides would carry the same
    ones, and the MIGRATION runs inside alembic's one transaction over the
    whole chain — a second connection (which reading the tenant's settings
    needs) sees a database that is still empty. Nothing outside this
    transaction is read here.
    """
    if not content:
        # An empty page has an empty document — the same nothing, as a block.
        return {"type": "doc", "content": []}
    opgeschoond = sanitize_cms_html(image_attributes_from_attachment(content)) or ""
    # The shift lives in the RENDERER (on_page, #1656): the document stores the
    # author's own level, so the parser feeds the unshifted HTML and the
    # comparison shifts the document's output — never both sides (measured:
    # a double shift turned every heading two levels down).
    today = headings_one_level_down(opgeschoond) if on_page else opgeschoond
    builder = _Builder(lenient=lenient)
    _DocumentParser(builder).feed(opgeschoond)
    document = {"type": "doc", "content": builder.blocks}
    if lenient:
        return document
    if not builder.lossless:
        return None
    uit_document = sanitize_cms_html(_blocks_html(document["content"], on_page=on_page)) or ""
    if _normalise(uit_document) != _normalise(today):
        # The measurement, not the parser's opinion: whatever the builder
        # thought, the round trip decides (test 12 is this line, per page).
        return None
    return document


class _Builder:
    """Collects the document while the parser walks the HTML."""

    def __init__(self, lenient: bool = False) -> None:
        self.lenient = lenient
        self.blocks: list[dict] = []
        self.lossless = True
        # The paragraph being built: its inline nodes.
        self.inline: list[dict] = []
        self.marks: list[dict] = []
        # A table: rows of cells, each cell a list of block nodes.
        self.table_rows: Optional[list[dict]] = None
        self.table_section: Optional[str] = None
        self.table_cell_blocks: Optional[list[dict]] = None
        self.in_cell_paragraph: Optional[list[dict]] = None
        # Lists: items are paragraphs.
        self.list_tag: Optional[str] = None
        self.list_items: Optional[list[dict]] = None

    def refuse(self, tag: str) -> None:
        """Strict: this page does not convert losslessly. Lenient: the tag is
        ignored and its words survive as text — the draft keeps what the page
        said, not how it said it."""
        if not self.lenient:
            self.lossless = False

    def flush_inline(self) -> None:
        if self.inline:
            self._current_blocks().append({"type": "paragraph", "content": self.inline})
            self.inline = []

    def _current_blocks(self) -> list[dict]:
        if self.table_cell_blocks is not None:
            return self.table_cell_blocks
        if self.list_items is not None:
            return self.list_items
        return self.blocks

    def open_block(self, tag: str, attrs: dict[str, str]) -> None:
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.flush_inline()
            if tag not in ("h1", "h2", "h3") and not self.lenient:
                self.refuse(tag)
                return
            level = min(int(tag[1]), 3)  # lenient: a fourth level is Kleine kop
            self._current_blocks().append(
                {"type": "heading", "attrs": {"level": level}, "content": []}
            )
            self.inline = self._current_blocks()[-1]["content"]
        elif tag == "p":
            self.flush_inline()
            self._current_blocks().append({"type": "paragraph", "content": []})
            self.inline = self._current_blocks()[-1]["content"]
        elif tag in ("ul", "ol"):
            self.flush_inline()
            if self.list_items is not None:
                self.refuse(tag)  # nested lists: the schema has one level
                return
            self.list_tag = tag
            self.list_items = []
        elif tag == "li":
            if self.list_items is None:
                self.refuse(tag)
                return
            self.list_items.append({"type": "paragraph", "content": []})
            self.inline = self.list_items[-1]["content"]
        elif tag == "table":
            self.flush_inline()
            if self.table_rows is not None:
                self.refuse(tag)
                return
            self.table_rows = []
        elif tag in ("figure", "figcaption", "caption"):
            # Transparent: the pre-CR-17 sanitiser drops the wrapper and
            # keeps the <img> (the lift ran before it), so a migrated figure
            # never carries the wrapper — and neither does its rendering.
            pass
        elif tag in ("thead", "tbody", "tfoot"):
            # Transparent: a row remembers which section carried it, so the
            # renderer rebuilds the same <thead>/<tbody> shape (#1671).
            if tag in ("thead", "tbody"):
                self.table_section = "head" if tag == "thead" else "body"
        elif tag == "tr":
            if self.table_rows is None:
                self.refuse(tag)
                return
            row = {"type": "tableRow", "content": []}
            if self.table_section:
                # None means a bare row (a table typed without thead/tbody):
                # no attr at all, so the schema never sees a None enum value.
                row["attrs"] = {"section": self.table_section}
            self.table_rows.append(row)
        elif tag in ("td", "th"):
            if not self.table_rows:
                self.refuse(tag)
                return
            self.table_cell_blocks = []
            self.table_rows[-1]["content"].append(
                {
                    "type": "tableHeader" if tag == "th" else "tableCell",
                    "content": self.table_cell_blocks,
                }
            )
        elif tag == "img":
            figure = self._figure(attrs)
            if figure is None:
                self.refuse("img")
            else:
                self.flush_inline()
                self._current_blocks().append(figure)
        elif tag == "br":
            self.inline.append({"type": "hardBreak"})
        else:
            self.refuse(tag)

    def _figure(self, attrs: dict[str, str]) -> Optional[dict]:
        match = re.search(r"/api/v1/media/(\d+)", attrs.get("src", ""))
        if match is None:
            return None
        classes = (attrs.get("class") or "").split()
        legacy = next((c for c in classes if c.startswith("cms-beeld-")), None)
        size = legacy.removeprefix("cms-beeld-") if legacy else None
        # Only the attributes that exist: an absent attribute is "not set",
        # and None is not a value the schema knows (measured: a None
        # placement was refused on validation).
        figure_attrs: dict = {"media_id": int(match.group(1))}
        if attrs.get("alt"):
            figure_attrs["alt"] = attrs["alt"]
        if size:
            figure_attrs["legacy_size"] = size
        if attrs.get("width", "").isdigit():
            figure_attrs["width"] = int(attrs["width"])
        if attrs.get("height", "").isdigit():
            figure_attrs["height"] = int(attrs["height"])
        return {"type": "figure", "attrs": figure_attrs}

    def close_block(self, tag: str) -> None:
        if tag in ("h1", "h2", "h3", "h4", "p", "li"):
            # No flush here: the inline nodes already ARE this block's
            # content — flushing again appends the same list as a new
            # paragraph, and every paragraph came out twice (measured).
            self.inline = []
        elif tag in ("ul", "ol"):
            if self.list_items is not None and self.list_tag == tag:
                kind = "bulletList" if tag == "ul" else "orderedList"
                items = [{"type": "listItem", "content": [item]} for item in self.list_items]
                # Free the target FIRST: `_current_blocks()` still points at
                # this list while it is open — appending the finished list to
                # itself loses it (measured: a list came out empty).
                self.list_tag = None
                self.list_items = None
                self._current_blocks().append({"type": kind, "content": items})
            self.list_tag = None
            self.list_items = None
        elif tag in ("figure", "figcaption", "caption"):
            # Transparent: the pre-CR-17 sanitiser drops the wrapper and
            # keeps the <img> (the lift ran before it), so a migrated figure
            # never carries the wrapper — and neither does its rendering.
            pass
        elif tag in ("figure", "figcaption", "caption"):
            pass
        elif tag in ("thead", "tbody", "tfoot"):
            if tag in ("thead", "tbody"):
                self.table_section = None
        elif tag == "table":
            if self.table_rows is not None:
                self.blocks.append({"type": "table", "content": self.table_rows})
            self.table_rows = None
        elif tag in ("td", "th"):
            self.flush_inline()
            self.inline = []
            self.table_cell_blocks = None

    def mark(self, tag: str, attrs: dict[str, str]) -> None:
        if tag == "a":
            self.marks.append({"type": "link", "attrs": {"href": attrs.get("href", "")}})
        else:
            self.marks.append({"type": _MARK_FOR[tag]})


class _DocumentParser(HTMLParser):
    """Walks the sanitised HTML and feeds the builder."""

    def __init__(self, builder: _Builder) -> None:
        super().__init__(convert_charrefs=True)
        self.builder = builder

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attrd = {k: v or "" for k, v in attrs}
        if tag in _MARK_FOR or tag == "a":
            self.builder.mark(tag, attrd)
        elif tag in _BLOCK_TAGS:
            self.builder.open_block(tag, attrd)
        else:
            self.builder.refuse(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _MARK_FOR or tag == "a":
            if self.builder.marks:
                self.builder.marks.pop()
        elif tag in _BLOCK_TAGS:
            self.builder.close_block(tag)

    def handle_data(self, data: str) -> None:
        if not (_TEXTUAL.search(data) or data.strip()):
            return
        node: dict[str, Any] = {"type": "text", "text": data}
        if self.builder.marks:
            node["marks"] = [m for m in self.builder.marks]
        self.builder.inline.append(node)
