"""An optional friendly URL per activity (#884).

Koen: *"Would it be possible to optionally define a friendly URL next to the current one
(e.g. `/activiteiten/7/fotos`)?"*

Follows the pattern the CMS pages already use — a `slug` with uniqueness **per tenant**
(`ix_cms_pages_tenant_slug`) — instead of inventing a second one. Nullable, because the
feature is optional: without a slug everything behaves exactly as it does today.

**Unique per tenant and not globally.** Two afdelingen may both have a `zomerfeest-2026`;
they are different associations on different addresses, and a global constraint would let
the first one to use a name take it from everybody else.

**Partial index (`WHERE slug IS NOT NULL`)**, because NULLs are not equal to each other in
Postgres but a partial index states the intent rather than relying on that: activities
without a slug do not participate in the uniqueness at all.
"""
from alembic import op
import sqlalchemy as sa

revision = "114"
down_revision = "113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("slug", sa.String(255), nullable=True),
                  schema="activities")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_activities_tenant_slug "
        "ON activities.activities (tenant_id, slug) WHERE slug IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS activities.ix_activities_tenant_slug")
    op.drop_column("activities", "slug", schema="activities")
