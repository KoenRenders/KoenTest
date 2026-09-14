"""Meetings module (CR-09, #258): the meeting circle in MDM, the document in its own schema.

Two schemas, one migration, because the meetings tables cannot be created
without the relation that decides who is in the circle.

**mdm** gets a generic person↔organisation relation. The board-meeting circle is
not derivable from membership — it holds fixed participants who are not board
members, and the branch supporter of the national organisation, who is not a
member at all. Modelling that as a relation to the organisation keeps persons and
their contact details in master data, where they already live, instead of in a
second address list.

The relation type is **two tables, not one**, and that is deliberate. The older
code tables (``relation_type_codes``, ``legal_form_codes``) key on
(code, language) — which means the code alone is not unique, so nothing can
point a foreign key at it, and a unique key on the code alone is exactly what
silently dropped every English label in migration 017. Splitting identity from
translation fixes both at once: ``organization_relation_types`` holds the code
(one row per relation, referenceable), ``organization_relation_type_labels``
holds its texts per language. A third language is a row; the foreign key keeps
working.

**meetings** gets the document: sections and items as rows (so the next agenda is
generated, not copied), attendance, one-off recipients, and the files. The files
are deliberately *not* media assets: media serves publicly by design, so board
documents there would depend forever on a flag being set at every upload. A table
here with an admin-only download route fails closed instead.

Idempotent throughout — every create is guarded by an existence check, so a
re-run on a database that already has the tables changes nothing.
"""
import sqlalchemy as sa
from alembic import op

revision = "122"
down_revision = "121"
branch_labels = None
depends_on = None


RELATION_TYPES = ["BOARD_MEETING"]

RELATION_TYPE_LABELS = [
    ("BOARD_MEETING", "nl", "Bestuursvergadering",
     "Neemt deel aan de maandelijkse vergadering en krijgt agenda en verslag."),
    ("BOARD_MEETING", "en", "Board meeting",
     "Takes part in the monthly meeting and receives the agenda and the report."),
]


