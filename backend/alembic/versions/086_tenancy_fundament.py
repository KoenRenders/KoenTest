"""Fase 5 (#406): tenant-fundament — organizations-seed (account Raak + units
Millegem/Voorbeeldafdeling) en ``tenant_id`` (NOT NULL + index, RLS-klaar §7)
op alle tenant-tabellen. Bestaande rijen worden Millegem (id 2).

Revision ID: 086
Revises: 085
"""
from alembic import op
import sqlalchemy as sa

revision = "086"
down_revision = "085"
branch_labels = None
depends_on = None

# Deterministische ids — code (app/kernel/tenancy.py) en migraties delen ze.
ORGANIZATIONS = [
    (1, None, "ACCOUNT", "raak", "Raak"),
    (2, 1, "UNIT", "raakmillegem", "Raak Millegem"),
    (3, 1, "UNIT", "raakvoorbeeldafdeling", "Raak Voorbeeldafdeling"),
]

MILLEGEM_ID = 2

TENANT_TABLES = [
    ("activities", "activities"),
    ("activities", "activity_date_history"),
    ("activities", "activity_dates"),
    ("activities", "activity_history"),
    ("activities", "activity_products"),
    ("activities", "activity_sub_registrations"),
    ("activities", "component_history"),
    ("activities", "product_history"),
    ("activities", "registration_item_history"),
    ("activities", "registration_items"),
    ("activities", "registrations"),
    ("ai", "chatbot_info"),
    ("analytics", "business_events"),
    ("cms", "cms_pages"),
    ("form", "form_field_options"),
    ("form", "form_fields"),
    ("form", "form_sections"),
    ("form", "form_submission_answers"),
    ("form", "form_submissions"),
    ("form", "forms"),
    ("mail", "email_log"),
    ("mdm", "address_history"),
    ("mdm", "addresses"),
    ("mdm", "contact_detail_history"),
    ("mdm", "contact_details"),
    ("mdm", "external_numbers"),
    ("mdm", "member_history"),
    ("mdm", "member_person_history"),
    ("mdm", "member_persons"),
    ("mdm", "members"),
    ("mdm", "person_history"),
    ("mdm", "persons"),
    ("media", "media_assets"),
    ("membership", "membership_history"),
    ("membership", "memberships"),
    ("payment", "gateway_payments"),
    ("payment", "payment_record_history"),
    ("payment", "payment_records"),
    ("workflow", "workflow_definitions"),
    ("workflow", "workflow_instances"),
    ("workflow", "workflow_tasks"),
]


def _has_column(bind, schema: str, table: str, column: str) -> bool:
    return bool(bind.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = :s "
        "AND table_name = :t AND column_name = :c"),
        {"s": schema, "t": table, "c": column}).scalar())


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Organizations-seed (idempotent op code).
    for org_id, parent_id, org_type, code, name in ORGANIZATIONS:
        bestaat = bind.execute(sa.text(
            "SELECT 1 FROM mdm.organizations WHERE code = :c"), {"c": code}).scalar()
        if not bestaat:
            bind.execute(sa.text(
                "INSERT INTO mdm.organizations (id, parent_id, org_type, code, name, is_active) "
                "VALUES (:i, :p, :ot, :c, :n, TRUE)"),
                {"i": org_id, "p": parent_id, "ot": org_type, "c": code, "n": name})
    # Sequence voorbij de expliciete ids zetten.
    op.execute("SELECT setval(pg_get_serial_sequence('mdm.organizations', 'id'), "
               "GREATEST((SELECT MAX(id) FROM mdm.organizations), 1))")

    # 2. tenant_id op elke tenant-tabel: NOT NULL + server_default Millegem +
    # index. De server_default blijft bewust staan als vangnet voor schrijvers
    # buiten de ORM (de ORM zet de actieve tenant via de mixin-default).
    for schema, table in TENANT_TABLES:
        if not _has_column(bind, schema, table, "tenant_id"):
            op.execute(f"ALTER TABLE {schema}.{table} ADD COLUMN tenant_id INTEGER "
                       f"NOT NULL DEFAULT {MILLEGEM_ID}")
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id "
                   f"ON {schema}.{table} (tenant_id)")


def downgrade() -> None:
    for schema, table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {schema}.{table} DROP COLUMN IF EXISTS tenant_id")
