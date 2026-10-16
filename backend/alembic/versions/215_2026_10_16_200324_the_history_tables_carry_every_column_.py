"""the history tables carry every column of what they log

#1885: a change reached Wijzigingen only through links kept by hand, and the
history tables had fallen behind their models — measured on 15 October 2026:
an activity's history kept its name and nothing else of eleven columns, a
component's five of sixteen. Koen, 15 October 2026: every column of every model
Wijzigingen reads is logged, except an uploaded document's content and a purely
technical moment ("alles loggen behalve het technische moment"); the national
member number (`ExternalNumber`) is logged too.

So every history table gains the columns its model has and it lacks, and the
member number gets a history table of its own. A history table carries no
foreign key (CR-12 §F4: it must outlive what it names), so these are plain
columns, all nullable: the rows written before this migration hold nothing in
them, and that is what they knew.

The registration too, with Koen's two answers of 16 October 2026: its
`registered_at` is logged ("11 ja"), and the secret of its answer link is not
("3a, de sleutel moet niet in wijzigingen terecht komen") — nor the key of the
form it came from (#1987), the token's random part, a secret of the same kind.

Idempotent: a column or a table is made only when it is not there.
"""

from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
# `repr` with double quotes (#781): the generated file must already be what
# `ruff format` writes, or every new migration turns CI red. A `repr` still, not
# a bare string, because `down_revision` is a tuple for a merge and None for the
# first migration.
revision = "215_2026_10_16_200324"
down_revision = "214_2026_10_16_170934"
branch_labels = None
depends_on = None

#: table → the columns it gains, with their type.
COLUMNS: dict[str, list[tuple[str, str]]] = {
    "mdm.person_history": [("superseded_by_id", "INTEGER")],
    "mdm.address_history": [("organization_id", "INTEGER")],
    "mdm.contact_detail_history": [("organization_id", "INTEGER")],
    "payment.payment_record_history": [("structured_communication", "VARCHAR(20)")],
    "activities.activity_history": [
        ("slug", "VARCHAR(255)"),
        ("location", "VARCHAR(255)"),
        ("description", "TEXT"),
        ("poster_url", "TEXT"),
        ("is_cancelled", "BOOLEAN"),
        ("members_only", "BOOLEAN"),
        ("board_notes", "TEXT"),
        ("status", "VARCHAR(20)"),
        ("target_audience", "VARCHAR(20)"),
        ("copied_from_id", "INTEGER"),
    ],
    "activities.activity_date_history": [("start_time", "TIME"), ("end_time", "TIME")],
    "activities.component_history": [
        ("description", "TEXT"),
        ("external_register_url", "VARCHAR(500)"),
        ("external_registrations_url", "VARCHAR(500)"),
        ("info_url", "VARCHAR(500)"),
        ("registration_type_code", "VARCHAR(10)"),
        ("max_participants", "INTEGER"),
        ("registration_closes_on", "DATE"),
        ("is_free", "BOOLEAN"),
        ("team_name_required", "BOOLEAN"),
        ("form_id", "INTEGER"),
    ],
    "activities.registration_history": [
        ("activity_id", "INTEGER"),
        ("person_id", "INTEGER"),
        ("registered_at", "TIMESTAMP WITH TIME ZONE"),
        ("registration_type", "VARCHAR(10)"),
        ("team_name", "VARCHAR(200)"),
        ("payment_method", "VARCHAR(20)"),
        ("component_id", "INTEGER"),
        ("form_submission_id", "INTEGER"),
    ],
    "activities.product_history": [
        ("is_free", "BOOLEAN"),
        ("pay_on_site", "BOOLEAN"),
        ("is_active", "BOOLEAN"),
        ("max_participants", "INTEGER"),
    ],
}


def upgrade() -> None:
    for table, columns in COLUMNS.items():
        for name, kind in columns:
            op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {kind}")
    op.execute(
        "CREATE TABLE IF NOT EXISTS mdm.external_number_history ("
        " id SERIAL PRIMARY KEY,"
        " tenant_id INTEGER NOT NULL,"
        " external_number_id INTEGER NOT NULL,"
        " person_id INTEGER,"
        " number_source VARCHAR(50),"
        " external_id VARCHAR(50),"
        " operation VARCHAR(10) NOT NULL,"
        " action VARCHAR(40) NOT NULL,"
        " source VARCHAR(30) NOT NULL,"
        " actor VARCHAR(255),"
        " recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now())"
    )
    for column in ("tenant_id", "external_number_id", "recorded_at"):
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_mdm_external_number_history_{column} "
            f"ON mdm.external_number_history ({column})"
        )


def downgrade() -> None:
    # Schema and data: the columns and the member number's history go, with what
    # was written into them since. The rows of before keep what they had.
    op.execute("DROP TABLE IF EXISTS mdm.external_number_history")
    for table, columns in COLUMNS.items():
        for name, _kind in columns:
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {name}")
