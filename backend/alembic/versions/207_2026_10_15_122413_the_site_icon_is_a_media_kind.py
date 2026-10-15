"""the favicon of a site is a media kind of its own (CR-32 R6, F8)

`site_icon` is the picture a tenant's browser tab shows. Like the association's
logo it is a kind, not a setting (Koen, 15 October 2026, on the favicon: "zoals
het logo" — "akkoord"): the newest picture of the kind wins, so a new upload
replaces the old one. A media kind is one row in the code list and one member
in the code (CR-12 phase 4); this is the row, for a database that exists — a
database built from scratch gets it from the seed in `media/codes.py`.

Idempotent: a row that stands is left alone.
"""

from alembic import op

revision = "207_2026_10_15_122413"
down_revision = "205_2026_10_15_082601"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO media.media_kind_codes (code, sort_order, is_active, created_at) "
        "VALUES ('site_icon', 35, true, now()) ON CONFLICT (code) DO NOTHING"
    )
    for language, value in (("nl", "Favicon van de site"), ("en", "Site icon")):
        op.execute(
            "INSERT INTO media.media_kind_labels (code, language, value, created_at, updated_at) "
            f"VALUES ('site_icon', '{language}', '{value}', now(), now()) "
            "ON CONFLICT (code, language) DO NOTHING"
        )


def downgrade() -> None:
    # The pictures of the kind go with it: the foreign key would refuse the row.
    op.execute("DELETE FROM media.media_assets WHERE kind = 'site_icon'")
    op.execute("DELETE FROM media.media_kind_labels WHERE code = 'site_icon'")
    op.execute("DELETE FROM media.media_kind_codes WHERE code = 'site_icon'")
