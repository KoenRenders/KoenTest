"""the platform landing text is the platform's own home-intro

#1525 (CR-19). The landing page of the platform carried its text in the
template, and that text spoke of Raak departments only: since #1523 a company
can be a tenant too, and only a developer could change the words. The platform
has pages since #1523, so its text becomes its own `home-intro` site block —
the same block every tenant's home page renders — which the operator edits
under Pagina's.

Seeded once, with today's text made neutral (the intro and the call to action,
which stood in a box below the list and now stand above it). A platform that
already has a home-intro keeps it: the insert does nothing on conflict.

The text is frozen here, not read from the template or a seed function: a
migration that runs a year from now must write what it wrote today.
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
revision = "192_2026_10_04_055352"
down_revision = "191_2026_10_04_051847"
branch_labels = None
depends_on = None

TITLE = "Home intro"
CONTENT = (
    "<p>Eén platform voor verenigingen en organisaties: elk een eigen site met "
    "pagina's, formulieren en media, en waar nodig activiteiten, inschrijvingen, "
    "ledenbeheer en online betalen.</p>"
    "<h2>Ook op het platform?</h2>"
    "<p>Elke organisatie krijgt een eigen site, met de onderdelen die ze nodig "
    "heeft. Vraag het aan bij de platformbeheerder.</p>"
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO cms.cms_pages
                (tenant_id, title, slug, content, is_published, show_in_nav,
                 is_home, sort_order, created_at, updated_at)
            SELECT id, :title, 'home-intro', :content, true, false, false, 0, now(), now()
            FROM mdm.organizations WHERE org_type = 'PLATFORM'
            ON CONFLICT (tenant_id, slug) DO NOTHING
            """
        ),
        {"title": TITLE, "content": CONTENT},
    )


def downgrade() -> None:
    # Removes the block only while it still holds the seeded text: an operator's
    # edit is data this migration did not write, and a downgrade does not take
    # it. The template that rendered the old text comes back with the code.
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM cms.cms_pages
            WHERE slug = 'home-intro' AND content = :content
              AND tenant_id IN (SELECT id FROM mdm.organizations WHERE org_type = 'PLATFORM')
            """
        ),
        {"content": CONTENT},
    )
