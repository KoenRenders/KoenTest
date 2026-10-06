"""CR-17 spike (#1626) — the proef-renderer: TipTap JSON document to HTML.

The spike's server-side half. Phase 1 puts this shape in `cms/render.py`
(docs/change_request_17_web_content.md, C2 cms); here it proves the JSON
TipTap emits renders server-side without any browser, and that a round trip
changes only what was edited.

Supported here: doc, paragraph, heading, text (bold/italic/strike/link),
table/tableRow/tableHeader/tableCell, and the custom `value` node.
"""

import html
import json

VALUES = {"LIDGELD": "€ 35,00"}

BLOCK_TAGS = {
    "paragraph": "p",
    "tableHeader": "th",
    "tableCell": "td",
    "tableRow": "tr",
}

MARK_TAGS = {
    "bold": "strong",
    "italic": "em",
    "strike": "s",
}


def _render_marks(node):
    if node.get("type") != "text":
        raise ValueError(f"marks on a non-text node: {node}")
    text = html.escape(node.get("text", ""))
    for mark in node.get("marks", []):
        mark_type = mark.get("type")
        if mark_type == "link":
            href = html.escape(mark.get("attrs", {}).get("href", ""), quote=True)
            text = f'<a href="{href}">{text}</a>'
        elif mark_type in MARK_TAGS:
            tag = MARK_TAGS[mark_type]
            text = f"<{tag}>{text}</{tag}>"
        else:
            raise ValueError(f"unknown mark: {mark_type}")
    return text


def _render_inline(children):
    parts = []
    for node in children or []:
        node_type = node.get("type")
        if node_type == "text":
            parts.append(_render_marks(node))
        elif node_type == "value":
            code = node.get("attrs", {}).get("code", "")
            value = html.escape(VALUES.get(code, code))
            parts.append(f'<span data-value="{html.escape(code)}">{value}</span>')
        else:
            raise ValueError(f"unknown inline node: {node_type}")
    return "".join(parts)


def render_node(node, in_cell=False):
    node_type = node.get("type")

    if node_type == "doc":
        return "".join(render_node(child) for child in node.get("content", []))

    if node_type == "heading":
        level = node.get("attrs", {}).get("level", 2)
        tag = f"h{level}"
        return f"<{tag}>{_render_inline(node.get('content'))}</{tag}>"

    if node_type == "paragraph":
        # A paragraph inside a table cell renders inline: no <p> inside <td>.
        if in_cell:
            return _render_inline(node.get("content"))
        return f"<p>{_render_inline(node.get('content'))}</p>"

    if node_type == "table":
        rows = "".join(render_node(child) for child in node.get("content", []))
        return f"<table><tbody>{rows}</tbody></table>"

    # A row's children are cells; a cell's children are block nodes (paragraphs).
    if node_type in ("tableRow", "tableHeader", "tableCell"):
        tag = BLOCK_TAGS[node_type]
        inner = "".join(
            render_node(child, in_cell=node_type in ("tableHeader", "tableCell"))
            for child in node.get("content", [])
        )
        return f"<{tag}>{inner}</{tag}>"

    raise ValueError(f"unknown block node: {node_type}")


def render_document(document):
    """A TipTap JSON document (dict or JSON string) to site HTML."""
    if isinstance(document, str):
        document = json.loads(document)
    return render_node(document)


if __name__ == "__main__":
    import sys

    print(render_document(open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()))
