"""FK RESTRICT op registration_items.product_id

Beschermt financiële geschiedenis: een product kan niet worden verwijderd
zolang er registratie-items aan gekoppeld zijn.

Revision ID: 038
Revises: 037
Create Date: 2026-06-14
"""
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def _fk_exists(conn, table, name):
    insp = Inspector.from_engine(conn)
    return any(fk["name"] == name for fk in insp.get_foreign_keys(table))


def upgrade():
    conn = op.get_bind()

    # Verwijder de bestaande FK (naam kan variëren per PostgreSQL-versie/migratie).
    # We zoeken de huidige FK op naam en droppen die, dan voegen we een nieuwe toe
    # met ON DELETE RESTRICT.
    insp = Inspector.from_engine(conn)
    existing_fks = insp.get_foreign_keys("registration_items")
    for fk in existing_fks:
        if fk.get("referred_table") == "activity_products" and "product_id" in fk.get("constrained_columns", []):
            if fk.get("name"):
                op.drop_constraint(fk["name"], "registration_items", type_="foreignkey")
            break

    op.create_foreign_key(
        "fk_registration_items_product_restrict",
        "registration_items",
        "activity_products",
        ["product_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint("fk_registration_items_product_restrict", "registration_items", type_="foreignkey")
    op.create_foreign_key(
        None,
        "registration_items",
        "activity_products",
        ["product_id"],
        ["id"],
    )
