"""pages store the heading levels they show (CR-32 R21, F19)

A page stored the level its author chose in the editor (1–3: Kop, Subkop,
Kleine kop) and the renderer showed every heading one level down, because the
page's title is the only h1 (#1656). Koen, 15 October 2026: "Akkoord om de
pagina te laten opslaan wat ze renderen" — the document now stores h2–h4, the
levels it shows, and the renderer shifts nothing.

This rewrites every stored document once, h1→h2, h2→h3, h3→h4: the published
and the draft document of every translation, and every row of the history (a
restore must bring back a document that shows what it showed). The site's own
blocks (the home intro, the footer) are documents too and shift with the rest:
they stored h1–h3 and were shown unshifted; from now on they show h2–h4 like
every page, which stands right once the home is a page with its own title.

Not idempotent by nature (a second run would shift again); alembic runs a
revision once. The downgrade shifts back.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# `repr` with double quotes (#781): a generated file must already be what
# `ruff format` writes.
revision = "204_2026_10_15_080810"
down_revision = "200_2026_10_06_195129"
branch_labels = None
depends_on = None


def shift_headings(node, step: int):
    """The document with every heading's level moved by `step`, and whether
    anything moved. A heading outside the range the move arrives in is left
    alone (it cannot occur in a stored document; the guard keeps a repair from
    producing h0 or h5)."""
    changed = False
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            new, moved = shift_headings(value, step)
            out[key] = new
            changed = changed or moved
        if node.get("type") == "heading" and isinstance(node.get("attrs"), dict):
            level = node["attrs"].get("level")
            if isinstance(level, int) and 1 <= level + step <= 4 and level in (1, 2, 3, 4):
                out["attrs"] = {**node["attrs"], "level": level + step}
                changed = True
        return out, changed
    if isinstance(node, list):
        out_list = []
        for item in node:
            new, moved = shift_headings(item, step)
            out_list.append(new)
            changed = changed or moved
        return out_list, changed
    return node, False


def _rewrite(step: int) -> None:
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
                shifted, changed = shift_headings(document, step)
                if not changed:
                    continue
                where = " AND ".join(f"{key} = :{key}" for key in keys)
                bind.execute(
                    sa.text(f"UPDATE cms.{table} SET {column} = :doc WHERE {where}").bindparams(
                        sa.bindparam("doc", type_=JSONB)
                    ),
                    {"doc": shifted, **{key: values[key] for key in keys}},
                )


def upgrade() -> None:
    _rewrite(+1)


def downgrade() -> None:
    _rewrite(-1)
