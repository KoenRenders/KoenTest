"""The platform becomes a tenant of its own kind (#854).

Decided by Koen on 10 September 2026, during the v2.2.0 validation; it revises the
note *"the operator is not a tenant"* from the same morning. See
``docs/intermediate-architecture-upgrade-v1.md`` §7 — that is the source, this file is
one third of the execution.

> *"The platform is going to send mail, it has a name, in time a logo, a bank account
> number, a gmail password, tiktok, facebook, instagram, a privacy statement, a sender
> address, a mollie key. But it is not a Raak afdeling — companies may become customers
> too. 'Platform' is a type of tenant then."*

That list IS the list of tenant settings. Building a second store for the same eight
things, for a single row, costs more than the objection the previous decision carried.

**The platform is NOT row 1.** ``raak`` (id 1, ``ACCOUNT``) stays the customer; there
will be customers with nothing to do with Raak, and merging those two ideas into one row
is the kind of confusion you cannot undo later. So: a new row, without a parent.

**Idempotent on the code**, like migration 086: an environment that already carries the
row keeps it, and no id is hard-coded here — the row is looked up by
``org_type = 'PLATFORM'`` everywhere in the code, never by number. That is deliberate:
086 could hand out ids 1..3 because it created the table, but by now an environment may
have created tenants of its own through /admin/tenants, and id 4 is not free everywhere.
"""
from alembic import op
import sqlalchemy as sa

revision = "097"
down_revision = "096"
branch_labels = None
depends_on = None

PLATFORM_CODE = "platform"
PLATFORM_NAME = "Digital Platform"

# The settings the platform starts with. Deliberately only what a platform IS — a name
# and a language. No membership fee, no payment term: a platform has no members, and a
# value nobody can explain later is worse than a missing one.
START_SETTINGS = {
    "display_name": PLATFORM_NAME,
    "language": "nl_BE",
}


def upgrade() -> None:
    bind = op.get_bind()

    # 1. The CHECK from migration 078 knows ACCOUNT and UNIT; PLATFORM has to be added
    #    before the row can be inserted.
    op.execute("ALTER TABLE mdm.organizations DROP CONSTRAINT IF EXISTS ck_org_type")
    op.create_check_constraint(
        "ck_org_type", "organizations",
        "org_type IN ('ACCOUNT', 'UNIT', 'PLATFORM')", schema="mdm")

    # 2. The row itself — no parent, because the platform hangs under nobody.
    existing = bind.execute(sa.text(
        "SELECT id FROM mdm.organizations WHERE org_type = 'PLATFORM'")).scalar()
    if existing is None:
        existing = bind.execute(sa.text(
            "INSERT INTO mdm.organizations (parent_id, org_type, code, name, is_active) "
            "VALUES (NULL, 'PLATFORM', :c, :n, TRUE) RETURNING id"),
            {"c": PLATFORM_CODE, "n": PLATFORM_NAME}).scalar()

    # 3. Its base settings, idempotent per key. Koen fills in the real values (sender,
    #    keys, socials) through /admin/tenants; without that step the platform runs on
    #    the defaults from the code, which is a working state and not a broken one.
    for key, value in START_SETTINGS.items():
        present = bind.execute(sa.text(
            "SELECT 1 FROM kernel_tenant_settings WHERE tenant_id = :t AND key = :k"),
            {"t": existing, "k": key}).scalar()
        if not present:
            bind.execute(sa.text(
                "INSERT INTO kernel_tenant_settings (tenant_id, key, value) "
                "VALUES (:t, :k, :v)"), {"t": existing, "k": key, "v": value})


def downgrade() -> None:
    bind = op.get_bind()
    platform_id = bind.execute(sa.text(
        "SELECT id FROM mdm.organizations WHERE org_type = 'PLATFORM'")).scalar()
    if platform_id is not None:
        bind.execute(sa.text("DELETE FROM kernel_tenant_settings WHERE tenant_id = :t"),
                     {"t": platform_id})
        bind.execute(sa.text("DELETE FROM mdm.organizations WHERE id = :i"),
                     {"i": platform_id})
    op.execute("ALTER TABLE mdm.organizations DROP CONSTRAINT IF EXISTS ck_org_type")
    op.create_check_constraint(
        "ck_org_type", "organizations", "org_type IN ('ACCOUNT', 'UNIT')", schema="mdm")
