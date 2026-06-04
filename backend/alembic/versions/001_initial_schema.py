"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from datetime import datetime
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Code tables ---

    op.create_table(
        "gender_codes",
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("code", "language"),
    )

    op.create_table(
        "contact_type_codes",
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("code", "language"),
    )

    op.create_table(
        "role_codes",
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("code", "language"),
    )

    op.create_table(
        "registration_type_codes",
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("code", "language"),
    )

    op.create_table(
        "payment_status_codes",
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("code", "language"),
    )

    # --- Seed code tables ---
    now = datetime.utcnow()

    op.bulk_insert(
        sa.table(
            "gender_codes",
            sa.column("code", sa.String),
            sa.column("language", sa.String),
            sa.column("value", sa.String),
            sa.column("description", sa.String),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        [
            {"code": "M", "language": "nl", "value": "Man", "description": "Mannelijk geslacht", "created_at": now, "updated_at": now},
            {"code": "F", "language": "nl", "value": "Vrouw", "description": "Vrouwelijk geslacht", "created_at": now, "updated_at": now},
            {"code": "O", "language": "nl", "value": "Onzijdig", "description": "Neutraal geslacht", "created_at": now, "updated_at": now},
        ],
    )

    op.bulk_insert(
        sa.table(
            "contact_type_codes",
            sa.column("code", sa.String),
            sa.column("language", sa.String),
            sa.column("value", sa.String),
            sa.column("description", sa.String),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        [
            {"code": "EMAIL", "language": "nl", "value": "E-mail", "description": "E-mailadres", "created_at": now, "updated_at": now},
            {"code": "MOBILE", "language": "nl", "value": "Mobiel", "description": "Mobiel telefoonnummer", "created_at": now, "updated_at": now},
            {"code": "PHONE", "language": "nl", "value": "Telefoon", "description": "Vast telefoonnummer", "created_at": now, "updated_at": now},
        ],
    )

    op.bulk_insert(
        sa.table(
            "role_codes",
            sa.column("code", sa.String),
            sa.column("language", sa.String),
            sa.column("value", sa.String),
            sa.column("description", sa.String),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        [
            {"code": "ADMIN", "language": "nl", "value": "Beheerder", "description": "Systeembeheerder met volledige toegang", "created_at": now, "updated_at": now},
            {"code": "MEMBER", "language": "nl", "value": "Lid", "description": "Geregistreerd lid van de vereniging", "created_at": now, "updated_at": now},
            {"code": "USER", "language": "nl", "value": "Gebruiker", "description": "Gewone gebruiker", "created_at": now, "updated_at": now},
        ],
    )

    op.bulk_insert(
        sa.table(
            "registration_type_codes",
            sa.column("code", sa.String),
            sa.column("language", sa.String),
            sa.column("value", sa.String),
            sa.column("description", sa.String),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        [
            {"code": "INDIVIDUAL", "language": "nl", "value": "Individueel", "description": "Individuele inschrijving", "created_at": now, "updated_at": now},
            {"code": "FAMILY", "language": "nl", "value": "Gezin", "description": "Gezinsinschrijving", "created_at": now, "updated_at": now},
        ],
    )

    op.bulk_insert(
        sa.table(
            "payment_status_codes",
            sa.column("code", sa.String),
            sa.column("language", sa.String),
            sa.column("value", sa.String),
            sa.column("description", sa.String),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        [
            {"code": "PENDING", "language": "nl", "value": "In afwachting", "description": "Betaling in afwachting", "created_at": now, "updated_at": now},
            {"code": "PAID", "language": "nl", "value": "Betaald", "description": "Betaling ontvangen", "created_at": now, "updated_at": now},
            {"code": "FAILED", "language": "nl", "value": "Mislukt", "description": "Betaling mislukt", "created_at": now, "updated_at": now},
        ],
    )

    # --- postal_codes ---
    op.create_table(
        "postal_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("postal_code", sa.String(4), nullable=False),
        sa.Column("municipality", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_postal_codes_id", "postal_codes", ["id"])
    op.create_index("ix_postal_codes_postal_code", "postal_codes", ["postal_code"])

    # --- members ---
    op.create_table(
        "members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_members_id", "members", ["id"])

    # --- persons ---
    op.create_table(
        "persons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender_code", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["gender_code"], ["gender_codes.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_persons_id", "persons", ["id"])

    # --- member_persons ---
    op.create_table(
        "member_persons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_member_persons_id", "member_persons", ["id"])

    # --- memberships ---
    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memberships_id", "memberships", ["id"])

    # --- addresses ---
    op.create_table(
        "addresses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("street", sa.String(255), nullable=False),
        sa.Column("house_number", sa.String(10), nullable=False),
        sa.Column("bus_number", sa.String(10), nullable=True),
        sa.Column("postal_code_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"]),
        sa.ForeignKeyConstraint(["postal_code_id"], ["postal_codes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id"),
    )
    op.create_index("ix_addresses_id", "addresses", ["id"])

    # --- contact_details ---
    op.create_table(
        "contact_details",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("contact_type_code", sa.String(10), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"]),
        sa.ForeignKeyConstraint(["contact_type_code"], ["contact_type_codes.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contact_details_id", "contact_details", ["id"])

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # --- user_roles ---
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_code", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["role_code"], ["role_codes.code"]),
        sa.PrimaryKeyConstraint("user_id", "role_code"),
    )

    # --- activities ---
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("time", sa.Time(), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("max_participants", sa.Integer(), nullable=True),
        sa.Column("registration_type", sa.String(10), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("member_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("poster_url", sa.String(500), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["registration_type"], ["registration_type_codes.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activities_id", "activities", ["id"])

    # --- registrations ---
    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("is_waitlist", sa.Boolean(), nullable=False),
        sa.Column("registered_at", sa.DateTime(), nullable=False),
        sa.Column("registration_type", sa.String(10), nullable=False),
        sa.Column("contact_name", sa.String(200), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"]),
        sa.ForeignKeyConstraint(["registration_type"], ["registration_type_codes.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_registrations_id", "registrations", ["id"])

    # --- ideas ---
    op.create_table(
        "ideas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("submitter_name", sa.String(200), nullable=False),
        sa.Column("submitter_email", sa.String(255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("is_reviewed", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ideas_id", "ideas", ["id"])

    # --- cms_pages ---
    op.create_table(
        "cms_pages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cms_pages_id", "cms_pages", ["id"])
    op.create_index("ix_cms_pages_slug", "cms_pages", ["slug"], unique=True)

    # --- webshop_products ---
    op.create_table(
        "webshop_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("regular_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("member_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webshop_products_id", "webshop_products", ["id"])

    # --- orders ---
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("confirmation_number", sa.String(20), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=True),
        sa.Column("customer_name", sa.String(200), nullable=False),
        sa.Column("customer_email", sa.String(255), nullable=False),
        sa.Column("is_member", sa.Boolean(), nullable=False),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("payment_status", sa.String(10), nullable=False),
        sa.Column("mollie_payment_id", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
        sa.ForeignKeyConstraint(["payment_status"], ["payment_status_codes.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_id", "orders", ["id"])
    op.create_index("ix_orders_confirmation_number", "orders", ["confirmation_number"], unique=True)

    # --- order_items ---
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["webshop_products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_items_id", "order_items", ["id"])


def downgrade() -> None:
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("webshop_products")
    op.drop_table("cms_pages")
    op.drop_table("ideas")
    op.drop_table("registrations")
    op.drop_table("activities")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("contact_details")
    op.drop_table("addresses")
    op.drop_table("memberships")
    op.drop_table("member_persons")
    op.drop_table("persons")
    op.drop_table("members")
    op.drop_table("postal_codes")
    op.drop_table("gender_codes")
    op.drop_table("contact_type_codes")
    op.drop_table("role_codes")
    op.drop_table("registration_type_codes")
    op.drop_table("payment_status_codes")
