"""A sponsor logo chooses whether it appears in the footer (#1057).

Koen added the municipality as a second sponsor logo and it appeared straight away
under every public page. That is not a bug in the code: `kind="sponsor"` was read by
two things at once — the footer band and the Design Studio's logo picker — so a logo
meant for a poster could not exist without also standing in the footer.

One column separates them. `is_active` keeps meaning "nowhere"; this flag sits under
it, not beside it, and only the footer listens. The Design Studio keeps offering
every active sponsor logo on purpose: a logo that does not belong in the footer does
not therefore belong off the poster.

**Default true, and existing rows come along as true** (Koen, 20 September 2026), so
nothing changes about what the footer shows today and an ordinary sponsor asks for no
extra handling. The accepted price: the next poster-only logo needs the tick removed.

The column only carries meaning for `kind="sponsor"`; for the other kinds it is
present and ignored. Idempotent: the column is only added when it is missing.
"""
from alembic import op
import sqlalchemy as sa


# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '145_2026_09_20_074133'
down_revision = '144_2026_09_20_065547'
branch_labels = None
depends_on = None

KOLOM = "show_in_footer"


def _heeft_kolom() -> bool:
    return bool(op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'media' AND table_name = 'media_assets' "
        "AND column_name = :k"), {"k": KOLOM}).scalar())


def upgrade() -> None:
    if not _heeft_kolom():
        # server_default zet de bestaande rijen in dezelfde stap op waar; zonder
        # hem zou NOT NULL op een gevulde tabel falen.
        op.add_column("media_assets",
                      sa.Column(KOLOM, sa.Boolean, nullable=False,
                                server_default=sa.true()),
                      schema="media")


def downgrade() -> None:
    """Alleen het schema. De keuze per logo gaat verloren — ze bestaat hierna
    nergens meer, en de footer toont weer élk actief sponsorlogo."""
    if _heeft_kolom():
        op.drop_column("media_assets", KOLOM, schema="media")
