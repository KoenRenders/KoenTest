"""designstudio: four own highlights

Koen, 20 September 2026: "zouden we kernpunt 5 en 6 niet structureel
verwijderen?" — yes. Eight rows filled the left column to the brim and no real
poster ever needed more than four own points next to date and place; six
rows in total is calmer and Instagram shows four anyway. Rows five and six
that exist (HDEV only) are dropped, knowingly; the CHECK follows the service.
"""
from alembic import op

# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '143_2026_09_20_062539'
down_revision = '142_2026_09_20_090500'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM designstudio.design_highlights WHERE sort_order >= 4")
    op.execute("ALTER TABLE designstudio.design_highlights DROP CONSTRAINT IF EXISTS ck_design_highlight_order")
    op.create_check_constraint("ck_design_highlight_order", "design_highlights",
                               "sort_order >= 0 AND sort_order < 4", schema="designstudio")


def downgrade() -> None:
    # Schema only: the dropped rows five and six do not come back.
    op.execute("ALTER TABLE designstudio.design_highlights DROP CONSTRAINT IF EXISTS ck_design_highlight_order")
    op.create_check_constraint("ck_design_highlight_order", "design_highlights",
                               "sort_order >= 0 AND sort_order < 6", schema="designstudio")
