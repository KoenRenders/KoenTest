"""Roles per workspace (#963, golf 9b of #913).

Decided by Koen on 15 September 2026 (three answers recorded on #963):

1. **OPERATOR is platform-wide** — a role row with ``tenant_id IS NULL``
   applies in every workspace.
2. **Existing roles migrate to Raak Millegem** (org 2) — except for the
   accounts named in the ``SEED_ALLE_WERKRUIMTES_EMAILS`` environment
   variable (comma-separated, set per host, never committed: public repo),
   whose non-OPERATOR roles are copied to every workspace (orgs 1, 2, 3 —
   the deterministic ids from migration 086).
3. ADMIN of a workspace may grant roles within that workspace (service
   layer; no schema impact here).

Schema: ``auth.user_roles`` had PK ``(user_id, role_code)``. A nullable
``tenant_id`` cannot join a primary key, so the table gets a surrogate ``id``
plus two partial unique indexes — one for workspace rows, one for the
platform-wide (NULL) rows. No FK to ``mdm.organizations`` (§8: no
cross-schema FKs); validity is enforced in the service layer.
"""
import os

import sqlalchemy as sa
from alembic import op

revision = "126"
down_revision = "125"
branch_labels = None
depends_on = None

WORKSPACE_IDS = (1, 2, 3)  # migration 086: Raak, Raak Millegem, Voorbeeldafdeling
MILLEGEM_ID = 2


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table, schema="auth")}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "user_roles", "id"):
        # Surrogate key first: the old composite PK must make way before a
        # NULL-able tenant dimension can exist next to it.
        op.execute(sa.text(
            "ALTER TABLE auth.user_roles DROP CONSTRAINT user_roles_pkey"))
        op.execute(sa.text(
            "ALTER TABLE auth.user_roles ADD COLUMN id SERIAL PRIMARY KEY"))

    if not _has_column(bind, "user_roles", "tenant_id"):
        op.add_column("user_roles",
                      sa.Column("tenant_id", sa.Integer, nullable=True),
                      schema="auth")

    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_roles_workspace "
        "ON auth.user_roles (user_id, role_code, tenant_id) "
        "WHERE tenant_id IS NOT NULL"))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_roles_platform "
        "ON auth.user_roles (user_id, role_code) "
        "WHERE tenant_id IS NULL"))

    # Data: everything becomes Millegem-scoped, except OPERATOR (platform-wide
    # by decision 1). Idempotent: only rows still without tenant move.
    op.execute(sa.text(
        "UPDATE auth.user_roles SET tenant_id = :t "
        "WHERE tenant_id IS NULL AND role_code != 'OPERATOR'"
    ).bindparams(t=MILLEGEM_ID))

    # Decision 2's exception: the named accounts keep their roles in every
    # workspace. Copy, don't move — Millegem stays from the update above.
    emails = [e.strip().lower() for e in
              os.environ.get("SEED_ALLE_WERKRUIMTES_EMAILS", "").split(",")
              if e.strip()]
    for email in emails:
        for org_id in WORKSPACE_IDS:
            if org_id == MILLEGEM_ID:
                continue
            op.execute(sa.text(
                "INSERT INTO auth.user_roles (user_id, role_code, tenant_id) "
                "SELECT ur.user_id, ur.role_code, :org "
                "FROM auth.user_roles ur JOIN auth.users u ON u.id = ur.user_id "
                "WHERE lower(u.email) = :email AND ur.role_code != 'OPERATOR' "
                "AND ur.tenant_id = :mill "
                "AND NOT EXISTS (SELECT 1 FROM auth.user_roles d "
                "  WHERE d.user_id = ur.user_id AND d.role_code = ur.role_code "
                "  AND d.tenant_id = :org)"
            ).bindparams(org=org_id, email=email, mill=MILLEGEM_ID))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS auth.uq_user_roles_workspace"))
    op.execute(sa.text("DROP INDEX IF EXISTS auth.uq_user_roles_platform"))
    # Collapse back to one row per (user, role); the composite PK returns.
    op.execute(sa.text(
        "DELETE FROM auth.user_roles a USING auth.user_roles b "
        "WHERE a.user_id = b.user_id AND a.role_code = b.role_code "
        "AND a.id > b.id"))
    op.drop_column("user_roles", "tenant_id", schema="auth")
    op.execute(sa.text("ALTER TABLE auth.user_roles DROP CONSTRAINT user_roles_pkey"))
    op.drop_column("user_roles", "id", schema="auth")
    op.execute(sa.text(
        "ALTER TABLE auth.user_roles ADD PRIMARY KEY (user_id, role_code)"))
