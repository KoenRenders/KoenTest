"""the value codes typed in a document become value nodes (CR-32 R19, F17)

A code like `{{membership_price_full}}` stood as plain text in a document and the
renderer replaced it. The editor's Code item inserts a value node now (a chip
with the value it has now), so every stored document — draft, published and the
history of both — gets its typed codes of the closed list rewritten to that
node. What is not turned into a node stays text, and is counted in the log:
a code with a part of its own (`{{tenants:raak}}`), a form button
(`{{form:…}}`), whatever else an author typed, **a code in words that carry a
link** (a value has no marks, so the link would go: such a code is left alone
and still renders through the typed path, review of PR #2018) and a code split
over two text nodes by a mark (it matches inside neither node). Bold and
italic on the words a code stood in are not carried to the node: a value has
none — cosmetic, and counted apart.

The rewrite is one way in practice; the downgrade writes the codes back as
text.
"""

import logging
import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "206_2026_10_15_101648"
down_revision = "205_2026_10_15_082601"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

#: The closed list as it stood when this ran (`cms.schema.VALUE_CODES`): a
#: migration does not read the live list, which may grow.
CODES = (
    "membership_price_full",
    "membership_price_half",
    "half_price_start",
    "half_price_end",
    "next_year_from",
    "membership_valid_until",
    "tenants",
)
_TYPED = re.compile(r"\{\{(" + "|".join(CODES) + r")\}\}")
_ANY = re.compile(r"\{\{[^{}]+\}\}")


def codes_to_nodes(node, stats: dict):
    """The node with every typed code of the list turned into a value node:
    inline content is rebuilt text node by text node, around each code."""
    if isinstance(node, list):
        out: list = []
        run: list[str] = []  # the text of the consecutive text nodes of this inline run
        for child in node:
            if isinstance(child, dict) and child.get("type") == "text":
                run.append(child.get("text") or "")
                out.extend(_split(child, stats))
            else:
                _count_split(run, stats)
                run = []
                out.append(codes_to_nodes(child, stats))
        _count_split(run, stats)
        return out
    if isinstance(node, dict):
        return {key: codes_to_nodes(value, stats) for key, value in node.items()}
    return node


def _count_split(run: list[str], stats: dict) -> None:
    """A code split over two text nodes (a mark in the middle of it) matches in
    neither; it stays text, and is counted here: what the joined run holds
    beyond what each node holds on its own."""
    if len(run) > 1:
        stats["left"] += max(
            len(_ANY.findall("".join(run))) - sum(len(_ANY.findall(text)) for text in run), 0
        )


def _has_link(text_node: dict) -> bool:
    return any(
        isinstance(mark, dict) and mark.get("type") == "link"
        for mark in text_node.get("marks") or []
    )


def _split(text_node: dict, stats: dict) -> list:
    text = text_node.get("text") or ""
    if _has_link(text_node):
        # A link is a function, not decoration: the words stay as they are and
        # every `{{…}}` in them stays text (the typed path still renders it).
        stats["left"] += len(_ANY.findall(text))
        return [text_node]
    pieces = _TYPED.split(text)
    if len(pieces) == 1:
        stats["left"] += len(_ANY.findall(text))
        return [text_node]
    out: list = []
    for index, piece in enumerate(pieces):
        if index % 2 == 0:
            if piece:
                out.append({**text_node, "text": piece})
                stats["left"] += len(_ANY.findall(piece))
        else:
            out.append({"type": "value", "attrs": {"code": piece}})
            stats["made"] += 1
            if text_node.get("marks"):
                stats["unmarked"] += 1  # bold, italic: the node has none
    return out


def nodes_to_codes(node):
    """The reverse: a value node written back as the text it replaced."""
    if isinstance(node, list):
        out: list = []
        for child in node:
            if isinstance(child, dict) and child.get("type") == "value":
                out.append(
                    {"type": "text", "text": "{{" + child.get("attrs", {}).get("code", "") + "}}"}
                )
            else:
                out.append(nodes_to_codes(child))
        return out
    if isinstance(node, dict):
        return {key: nodes_to_codes(value) for key, value in node.items()}
    return node


def _rewrite(convert) -> None:
    bind = op.get_bind()
    targets = (
        ("page_translations", ("draft_json", "published_json"), ("page_id", "language")),
        ("cms_page_history", ("document",), ("id",)),
    )
    for table, columns, keys in targets:
        rows = bind.execute(
            sa.text(f"SELECT {', '.join(keys + columns)} FROM cms.{table}")
        ).fetchall()
        for row in rows:
            values = dict(zip(keys + columns, row))
            for column in columns:
                document = values[column]
                if document is None:
                    continue
                converted = convert(document)
                if converted == document:
                    continue
                where = " AND ".join(f"{key} = :{key}" for key in keys)
                bind.execute(
                    sa.text(f"UPDATE cms.{table} SET {column} = :doc WHERE {where}").bindparams(
                        sa.bindparam("doc", type_=JSONB)
                    ),
                    {"doc": converted, **{key: values[key] for key in keys}},
                )


def upgrade() -> None:
    stats = {"made": 0, "left": 0, "unmarked": 0}
    _rewrite(lambda document: codes_to_nodes(document, stats))
    log.info(
        "CR-32 R19: %(made)s typed codes became value nodes (%(unmarked)s lost a bold or "
        "italic mark); %(left)s {{…}} stay text (counted per text node: a code with a part of "
        "its own, a form button, a code in a link, a code split by a mark)",
        stats,
    )


def downgrade() -> None:
    _rewrite(nodes_to_codes)
