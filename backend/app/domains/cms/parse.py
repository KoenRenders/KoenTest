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
placeholder code stays TEXT in the document — the renderer replaces the codes
as it does today; the value BLOCK is phase 5 (revised assignment, #1671).

No legacy flags (Koen, 6 October 2026: not saddled with legacy): a page
whose paragraphs are Trix ``<div>``s, or whose picture carries a Trix-era
size, does not convert — she keeps her HTML (the visitor sees exactly today's
page, R17), her words stand in the draft for the editor, and the author
places the picture anew. It is a handful of pages, and the migration's log
line names them.

The one safety net, everywhere (the master CLI's advice, #1673): plain text
cannot fail. A page the converter cannot process, and a lenient draft that
holds fewer words than the page, gets the page's words as plain paragraphs —
one per block. Formatting is gone, no word is.

Two whitespace rules the review taught (A2/A3, #1673): whitespace-only text
inside an open paragraph is kept (a lost space between two marks is a change),
and ``normalise_html`` collapses only whitespace runs that contain a newline —
so a lost single space between inline tags turns the comparison red, and
inter-block layout whitespace stays irrelevant.
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
    "div",
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
    "span",
    "h5",
    "h6",
    "figure",
    "figcaption",
    "caption",
}
_TEXTUAL = re.compile(r"\S")
_NEWLINE_BETWEEN_TAGS = re.compile(r">\s*\n\s*<")


def normalise_html(html_text: str) -> str:
    """The one whitespace-insensitive comparison (review B4e, #1673): what
    separates BLOCK tags does not matter when it contains a newline — layout
    whitespace between blocks; a single space between inline tags is CONTENT,
    so it survives and a lost one turns the comparison red (review A3)."""
    return _NEWLINE_BETWEEN_TAGS.sub("><", html_text.strip())


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
    sanitized = sanitize_cms_html(image_attributes_from_attachment(content)) or ""
    # The shift lives in the RENDERER (on_page, #1656): the document stores the
    # author's own level, so the parser feeds the unshifted HTML and the
    # comparison shifts the document's output — never both sides (measured:
    # a double shift turned every heading two levels down).
    today = headings_one_level_down(sanitized) if on_page else sanitized
    builder = _Builder(lenient=lenient)
    _DocumentParser(builder).feed(sanitized)
    builder.finish()
    document: dict[str, Any] = {"type": "doc", "content": builder.blocks}
    if lenient:
        # The net (master CLI's advice, #1673): a draft that holds fewer words
        # than the page falls back to the page's words as plain paragraphs —
        # plain text cannot fail, and no word is lost. Covers the guard case
        # and the two A2 edges (text after a block inside a div).
        if _word_count(document) < _word_count(plain_text_document(sanitized)):
            return plain_text_document(sanitized)
        return document
    if not builder.lossless:
        return None
    rendered = sanitize_cms_html(_blocks_html(builder.blocks)) or ""
    if on_page:
        # The shift, through its one source, after the sanitiser - the same
        # order as the old path (review B4a, #1673).
        rendered = headings_one_level_down(rendered)
    if normalise_html(rendered) != normalise_html(today):
        # The measurement, not the parser's opinion: whatever the builder
        # thought, the round trip decides (test 12 is this line, per page).
        return None
    return document


class _Builder:
    """Collects the document while the parser walks the HTML."""

    def __init__(self, lenient: bool = False) -> None:
        self.lenient = lenient
        self.blocks: list[dict[str, Any]] = []
        self.lossless = True
        # The inline nodes being collected. Inside an open paragraph,
        # heading, list item or cell this IS that block's content list; a
        # paragraph holds its own list, so closing it must not flush.
        self.inline: list[dict[str, Any]] = []
        # True while an inline-carrying block is open: whitespace-only text
        # is content there (a space between two marks), noise between blocks.
        self.in_text_block = False
        self.marks: list[dict[str, Any]] = []
        # A table: rows, and the cell blocks being collected.
        self.table_rows: Optional[list[dict[str, Any]]] = None
        self.table_section: Optional[str] = None
        self.table_cell_blocks: Optional[list[dict[str, Any]]] = None
        # Lists: items are paragraphs.
        self.list_tag: Optional[str] = None
        self.list_items: Optional[list[dict[str, Any]]] = None

    def refuse(self, tag: str) -> None:
        """Strict: this page does not convert losslessly. Lenient: the tag is
        ignored and its words survive as text — the draft keeps what the page
        said, not how it said it."""
        if not self.lenient:
            self.lossless = False

    def finish(self) -> None:
        """After the walk: text that stood after the last closed block (a
        loose tail) still belongs in the document — the lenient draft keeps
        the page's words (review A2, #1673). Without this the tail was lost
        and, for div-only content, the draft came out empty."""
        self.flush_inline()

    def flush_inline(self) -> None:
        if self.inline and self.in_text_block is False:
            self._current_blocks().append({"type": "paragraph", "content": self.inline})
            self.inline = []

    def _current_blocks(self) -> list[dict[str, Any]]:
        if self.table_cell_blocks is not None:
            return self.table_cell_blocks
        if self.list_items is not None:
            return self.list_items
        return self.blocks

    def _open_paragraph(self) -> None:
        self.flush_inline()
        paragraph: dict[str, Any] = {"type": "paragraph", "content": []}
        self._current_blocks().append(paragraph)
        self.inline = paragraph["content"]
        self.in_text_block = True

    def open_block(self, tag: str, attrs: dict[str, str]) -> None:
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.flush_inline()
            if tag not in ("h1", "h2", "h3") and not self.lenient:
                self.refuse(tag)
                return
            level = min(int(tag[1]), 3)  # lenient: a fourth level is Kleine kop
            heading: dict[str, Any] = {
                "type": "heading",
                "attrs": {"level": level},
                "content": [],
            }
            self._current_blocks().append(heading)
            self.inline = heading["content"]
            self.in_text_block = True
        elif tag in ("p", "div"):
            # A div is Trix' paragraph; as a paragraph it renders as a <p>,
            # so a div page does not convert byte-equal and keeps her HTML —
            # her words stand in the draft (no legacy flags, Koen 6 okt).
            self._open_paragraph()
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
            item: dict[str, Any] = {"type": "paragraph", "content": []}
            self.list_items.append(item)
            self.inline = item["content"]
            self.in_text_block = True
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
            row: dict[str, Any] = {"type": "tableRow", "content": []}
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
            cell: dict[str, Any] = {
                "type": "tableHeader" if tag == "th" else "tableCell",
                "content": self.table_cell_blocks,
            }
            self.table_rows[-1]["content"].append(cell)
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

    def _figure(self, attrs: dict[str, str]) -> Optional[dict[str, Any]]:
        match = re.search(r"/api/v1/media/(\d+)", attrs.get("src", ""))
        if match is None:
            return None
        # Only the attributes that exist: an absent attribute is "not set",
        # and None is not a value the schema knows (measured: a None
        # placement was refused on validation). No legacy size: the class
        # stays on the old HTML's image, and this page keeps her HTML.
        figure_attrs: dict[str, Any] = {"media_id": int(match.group(1))}
        if attrs.get("alt"):
            figure_attrs["alt"] = attrs["alt"]
        if attrs.get("width", "").isdigit():
            figure_attrs["width"] = int(attrs["width"])
        if attrs.get("height", "").isdigit():
            figure_attrs["height"] = int(attrs["height"])
        return {"type": "figure", "attrs": figure_attrs}

    def close_block(self, tag: str) -> None:
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "li"):
            # No flush here: the inline nodes already ARE this block's
            # content — flushing again appends the same list as a new
            # paragraph, and every paragraph came out twice (measured).
            self.inline = []
            self.in_text_block = False
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
            # Transparent, on close too (see open_block).
            pass
        elif tag in ("thead", "tbody", "tfoot"):
            if tag in ("thead", "tbody"):
                self.table_section = None
        elif tag == "table":
            if self.table_rows is not None:
                self.blocks.append({"type": "table", "content": self.table_rows})
            self.table_rows = None
        elif tag in ("td", "th"):
            # A cell's loose text becomes its paragraph — the cell's own
            # flush, NOT `flush_inline`: `in_text_block` is False here (the
            # cell itself is no inline block), and without this the text was
            # lost and the table fell back (measured).
            if self.inline and self.table_cell_blocks is not None:
                self.table_cell_blocks.append({"type": "paragraph", "content": self.inline})
            self.inline = []
            self.in_text_block = False
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
        # Whitespace-only text is content INSIDE an open paragraph (a space
        # between two marks, review A3, #1673) and noise between blocks.
        if not _TEXTUAL.search(data):
            if not self.builder.in_text_block:
                return
        node: dict[str, Any] = {"type": "text", "text": data}
        if self.builder.marks:
            node["marks"] = [m for m in self.builder.marks]
        self.builder.inline.append(node)


_PLAIN_TEXT_BLOCK_TAGS = {
    "p",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "td",
    "th",
    "blockquote",
    "pre",
    "figcaption",
    "caption",
    "table",
}


def plain_text_document(content: Optional[str]) -> dict:
    """A page's words as plain paragraphs, one per block (the safety net).

    This cannot fail the way the converter can: it collects text runs and
    starts a new paragraph at every block tag. The migration's per-page guard
    and the lenient draft's word-count net use it — formatting is gone, no
    word is (the master CLI's advice, #1673).
    """
    # Sanitised first, like `parse_html` does: balanced HTML keeps every
    # word in its own block, also when the caller hands the net RAW content
    # (the migration's guard does) and the tags are not closed (review 3,
    # #1673 — `ul` and `ol` were missing from the set on top of that).
    content = sanitize_cms_html(content) or content
    paragraphs: list[dict[str, Any]] = []
    buffer: list[str] = []

    def flush() -> None:
        words = "".join(buffer).strip()
        if words:
            paragraphs.append({"type": "paragraph", "content": [{"type": "text", "text": words}]})
        buffer.clear()

    class _Plain(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list) -> None:
            if tag in _PLAIN_TEXT_BLOCK_TAGS:
                flush()

        def handle_endtag(self, tag: str) -> None:
            if tag in _PLAIN_TEXT_BLOCK_TAGS:
                flush()

        def handle_data(self, data: str) -> None:
            if data.strip():
                buffer.append(data)

    parser = _Plain(convert_charrefs=True)
    parser.feed(content or "")
    parser.close()
    flush()
    return {"type": "doc", "content": paragraphs}


def _word_count(document: Optional[dict]) -> int:
    """How many words a document holds — the net's measure."""
    count = 0

    def walk(node: Any) -> None:
        nonlocal count
        if not isinstance(node, dict):
            return
        if node.get("type") == "text":
            count += len(str(node.get("text", "")).split())
        for child in node.get("content") or []:
            walk(child)

    walk(document or {})
    return count
