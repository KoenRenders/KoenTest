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

Added on 16 September 2026: **ACCOUNT_ADMIN belongs to Raak vzw and the
platform** ("account_admin hoort bij Raak vzw en platform" — Koen), so it is
excluded from both the Millegem move and the seed copy, and placed on the
ACCOUNT organization (org 1) plus the PLATFORM organization instead. The
platform id is looked up by ``org_type = 'PLATFORM'``, never hardcoded —
migration 097 explains why its id is not deterministic.

The data steps live in module-level functions on a plain bind so the test
(``test_rollen_per_werkruimte.py``) exercises exactly the SQL that runs on a
host — not a re-implementation of it.

Schema: ``auth.user_roles`` had PK ``(user_id, role_code)``. A nullable
``tenant_id`` cannot join a primary key, so the table gets a surrogate ``id``
plus two partial unique indexes — one for workspace rows, one for the
platform-wide (NULL) rows. No FK to ``mdm.organizations`` (§8: no
cross-schema FKs); validity is enforced in the service layer.
"""
import os

import sqlalchemy as sa
from alembic import op

revision = "127"
down_revision = "126"
branch_labels = None
depends_on = None

WORKSPACE_IDS = (1, 2, 3)  # migration 086: Raak, Raak Millegem, Voorbeeldafdeling
MILLEGEM_ID = 2
ACCOUNT_ID = 1  # migration 086: the ACCOUNT organization (Raak vzw)


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table, schema="auth")}


def _platform_org_id(bind):
    """The PLATFORM organization's id, by type — see migration 097 on why the
    number is not deterministic across hosts."""
    return bind.execute(sa.text(
        "SELECT id FROM mdm.organizations WHERE org_type = 'PLATFORM'")).scalar()


def scope_existing_roles(bind) -> None:
    """Give every pre-#963 role row (``tenant_id IS NULL``) its workspace.

    Order matters: ACCOUNT_ADMIN is placed first (Raak vzw + platform, Koen
    16 Sep), so the general Millegem move below can never claim it.
    """
    bind.execute(sa.text(
        "UPDATE auth.user_roles SET tenant_id = :acc "
        "WHERE tenant_id IS NULL AND role_code = 'ACCOUNT_ADMIN'"
    ).bindparams(acc=ACCOUNT_ID))
    platform_id = _platform_org_id(bind)
    if platform_id:
        bind.execute(sa.text(
            "INSERT INTO auth.user_roles (user_id, role_code, tenant_id, created_at) "
            "SELECT ur.user_id, 'ACCOUNT_ADMIN', :plat, now() "
            "FROM auth.user_roles ur "
            "WHERE ur.role_code = 'ACCOUNT_ADMIN' AND ur.tenant_id = :acc "
            "AND NOT EXISTS (SELECT 1 FROM auth.user_roles d "
            "  WHERE d.user_id = ur.user_id AND d.role_code = 'ACCOUNT_ADMIN' "
            "  AND d.tenant_id = :plat)"
        ).bindparams(plat=platform_id, acc=ACCOUNT_ID))
    # Everything else becomes Millegem-scoped, except OPERATOR (platform-wide
    # by decision 1). Idempotent: only rows still without tenant move.
    bind.execute(sa.text(
        "UPDATE auth.user_roles SET tenant_id = :t "
        "WHERE tenant_id IS NULL "
        "AND role_code NOT IN ('OPERATOR', 'ACCOUNT_ADMIN')"
    ).bindparams(t=MILLEGEM_ID))


def copy_seed_roles(bind, emails) -> None:
    """Decision 2's exception: the named accounts keep their roles in every
    workspace. Copy, don't move — Millegem stays from the move above.

    ACCOUNT_ADMIN is excluded here too. After ``scope_existing_roles`` it has
    no Millegem source row, so today this exclusion is belt-and-braces — but a
    future reordering of the two steps must not hand the Voorbeeldafdeling an
    ACCOUNT_ADMIN silently.
    """
    for email in emails:
        for org_id in WORKSPACE_IDS:
            if org_id == MILLEGEM_ID:
                continue
            bind.execute(sa.text(
                "INSERT INTO auth.user_roles (user_id, role_code, tenant_id, created_at) "
                "SELECT ur.user_id, ur.role_code, :org, now() "
                "FROM auth.user_roles ur JOIN auth.users u ON u.id = ur.user_id "
                "WHERE lower(u.email) = :email "
                "AND ur.role_code NOT IN ('OPERATOR', 'ACCOUNT_ADMIN') "
                "AND ur.tenant_id = :mill "
                "AND NOT EXISTS (SELECT 1 FROM auth.user_roles d "
                "  WHERE d.user_id = ur.user_id AND d.role_code = ur.role_code "
                "  AND d.tenant_id = :org)"
            ).bindparams(org=org_id, email=email, mill=MILLEGEM_ID))


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

    scope_existing_roles(bind)
    emails = [e.strip().lower() for e in
              os.environ.get("SEED_ALLE_WERKRUIMTES_EMAILS", "").split(",")
              if e.strip()]
    copy_seed_roles(bind, emails)


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
