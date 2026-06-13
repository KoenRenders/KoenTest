"""Ontkoppel User van Person en LoginToken van User

De auth-unificatie maximaliseert de domeinscheiding: een User is louter een
backoffice-account (rollen via user_roles), lid-zijn wordt afgeleid uit
ContactDetail. De brug tussen beide domeinen is de e-mailwaarde, geen FK.
Daarom verdwijnen:
  - users.person_id        (FK naar persons)
  - login_tokens.user_id   (FK naar users)

Revision ID: 037
Revises: 036
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def _drop_column_with_fks(table: str, column: str) -> None:
    """Idempotent: drop FK's en index op de kolom, dan de kolom zelf."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = [c["name"] for c in insp.get_columns(table)]
    if column not in columns:
        return
    for fk in insp.get_foreign_keys(table):
        if column in fk.get("constrained_columns", []) and fk.get("name"):
            op.drop_constraint(fk["name"], table, type_="foreignkey")
    for ix in insp.get_indexes(table):
        if ix.get("column_names") == [column] and ix.get("name"):
            op.drop_index(ix["name"], table_name=table)
    op.drop_column(table, column)


def upgrade() -> None:
    _drop_column_with_fks("users", "person_id")
    _drop_column_with_fks("login_tokens", "user_id")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "person_id" not in [c["name"] for c in insp.get_columns("users")]:
        op.add_column("users", sa.Column("person_id", sa.Integer(), nullable=True))
        op.create_foreign_key("fk_users_person_id", "users", "persons", ["person_id"], ["id"])

    if "user_id" not in [c["name"] for c in insp.get_columns("login_tokens")]:
        op.add_column("login_tokens", sa.Column("user_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_login_tokens_user_id", "login_tokens", "users",
            ["user_id"], ["id"], ondelete="CASCADE",
        )
