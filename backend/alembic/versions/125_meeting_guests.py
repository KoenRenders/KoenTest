"""Gasten op een vergadering (#939): een naam, en aanwezigheid.

Koen, 15 september 2026, bij het nakijken van het verstuurscherm: *"Sla je die
losse mailadressen eigenlijk op in een database? Zouden we dit dan niet liever
voorzien in de agenda zelf? Dan kunnen we ze ook op aanwezig/verontschuldigd
zetten."*

Dat is de betere plaats. Een gastspreker wordt bewust geen `Person` (CR-09
§3.15) — maar hij zit wél mee aan tafel, dus hij hoort in de aanwezigheidslijst
en niet alleen in een verzendlijstje. Twee gevolgen voor het schema:

- ``meeting_extra_recipients`` krijgt een **naam**: een adres alleen is geen
  aanwezigheidsregel waar iemand iets aan heeft.
- ``meeting_attendances`` kan voortaan naar een gast wijzen in plaats van naar
  een persoon. Precies één van de twee is gezet — bewaakt door een CHECK, want
  een rij die naar allebei of naar niets wijst, is een rij zonder betekenis.
"""
import sqlalchemy as sa
from alembic import op

# 125 en niet 124: master landde intussen een eigen 124
# (organisatielijsten). Twee migraties met hetzelfde nummer geven twee
# hoofden, en dan weigert alembic te draaien — de keten moet één lijn zijn.
revision = "125"
down_revision = "124"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meeting_extra_recipients",
                  sa.Column("name", sa.String(255), nullable=True),
                  schema="meetings")
    op.add_column("meeting_attendances",
                  sa.Column("guest_id", sa.Integer, nullable=True),
                  schema="meetings")
    op.create_foreign_key("fk_meeting_attendances_guest", "meeting_attendances",
                          "meeting_extra_recipients", ["guest_id"], ["id"],
                          ondelete="CASCADE",
                          source_schema="meetings", referent_schema="meetings")
    op.create_index("ix_meetings_meeting_attendances_guest", "meeting_attendances",
                    ["guest_id"], schema="meetings")
    op.alter_column("meeting_attendances", "person_id", nullable=True,
                    schema="meetings")
    op.create_check_constraint(
        "ck_meeting_attendances_wie", "meeting_attendances",
        "(person_id IS NOT NULL AND guest_id IS NULL) "
        "OR (person_id IS NULL AND guest_id IS NOT NULL)",
        schema="meetings")


def downgrade() -> None:
    op.drop_constraint("ck_meeting_attendances_wie", "meeting_attendances",
                       type_="check", schema="meetings")
    # Rijen van gasten vallen weg: zonder persoon kunnen ze de oude NOT NULL niet
    # halen, en ze hebben geen plaats om naartoe te verhuizen.
    op.execute("DELETE FROM meetings.meeting_attendances WHERE person_id IS NULL")
    op.alter_column("meeting_attendances", "person_id", nullable=False,
                    schema="meetings")
    op.drop_index("ix_meetings_meeting_attendances_guest", table_name="meeting_attendances",
                  schema="meetings")
    op.drop_constraint("fk_meeting_attendances_guest", "meeting_attendances",
                       type_="foreignkey", schema="meetings")
    op.drop_column("meeting_attendances", "guest_id", schema="meetings")
    op.drop_column("meeting_extra_recipients", "name", schema="meetings")
