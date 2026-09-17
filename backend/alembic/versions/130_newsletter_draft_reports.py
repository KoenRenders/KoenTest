"""Raakje reads whole reports, not points (#984).

Koen, 17 September 2026, validating the newsletter on HDEV: *"Gelieve enkel
verslagen te kunnen aanvinken, geen punten."* The author ticks a meeting
report as a whole — the latest one by default — and Raakje takes from it only
what matters to readers. The draft therefore remembers meeting ids instead of
meeting-point ids.

The column is renamed, and emptied: a list of point ids is not a list of
meeting ids, and reading one as the other would tick the wrong reports. Only
drafts on the test environments carry values; the module has not reached PROD.

Idempotent: renamed only when the old column is still there.
"""
from alembic import op
import sqlalchemy as sa

# De id is een tijdstempel en geen volgnummer (#951).
revision = "130_2026_09_17_073104"
down_revision = "129_2026_09_16_221108"
branch_labels = None
depends_on = None


def _has_column(name: str) -> bool:
    return bool(op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = 'newsletter' "
        "AND table_name = 'newsletters' AND column_name = :c"), {"c": name}).scalar())


def upgrade() -> None:
    if _has_column("draft_meeting_item_ids"):
        op.alter_column("newsletters", "draft_meeting_item_ids",
                        new_column_name="draft_meeting_ids", schema="newsletter")
        op.execute("UPDATE newsletter.newsletters SET draft_meeting_ids = '[]'::json")


def downgrade() -> None:
    # Schema only: the ticked reports do not turn back into ticked points.
    if _has_column("draft_meeting_ids"):
        op.alter_column("newsletters", "draft_meeting_ids",
                        new_column_name="draft_meeting_item_ids", schema="newsletter")
        op.execute("UPDATE newsletter.newsletters SET draft_meeting_item_ids = '[]'::json")
