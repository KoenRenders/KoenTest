"""cms_pages.show_in_nav — pagina's expliciet uit de navigatie houden (#152)

Vervangt de hardcoded slug-uitzonderingen in de frontend-navigatie door een
boolean per pagina. Bestaande pagina's blijven standaard zichtbaar (true); de
blok-/juridische pagina's 'home-intro' en 'privacy' worden op false gezet.

Idempotent: controleert of de kolom al bestaat voor hij hem toevoegt.

Revision ID: 049
Revises: 048
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def _has_column(conn, table, column) -> bool:
    return conn.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name=:c)"
    ), {"t": table, "c": column}).scalar()


def upgrade():
    conn = op.get_bind()
    if not _has_column(conn, "cms_pages", "show_in_nav"):
        # server_default=true vult de bestaande rijen; daarna weghalen zodat de
        # default in de app-laag ligt (model default=True), conform de conventie.
        op.add_column(
            "cms_pages",
            sa.Column("show_in_nav", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        op.alter_column("cms_pages", "show_in_nav", server_default=None)
    # Blok-/juridische pagina's nooit in de hoofdnavigatie.
    conn.execute(text(
        "UPDATE cms_pages SET show_in_nav = false WHERE slug IN ('home-intro', 'privacy')"
    ))


def downgrade():
    conn = op.get_bind()
    if _has_column(conn, "cms_pages", "show_in_nav"):
        op.drop_column("cms_pages", "show_in_nav")
