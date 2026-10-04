"""contact form and message workflow per tenant

Why (#1509): every tenant is to have its own contact form (`form.forms` with
slug "berichten") and its own workflow definition "bericht". Two keys made that
impossible, both older than the tenancy:

- `ix_forms_slug_uniek` (091) is unique on `slug` over ALL tenants, so a second
  tenant could not have a form "berichten";
- `workflow.workflow_definitions` has `code` as its whole primary key (082), so
  a second tenant could not have a definition "bericht", and the foreign key of
  `workflow_instances` (165) points at that single column.

Both become per tenant: the index on (tenant_id, slug), the primary key on
(tenant_id, code), and the instances' foreign key on (tenant_id, definition_code).
The rows themselves are added by the startup seed (`seed_contact_forms.py`),
through the app's services — not here, so this file never imports service code
that may change after it.

The previous release keeps working on this schema: it looks a form up by slug
under the tenant filter, and a definition by code under the tenant filter, and
a new instance carries its tenant from the mixin.

Before a key changes, the rows it would refuse are counted, and the migration
stops naming them instead of failing on the constraint (as 165 does). Measured
read-only on PROD, UAT and HDEV before the build: none.
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
revision = "190_2026_10_03_000631"
down_revision = "189_2026_10_02_142946"
branch_labels = None
depends_on = None

OLD_SLUG_INDEX = "ix_forms_slug_uniek"
SLUG_INDEX = "uq_forms_tenant_slug"
OLD_DEFINITION_FK = "fk_workflow_instances_definition_code"
DEFINITION_FK = "fk_workflow_instances_tenant_definition"
DEFINITION_PK = "pk_workflow_definitions"

# What each new key would refuse, counted first. A count that is not zero stops
# the migration with the rows named.
CHECKS = (
    (
        "workflow.workflow_definitions rows without a tenant (a primary key column cannot be NULL)",
        "SELECT code AS value, count(*) AS n FROM workflow.workflow_definitions "
        "WHERE tenant_id IS NULL GROUP BY code",
    ),
    (
        "workflow.workflow_instances rows without a tenant",
        "SELECT definition_code AS value, count(*) AS n FROM workflow.workflow_instances "
        "WHERE tenant_id IS NULL GROUP BY definition_code",
    ),
    (
        "workflow.workflow_instances under another tenant than their definition (the "
        "new foreign key would refuse them)",
        "SELECT i.definition_code || ' (instance tenant ' || i.tenant_id || ', definition "
        "tenant ' || d.tenant_id || ')' AS value, count(*) AS n "
        "FROM workflow.workflow_instances i "
        "JOIN workflow.workflow_definitions d ON d.code = i.definition_code "
        "WHERE i.tenant_id IS DISTINCT FROM d.tenant_id "
        "GROUP BY i.definition_code, i.tenant_id, d.tenant_id",
    ),
    (
        "form.forms with the same slug twice in one tenant",
        "SELECT tenant_id || '/' || slug AS value, count(*) AS n FROM form.forms "
        "WHERE slug IS NOT NULL GROUP BY tenant_id, slug HAVING count(*) > 1",
    ),
)


def _refuse_what_the_keys_would_refuse(bind) -> None:
    for what, query in CHECKS:
        rows = bind.execute(sa.text(query)).all()
        if rows:
            found = ", ".join(f"{row.value!r}x{row.n}" for row in rows)
            raise RuntimeError(f"{what}: {found}. Repair these rows first; nothing changed.")


def _pk_name(bind) -> str | None:
    return sa.inspect(bind).get_pk_constraint("workflow_definitions", schema="workflow")["name"]


def _fk_names(bind) -> set[str]:
    return {
        fk["name"]
        for fk in sa.inspect(bind).get_foreign_keys("workflow_instances", schema="workflow")
    }


def upgrade() -> None:
    bind = op.get_bind()
    _refuse_what_the_keys_would_refuse(bind)

    # forms: one "berichten" per tenant.
    op.execute(sa.text(f"DROP INDEX IF EXISTS form.{OLD_SLUG_INDEX}"))
    op.execute(
        sa.text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {SLUG_INDEX} "
            "ON form.forms (tenant_id, slug) WHERE slug IS NOT NULL"
        )
    )

    # workflow: the definition's key is (tenant_id, code). The foreign key leans
    # on the old primary key, so it goes first and comes back on both columns.
    if OLD_DEFINITION_FK in _fk_names(bind):
        op.drop_constraint(
            OLD_DEFINITION_FK, "workflow_instances", schema="workflow", type_="foreignkey"
        )
    if _pk_name(bind) != DEFINITION_PK:
        op.drop_constraint(
            _pk_name(bind), "workflow_definitions", schema="workflow", type_="primary"
        )
        op.create_primary_key(
            DEFINITION_PK, "workflow_definitions", ["tenant_id", "code"], schema="workflow"
        )
    if DEFINITION_FK not in _fk_names(bind):
        op.create_foreign_key(
            DEFINITION_FK,
            "workflow_instances",
            "workflow_definitions",
            ["tenant_id", "definition_code"],
            ["tenant_id", "code"],
            source_schema="workflow",
            referent_schema="workflow",
        )


def downgrade() -> None:
    # Schema only, and only while no code exists twice: with two tenants each
    # holding "berichten" or "bericht", the old single-column keys cannot come
    # back, and this downgrade fails on them rather than deleting a tenant's form
    # or definition. The rows the startup seed added stay.
    bind = op.get_bind()
    if DEFINITION_FK in _fk_names(bind):
        op.drop_constraint(
            DEFINITION_FK, "workflow_instances", schema="workflow", type_="foreignkey"
        )
    if _pk_name(bind) == DEFINITION_PK:
        op.drop_constraint(
            DEFINITION_PK, "workflow_definitions", schema="workflow", type_="primary"
        )
        op.create_primary_key(
            "workflow_definitions_pkey", "workflow_definitions", ["code"], schema="workflow"
        )
    if OLD_DEFINITION_FK not in _fk_names(bind):
        op.create_foreign_key(
            OLD_DEFINITION_FK,
            "workflow_instances",
            "workflow_definitions",
            ["definition_code"],
            ["code"],
            source_schema="workflow",
            referent_schema="workflow",
        )
    op.execute(sa.text(f"DROP INDEX IF EXISTS form.{SLUG_INDEX}"))
    op.execute(
        sa.text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {OLD_SLUG_INDEX} "
            "ON form.forms (slug) WHERE slug IS NOT NULL"
        )
    )
