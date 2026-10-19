"""the organisations a tenant sees, by fact

CR-26 phase 2 (#2020, F9). A department lists the organisations that have a fact at it,
as it lists persons (`person_tenants`, 314): the view `mdm.organisation_tenants`
answers *(tenant, organisation)*. A fact is

- the tenant shows the organisation (`tenants.organization_id`);
- an order of the tenant names its party as the buyer (`sales_orders.buyer_party_id`);
- a person who acts for it is at the tenant (`person_tenants`, relation kind `ACTS_FOR`):
  only that kind counts — a circle membership is no fact — and an ended relation still
  counts, as an ended membership does for `household_tenants`.

A new kind of fact (an invoice, a registration for an organisation) adds a branch.
An organisation with none is at no tenant: the platform sees it, a department does not.
The view is additive; nothing is moved or dropped.
"""

from alembic import op

# The id is a timestamp, not a sequence number (#951).
revision = "318_2026_10_19_154158"
down_revision = "317_2026_10_19_105524"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW mdm.organisation_tenants AS
        SELECT t.id AS tenant_id, t.organization_id
          FROM mdm.tenants t
         WHERE t.organization_id IS NOT NULL
        UNION
        SELECT so.tenant_id, o.id
          FROM sales.sales_orders so
          JOIN mdm.organizations o ON o.party_id = so.buyer_party_id
         WHERE so.deleted_at IS NULL
        UNION
        SELECT pt.tenant_id, o.id
          FROM mdm.party_relationships pr
          JOIN mdm.persons p ON p.party_id = pr.from_party_id
          JOIN mdm.person_tenants pt ON pt.person_id = p.id
          JOIN mdm.organizations o ON o.party_id = pr.to_party_id
         WHERE pr.kind = 'ACTS_FOR' AND pr.deleted_at IS NULL;
        COMMENT ON VIEW mdm.organisation_tenants IS
            'CR-26 F9: the organisations at a tenant by fact. A new kind of fact adds a '
            'branch here; an organisation without one is not at the tenant.';
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS mdm.organisation_tenants")
