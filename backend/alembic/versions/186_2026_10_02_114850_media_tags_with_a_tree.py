"""Media gets tags, shown as a tree (CR-15 phase 1, #1470).

The library's own material — page pictures, the association's logo, sponsor
images — has no natural place, and with hundreds of pictures a flat list cannot
be searched by eye. Koen chose tags over folders (2 October 2026, CR-15 §C4.2):
a picture carries several tags, and the tags are shown as a tree, each with an
optional parent.

Two additive tables, no column on `media_assets`:

* `media.tags (id, parent_id → media.tags ON DELETE RESTRICT, name, tenant_id)`.
  The key is `UNIQUE NULLS NOT DISTINCT (tenant_id, parent_id, name)`. The CR
  writes plain `UNIQUE`, and in Postgres that lets two top-level tags of the same
  name in: two NULL parents count as different. `NULLS NOT DISTINCT` (Postgres
  15+) is what the CR means.
* `media.asset_tags (asset_id → media_assets ON DELETE CASCADE, tag_id →
  media.tags ON DELETE RESTRICT, PRIMARY KEY (asset_id, tag_id))`. The same tag
  twice on one picture is refused by the key; a tag in use cannot be deleted.
  No `tenant_id`: a row belongs to its asset and its tag, both of which carry one.

**The starting tags** (Koen, 2 October 2026): one per kind already present among
the library's own material — "Logo's" for `tenant_logo`, "Sponsors" for
`sponsor`, "Pagina's" for `page_image` — per tenant that has rows of that kind,
each linked to those rows. Nothing for activities: their photos are a branch
derived from the activity, not tags. Finer tags the board makes itself.

Idempotent: the tables are created when missing, the tags and links only where
they are not there yet. The downgrade drops both tables, links and starting tags
with them; no picture is touched either way.
"""

import sqlalchemy as sa
from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
# `repr` with double quotes (#781): the generated file must already be what
# `ruff format` writes, or every new migration turns CI red. A `repr` still, not
# a bare string, because `down_revision` is a tuple for a merge and None for the
# first migration.
revision = "186_2026_10_02_114850"
down_revision = "185_2026_10_02_082804"
branch_labels = None
depends_on = None

SCHEMA = "media"

#: The starting tags: the kind they gather, and their name (Koen, 2 October 2026).
STARTING_TAGS = (
    ("tenant_logo", "Logo's"),
    ("sponsor", "Sponsors"),
    ("page_image", "Pagina's"),
)


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name, schema=SCHEMA)


def seed_starting_tags(bind) -> None:
    """The starting tags and their links — a function of its own so a test can run
    it on rows it made (`test_media_tags.py`). Idempotent."""
    for kind, name in STARTING_TAGS:
        bind.execute(
            sa.text(
                f"INSERT INTO {SCHEMA}.tags (parent_id, name, tenant_id) "
                f"SELECT DISTINCT NULL::int, :name, a.tenant_id FROM {SCHEMA}.media_assets a "
                "WHERE a.kind = :kind "
                "ON CONFLICT ON CONSTRAINT uq_tags_tenant_parent_name DO NOTHING"
            ),
            {"kind": kind, "name": name},
        )
        bind.execute(
            sa.text(
                f"INSERT INTO {SCHEMA}.asset_tags (asset_id, tag_id) "
                f"SELECT a.id, t.id FROM {SCHEMA}.media_assets a "
                f"JOIN {SCHEMA}.tags t ON t.tenant_id = a.tenant_id "
                "  AND t.parent_id IS NULL AND t.name = :name "
                "WHERE a.kind = :kind "
                "ON CONFLICT DO NOTHING"
            ),
            {"kind": kind, "name": name},
        )


def upgrade() -> None:
    if not _has_table("tags"):
        op.create_table(
            "tags",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "parent_id",
                sa.Integer,
                sa.ForeignKey(f"{SCHEMA}.tags.id", ondelete="RESTRICT"),
                nullable=True,
            ),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            schema=SCHEMA,
        )
        op.execute(
            f"ALTER TABLE {SCHEMA}.tags ADD CONSTRAINT uq_tags_tenant_parent_name "
            "UNIQUE NULLS NOT DISTINCT (tenant_id, parent_id, name)"
        )
        op.create_index("ix_tags_parent_id", "tags", ["parent_id"], schema=SCHEMA)
    if not _has_table("asset_tags"):
        op.create_table(
            "asset_tags",
            sa.Column(
                "asset_id",
                sa.Integer,
                sa.ForeignKey(f"{SCHEMA}.media_assets.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "tag_id",
                sa.Integer,
                sa.ForeignKey(f"{SCHEMA}.tags.id", ondelete="RESTRICT"),
                primary_key=True,
            ),
            schema=SCHEMA,
        )
        op.create_index("ix_asset_tags_tag_id", "asset_tags", ["tag_id"], schema=SCHEMA)

    seed_starting_tags(op.get_bind())


def downgrade() -> None:
    """Both tables go, and the starting tags and every link with them. No picture
    is touched: `media_assets` gets no column and loses none."""
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.asset_tags")
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.tags")
