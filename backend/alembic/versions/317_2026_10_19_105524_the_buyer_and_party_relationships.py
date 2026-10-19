"""the buyer: party relationships, the buyer on an order, the invoices module

CR-26 phase 2 (#2020). What a person is to an organisation becomes one table, an order
can name a party as its buyer, and one module switches selling to an organisation.

- **`mdm.party_relationships`** (F4) replaces `mdm.organization_persons`: `from_party` is
  in a relation of a `kind` to `to_party`, with a period, on the account scope. The rows
  move **with their ids** (the meeting circle reads them by id), their kind and their
  period; a person's party and an organisation's party stand where the person and the
  organisation stood. The code list `organization_relation_type` becomes
  `party_relationship_kind` and gains `ACTS_FOR` (the person who buys on behalf of an
  organisation, C4.7).
- **`mdm.person_tenants`** (F9) is replaced: a person is at a tenant through a relation
  to the party that tenant shows, as before the circle's `tenant_id` said.
- **`sales.sales_orders`** (F8) gets `buyer_party_id` — a key to `mdm.parties`, NULL for
  a guest (the named exception of B4) — and the buyer copy: name, address and VAT number
  as they were at placement, nullable (a private person has no VAT number and a guest's
  address is asked of nobody by this change). `person_id` stays and keeps its meaning,
  the person who placed the order.
- **`ck_tenant_modules_module_code`** (F14) is widened with `invoices`.

Expand and contract in one release (B4, Koen: "a, maar wel in één release"): the previous
tag cannot run on the result; the safety is the checked dump and `raak restore-test`.
"""

from alembic import op

# The id is a timestamp, not a sequence number (#951).
revision = "317_2026_10_19_105524"
down_revision = "316_2026_10_19_095522"
branch_labels = None
depends_on = None

MODULES = (
    "activities",
    "membership",
    "payment",
    "forms",
    "cms",
    "media",
    "newsletter",
    "meetings",
    "designstudio",
    "reporting",
    "chatbot",
    "shop",
    "invoices",
)


def _count(sql: str) -> int:
    return op.get_bind().exec_driver_sql(sql).scalar() or 0


