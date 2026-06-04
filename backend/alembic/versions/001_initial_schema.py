"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # families
    op.create_table(
        "families",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("street", sa.String(255), nullable=False),
        sa.Column("house_number", sa.String(20), nullable=False),
        sa.Column("bus_number", sa.String(20), nullable=True),
        sa.Column("postal_code", sa.String(10), nullable=False),
        sa.Column("municipality", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_families_id", "families", ["id"])

    # family_members
    op.create_table(
        "family_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("family_id", sa.Integer(), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(20), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_family_members_id", "family_members", ["id"])

    # memberships
    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("family_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memberships_id", "memberships", ["id"])

    # admin_users
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_users_id", "admin_users", ["id"])
    op.create_index("ix_admin_users_username", "admin_users", ["username"], unique=True)

    # activities
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("time", sa.Time(), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("max_participants", sa.Integer(), nullable=True),
        sa.Column(
            "registration_type",
            sa.Enum("individual", "family", name="registrationtypeenum"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("member_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("poster_url", sa.String(500), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activities_id", "activities", ["id"])

    # registrations
    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("family_id", sa.Integer(), nullable=True),
        sa.Column("family_member_id", sa.Integer(), nullable=True),
        sa.Column("is_waitlist", sa.Boolean(), nullable=False),
        sa.Column("registered_at", sa.DateTime(), nullable=False),
        sa.Column(
            "registration_type",
            sa.Enum("individual", "family", name="registrationtypeenum"),
            nullable=False,
        ),
        sa.Column("contact_name", sa.String(200), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"]),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"]),
        sa.ForeignKeyConstraint(["family_member_id"], ["family_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_registrations_id", "registrations", ["id"])

    # ideas
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

    # cms_pages
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

    # webshop_products
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

    # orders
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("confirmation_number", sa.String(20), nullable=False),
        sa.Column("family_id", sa.Integer(), nullable=True),
        sa.Column("customer_name", sa.String(200), nullable=False),
        sa.Column("customer_email", sa.String(255), nullable=False),
        sa.Column("is_member", sa.Boolean(), nullable=False),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "payment_status",
            sa.Enum("pending", "paid", "failed", name="paymentstatusenum"),
            nullable=False,
        ),
        sa.Column("mollie_payment_id", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_id", "orders", ["id"])
    op.create_index("ix_orders_confirmation_number", "orders", ["confirmation_number"], unique=True)

    # order_items
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
    op.drop_table("admin_users")
    op.drop_table("memberships")
    op.drop_table("family_members")
    op.drop_table("families")
    op.execute("DROP TYPE IF EXISTS registrationtypeenum")
    op.execute("DROP TYPE IF EXISTS paymentstatusenum")
