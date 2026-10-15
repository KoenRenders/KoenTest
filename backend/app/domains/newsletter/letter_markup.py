"""A letter's text with markers — the form Raakje reads and writes — and the
document it is stored as (CR-17 phase 7, #2023; Koen, 15 October 2026: "Raakje
keeps writing the markers; the app turns them into blocks at the save").

The letter is stored as a document of the page editor's `letter` set. Raakje (the
drafting assistant) and the letters written before the editor moved speak HTML
with three markers, each on a line of its own:

- ``[[activiteit:12|Naam]]`` — one activity (the name after the bar is for the eye);
- ``[[kalender]]`` — the calendar of the letter's own choices;
- ``[[afsluiting]]`` — the closing every letter ends with.

`markup_to_document` turns such text into a document, `document_to_markup` turns a
document back into it. Nothing here touches a database: the blocks the mail shows
are built from the data by `service.py` when the letter is rendered.
"""

from __future__ import annotations

import re
from typing import Any

#: The three markers. Anything but a closing bracket may stand behind the bar of an
#: activity: nothing reads it.
MARKER = re.compile(r"\[\[(?:activiteit:(\d+)(?:\|[^\]]*)?|(kalender)|(afsluiting))\]\]")


#: The marker of an activity, without its name.
def activity_marker(activity_id: int, name: str = "") -> str:
    return f"[[activiteit:{activity_id}|{name}]]" if name else f"[[activiteit:{activity_id}]]"


CALENDAR_MARKER = "[[kalender]]"
CLOSING_MARKER = "[[afsluiting]]"


def _block_of(match: "re.Match[str]") -> dict[str, Any]:
    if match.group(1):
        return {"type": "activity", "attrs": {"activity_id": int(match.group(1))}}
    return {"type": "calendar" if match.group(2) else "closing"}


def _paragraph(inline: list[dict[str, Any]]) -> "dict[str, Any] | None":
    """A paragraph of what stands left of a marker — none when only blanks do."""
    has_words = any(n["type"] == "text" and n["text"].strip() for n in inline)
    return {"type": "paragraph", "content": inline} if has_words else None


def _text_of(paragraph: dict[str, Any]) -> str:
    return "".join(n.get("text", "") for n in paragraph.get("content") or [] if n["type"] == "text")


def _has_words(paragraph: dict[str, Any]) -> bool:
    return bool(_text_of(paragraph).strip())


def _split(paragraph: dict[str, Any]) -> list[dict[str, Any]]:
    """One paragraph, cut at every marker in its text: the text before it, the
    block, the text after it."""
    if not any(
        n["type"] == "text" and MARKER.search(n["text"]) for n in paragraph.get("content") or []
    ):
        return [paragraph]
    out: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []

    def flush() -> None:
        piece = _paragraph(current)
        if piece:
            out.append(piece)
        current.clear()

    for node in paragraph.get("content") or []:
        if node["type"] != "text" or not MARKER.search(node["text"]):
            current.append(node)
            continue
        text, at = node["text"], 0
        for match in MARKER.finditer(text):
            before = text[at : match.start()]
            if before:
                current.append({**node, "text": before})
            flush()
            out.append(_block_of(match))
            at = match.end()
        if text[at:]:
            current.append({**node, "text": text[at:]})
    flush()
    return out


def markup_to_document(markup: "str | None") -> dict[str, Any]:
    """The letter's text (HTML with markers) as a document: lenient like the page
    editor's migration — formatting may soften, no word is lost — with the markers
    become blocks. Always a document the schema accepts."""
    from app.domains.cms.api import document_from_html

    document = document_from_html(markup or "")
    blocks: list[dict[str, Any]] = []
    for node in document.get("content") or []:
        if node["type"] != "paragraph":
            blocks.append(node)
        elif _has_words(node) or MARKER.search(_text_of(node)):
            blocks.extend(_split(node))
        # else: a blank line (`<div><br></div>`) — spacing, which the mail gives
        # between its paragraphs itself; a document holds no empty paragraph.
    return {"type": "doc", "content": blocks}


def document_to_markup(
    document: "dict[str, Any] | None", names: "dict[int, str] | None" = None
) -> str:
    """The letter as the text Raakje reads: the document as HTML, each of the three
    blocks as its marker in a `div` of its own. `names` gives an activity its name
    behind the bar."""
    from app.domains.cms.api import render_document

    names = names or {}

    def marked(marker: str) -> str:
        return f"<div>{marker}</div>"

    blocks = {
        "activity": lambda node: marked(
            activity_marker(
                node["attrs"]["activity_id"], names.get(node["attrs"]["activity_id"], "")
            )
        ),
        "calendar": lambda node: marked(CALENDAR_MARKER),
        "closing": lambda node: marked(CLOSING_MARKER),
    }
    return render_document(document or {"type": "doc", "content": []}, blocks=blocks)