def _move_the_circle() -> None:
    # ── 1. The kinds: the old list, the new one beside it ────────────────────
    op.execute(
        """
        CREATE TABLE mdm.party_relationship_kind_codes (
            code VARCHAR(30) PRIMARY KEY,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        INSERT INTO mdm.party_relationship_kind_codes (code, sort_order, is_active, created_at)
            SELECT code, sort_order, is_active, created_at
              FROM mdm.organization_relation_type_codes;
        INSERT INTO mdm.party_relationship_kind_codes (code, sort_order)
            VALUES ('ACTS_FOR', 20);
        CREATE TABLE mdm.party_relationship_kind_labels (
            code VARCHAR(30) NOT NULL REFERENCES mdm.party_relationship_kind_codes (code),
            language VARCHAR(5) NOT NULL REFERENCES mdm.language_codes (code),
            value VARCHAR(100) NOT NULL,
            description VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (code, language)
        );
        INSERT INTO mdm.party_relationship_kind_labels
                (code, language, value, description, created_at, updated_at)
            SELECT code, language, value, description, created_at, updated_at
              FROM mdm.organization_relation_type_labels;
        INSERT INTO mdm.party_relationship_kind_labels (code, language, value)
            VALUES ('ACTS_FOR', 'nl', 'Treedt op namens'), ('ACTS_FOR', 'en', 'Acts for');
        """
    )

    # ── 2. The relationships, with the ids the circle already holds ──────────
    op.execute(
        """
        CREATE TABLE mdm.party_relationships (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES mdm.parties (id),
            from_party_id INTEGER NOT NULL REFERENCES mdm.parties (id),
            to_party_id INTEGER NOT NULL REFERENCES mdm.parties (id),
            kind VARCHAR(30) NOT NULL REFERENCES mdm.party_relationship_kind_codes (code),
            start_date DATE,
            end_date DATE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ,
            CONSTRAINT ck_party_relationships_period
                CHECK (start_date IS NULL OR end_date IS NULL OR start_date <= end_date)
        );
        CREATE INDEX ix_party_relationships_account_id ON mdm.party_relationships (account_id);
        CREATE INDEX ix_party_relationships_from_party_id ON mdm.party_relationships (from_party_id);
        CREATE INDEX ix_party_relationships_to_party_id ON mdm.party_relationships (to_party_id);
        INSERT INTO mdm.party_relationships
                (id, account_id, from_party_id, to_party_id, kind, start_date, end_date,
                 created_at, updated_at, deleted_at)
            SELECT op.id, o.account_id, p.party_id, o.party_id, op.relation_type,
                   op.start_date, op.end_date, op.created_at, op.updated_at, op.deleted_at
              FROM mdm.organization_persons op
              JOIN mdm.organizations o ON o.id = op.organization_id
              JOIN mdm.persons p ON p.id = op.person_id;
        """
    )
    before = _count("SELECT count(*) FROM mdm.organization_persons")
    after = _count("SELECT count(*) FROM mdm.party_relationships")
    if before != after:
        lost = [
            row[0]
            for row in op.get_bind().exec_driver_sql(
                "SELECT id FROM mdm.organization_persons WHERE id NOT IN "
                "(SELECT id FROM mdm.party_relationships) ORDER BY id LIMIT 20"
            )
        ]
        raise RuntimeError(f"CR-26: rows of organization_persons found no party: {lost}")
    op.execute(
        "SELECT setval(pg_get_serial_sequence('mdm.party_relationships', 'id'), "
        "COALESCE((SELECT max(id) FROM mdm.party_relationships), 0) + 1, false)"
    )

    # ── 3. A person is at a tenant through a relation to the party it shows ──
    op.execute(
        """
        CREATE OR REPLACE VIEW mdm.person_tenants AS
        SELECT ht.tenant_id, mp.person_id
          FROM mdm.member_persons mp
          JOIN mdm.household_tenants ht ON ht.member_id = mp.member_id
         WHERE mp.deleted_at IS NULL
        UNION
        SELECT reg.tenant_id, reg.person_id
          FROM activities.registrations reg
         WHERE reg.person_id IS NOT NULL AND reg.deleted_at IS NULL
        UNION
        SELECT so.tenant_id, so.person_id
          FROM sales.sales_orders so
         WHERE so.person_id IS NOT NULL AND so.deleted_at IS NULL
        UNION
        SELECT t.id, p.id
          FROM mdm.party_relationships pr
          JOIN mdm.persons p ON p.party_id = pr.from_party_id
          JOIN mdm.organizations o ON o.party_id = pr.to_party_id
          JOIN mdm.tenants t ON t.organization_id = o.id
         WHERE pr.deleted_at IS NULL;
        COMMENT ON VIEW mdm.person_tenants IS
            'CR-26 F9: the persons at a tenant by fact. A new kind of fact (an invoice, '
            'a webshop customer) adds a branch here; a person without one is simply not '
            'at the tenant (mdm CONTRACT.md).';
        """
    )

    # ── 4. The old table and its list go ─────────────────────────────────────
    op.execute(
        """
        DROP TABLE mdm.organization_persons;
        DROP TABLE mdm.organization_relation_type_labels;
        DROP TABLE mdm.organization_relation_type_codes;
        """
    )


def upgrade() -> None:
    # Idempotent: a database that already ran steps 1 to 4 has no `organization_persons`.
    if op.get_bind().exec_driver_sql("SELECT to_regclass('mdm.organization_persons')").scalar():
        _move_the_circle()

    # ── 5. The buyer of an order, and the copy of who it was ─────────────────
    op.execute(
        """
        ALTER TABLE sales.sales_orders
            ADD COLUMN IF NOT EXISTS buyer_party_id INTEGER REFERENCES mdm.parties (id),
            ADD COLUMN IF NOT EXISTS buyer_name VARCHAR(200),
            ADD COLUMN IF NOT EXISTS buyer_street VARCHAR(200),
            ADD COLUMN IF NOT EXISTS buyer_house_number VARCHAR(20),
            ADD COLUMN IF NOT EXISTS buyer_bus_number VARCHAR(20),
            ADD COLUMN IF NOT EXISTS buyer_postal_code VARCHAR(10),
            ADD COLUMN IF NOT EXISTS buyer_municipality VARCHAR(100),
            ADD COLUMN IF NOT EXISTS buyer_country VARCHAR(2),
            ADD COLUMN IF NOT EXISTS buyer_vat_number VARCHAR(50);
        CREATE INDEX IF NOT EXISTS ix_sales_orders_buyer_party_id ON sales.sales_orders (buyer_party_id);
        """
    )

    # ── 6. The invoices module joins the modules a tenant can have ───────────
    allowed = ", ".join(f"'{code}'" for code in MODULES)
    op.execute(
        "ALTER TABLE mdm.tenant_modules DROP CONSTRAINT IF EXISTS ck_tenant_modules_module_code"
    )
    op.execute(
        "ALTER TABLE mdm.tenant_modules ADD CONSTRAINT ck_tenant_modules_module_code "
        f"CHECK (module_code IN ({allowed}))"
    )


def downgrade() -> None:
    # Not reversible in one step, like 314 to 316 under it: the way back is the dump
    # taken before the deploy (B4).
    raise NotImplementedError("CR-26: restore the dump taken before the deploy")