def _has_table(schema: str, name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name, schema=schema)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS meetings")

    # ── mdm: the circle as master data ───────────────────────────────────────
    if not _has_table("mdm", "organization_relation_types"):
        op.create_table(
            "organization_relation_types",
            sa.Column("code", sa.String(30), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            schema="mdm",
        )

    if not _has_table("mdm", "organization_relation_type_labels"):
        op.create_table(
            "organization_relation_type_labels",
            sa.Column("code", sa.String(30),
                      sa.ForeignKey("mdm.organization_relation_types.code"),
                      primary_key=True),
            sa.Column("language", sa.String(5), primary_key=True),
            sa.Column("value", sa.String(100), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            schema="mdm",
        )

    for code in RELATION_TYPES:
        op.execute(sa.text(
            "INSERT INTO mdm.organization_relation_types (code) VALUES (:c) "
            "ON CONFLICT (code) DO NOTHING").bindparams(c=code))
    for code, language, value, description in RELATION_TYPE_LABELS:
        op.execute(sa.text(
            "INSERT INTO mdm.organization_relation_type_labels "
            "(code, language, value, description) VALUES (:c, :l, :v, :d) "
            "ON CONFLICT (code, language) DO NOTHING"
        ).bindparams(c=code, l=language, v=value, d=description))

    if not _has_table("mdm", "organization_persons"):
        op.create_table(
            "organization_persons",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("organization_id", sa.Integer,
                      sa.ForeignKey("mdm.organizations.id"), nullable=False),
            # Soft-ref, no FK: `organization_persons` lives in mdm and points at
            # mdm.persons, so this one *could* be a real FK — but keeping every
            # person reference in this migration the same shape is worth more than
            # one extra constraint. The index below is what queries need.
            sa.Column("person_id", sa.Integer, nullable=False),
            sa.Column("relation_type", sa.String(30),
                      sa.ForeignKey("mdm.organization_relation_types.code"),
                      nullable=False, server_default="BOARD_MEETING"),
            # Ending a relation end-dates it; the attendance of an old report
            # must keep resolving to the person who was there.
            sa.Column("start_date", sa.Date, nullable=True),
            sa.Column("end_date", sa.Date, nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            schema="mdm",
        )
        op.create_index("ix_mdm_organization_persons_person",
                        "organization_persons", ["person_id"], schema="mdm")
        op.create_index("ix_mdm_organization_persons_org",
                        "organization_persons", ["organization_id"], schema="mdm")

    # ── meetings: the document ───────────────────────────────────────────────
    if not _has_table("meetings", "meetings"):
        op.create_table(
            "meetings",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("meeting_date", sa.Date, nullable=False, index=True),
            sa.Column("start_time", sa.Time, nullable=True),
            sa.Column("location", sa.String(255), nullable=True),
            sa.Column("status", sa.String(10), nullable=False, server_default="agenda"),
            sa.Column("agenda_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("report_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("status IN ('agenda','report','sent')",
                               name="ck_meetings_status"),
            schema="meetings",
        )

    if not _has_table("meetings", "meeting_sections"):
        op.create_table(
            "meeting_sections",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("meeting_id", sa.Integer,
                      sa.ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("title", sa.String(255), nullable=True),
            sa.Column("position", sa.Integer, nullable=False, server_default="0"),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(
                "kind IN ('EVALUATION','UPCOMING','MEMBERS','IDEAS','MISC','CUSTOM')",
                name="ck_meeting_sections_kind"),
            schema="meetings",
        )

    if not _has_table("meetings", "meeting_items"):
        op.create_table(
            "meeting_items",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("meeting_id", sa.Integer,
                      sa.ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("section_id", sa.Integer,
                      sa.ForeignKey("meetings.meeting_sections.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("position", sa.Integer, nullable=False, server_default="0"),
            sa.Column("title", sa.String(255), nullable=True),
            sa.Column("notes", sa.Text, nullable=True),
            # Soft-refs and deliberately NOT foreign keys: a FK across schemas
            # would tie the deploys of two domains together
            # (`test_schema_boundaries`). In code this domain reaches the
            # subjects through the other domains' facades; a reference that no
            # longer resolves renders as a free item instead of breaking.
            sa.Column("activity_id", sa.Integer, nullable=True, index=True),
            sa.Column("member_id", sa.Integer, nullable=True, index=True),
            sa.Column("noted_steward_person_id", sa.Integer, nullable=True),
            sa.Column("carried_over_from", sa.Integer,
                      sa.ForeignKey("meetings.meeting_items.id"), nullable=True),
            sa.Column("sort_key", sa.Date, nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            schema="meetings",
        )

    if not _has_table("meetings", "meeting_attendances"):
        op.create_table(
            "meeting_attendances",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("meeting_id", sa.Integer,
                      sa.ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("person_id", sa.Integer, nullable=False, index=True),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("status IN ('present','excused')",
                               name="ck_meeting_attendances_status"),
            schema="meetings",
        )

    if not _has_table("meetings", "meeting_files"):
        op.create_table(
            "meeting_files",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("meeting_id", sa.Integer,
                      sa.ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("purpose", sa.String(20), nullable=False,
                      server_default="attachment"),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(100), nullable=False),
            sa.Column("byte_size", sa.Integer, nullable=True),
            sa.Column("data", sa.LargeBinary, nullable=False),
            sa.Column("on_agenda_mail", sa.Boolean, nullable=False,
                      server_default=sa.true()),
            sa.Column("on_report_mail", sa.Boolean, nullable=False,
                      server_default=sa.true()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("purpose IN ('attachment','sent_pdf')",
                               name="ck_meeting_files_purpose"),
            schema="meetings",
        )

    if not _has_table("meetings", "meeting_extra_recipients"):
        op.create_table(
            "meeting_extra_recipients",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("meeting_id", sa.Integer,
                      sa.ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            schema="meetings",
        )


def downgrade() -> None:
    for table in ("meeting_extra_recipients", "meeting_files", "meeting_attendances",
                  "meeting_items", "meeting_sections", "meetings"):
        op.drop_table(table, schema="meetings")
    op.execute("DROP SCHEMA IF EXISTS meetings")
    op.drop_table("organization_persons", schema="mdm")
    op.drop_table("organization_relation_type_labels", schema="mdm")
    op.drop_table("organization_relation_types", schema="mdm")
