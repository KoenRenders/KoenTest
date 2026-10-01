"""The annual programme as a shipped report (#1428, part B).

The board plans its year in a spreadsheet: one line per date, with month, time,
audience, activity, location, organisers and its own notes. Every one of those
already lives on the activity, but the reporting could not list them **per date**:
`f_activities` is one row per activity and folds its dates into a first and a last
day, so a course of six evenings was one line. The programme needs six.

So this adds a fact with that grain, `f_activity_dates`, and nothing else new:

* the fact is one row per date of an activity, soft-deleted dates and activities
  excluded. Its own columns are the day and the start time; everything else comes
  from `d_activity` through the ordinary join, so a date carries the same name,
  location, organisers and notes as the activity it belongs to;
* `d_activity` gains the two fields of part A as **labels**, joined from their
  label tables in Dutch the way migration 154 does for gender and relation — the
  status ("Concept", "Gepubliceerd") and the target audience, empty when nobody
  filled it in. A report shows the word, never the code;
* one shipped report, "Jaarprogramma", seeded per UNIT tenant like the others
  (migration 103), filtered on this year by the same symbolic value migration 109
  uses, so it is the current year on the day it is opened.

Drafts are deliberately IN the report: the programme is where the board sees what
is still to be published, and the status column says which.

`d_activity` is a view, so this is a replacement (migration 147 explains why
`CREATE OR REPLACE` and not a drop): the new columns are appended.
"""

import json

import sqlalchemy as sa
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
revision = "181_2026_10_01_080312"
down_revision = "180_2026_10_01_071520"
branch_labels = None
depends_on = None


F_ACTIVITY_DATES = """
CREATE OR REPLACE VIEW reporting.f_activity_dates AS
SELECT
    a.tenant_id,
    ad.id                                       AS activity_date_id,
    ad.activity_id,
    ad.start_date                               AS date_key,
    ad.start_time,
    COALESCE(to_char(ad.start_time, 'HH24:MI'), '') AS start_time_label
FROM activities.activity_dates ad
JOIN activities.activities a
  ON a.id = ad.activity_id AND a.deleted_at IS NULL
WHERE ad.deleted_at IS NULL
"""

F_ACTIVITY_DATES_COMMENT = (
    "Eén rij per datum van een activiteit — de korrel van het jaarprogramma. "
    "Sluit uit: verwijderde datums en datums van verwijderde activiteiten. Bevat "
    "OOK concepten en geannuleerde activiteiten; de status en Geannuleerd op "
    "d_activity zeggen welke."
)

#: The view of migration 147, with status and target audience appended.
D_ACTIVITY = """
CREATE OR REPLACE VIEW reporting.d_activity AS
SELECT
    a.tenant_id,
    a.id                                        AS activity_id,
    a.name                                      AS activity_name,
    COALESCE(a.location, 'Onbekend')            AS location,
    a.is_cancelled,
    a.members_only,
    fd.first_date,
    EXTRACT(YEAR FROM fd.first_date)::int       AS activity_year,
    a.description                               AS activity_description,
    a.board_notes                               AS activity_board_notes,
    org.organisers                              AS activity_organisers,
    COALESCE(sl.value, a.status)                AS status_label,
    tl.value                                    AS target_audience_label
FROM activities.activities a
LEFT JOIN LATERAL (
    SELECT MIN(ad.start_date) AS first_date
    FROM activities.activity_dates ad
    WHERE ad.activity_id = a.id AND ad.deleted_at IS NULL
) fd ON TRUE
LEFT JOIN LATERAL (
    SELECT string_agg(
               TRIM(CONCAT_WS(' ', p.first_name, p.last_name)), ' · '
               ORDER BY o.sort_order, o.id) AS organisers
    FROM activities.activity_organisers o
    JOIN mdm.persons p ON p.id = o.person_id AND p.deleted_at IS NULL
    WHERE o.activity_id = a.id AND o.is_contact
) org ON TRUE
LEFT JOIN activities.activity_status_labels sl
       ON sl.code = a.status AND sl.language = 'nl'
LEFT JOIN activities.target_audience_labels tl
       ON tl.code = a.target_audience AND tl.language = 'nl'
WHERE a.deleted_at IS NULL
"""

#: Exactly the view of migration 147 — for the downgrade.
D_ACTIVITY_147 = """
CREATE OR REPLACE VIEW reporting.d_activity AS
SELECT
    a.tenant_id,
    a.id                                        AS activity_id,
    a.name                                      AS activity_name,
    COALESCE(a.location, 'Onbekend')            AS location,
    a.is_cancelled,
    a.members_only,
    fd.first_date,
    EXTRACT(YEAR FROM fd.first_date)::int       AS activity_year,
    a.description                               AS activity_description,
    a.board_notes                               AS activity_board_notes,
    org.organisers                              AS activity_organisers
FROM activities.activities a
LEFT JOIN LATERAL (
    SELECT MIN(ad.start_date) AS first_date
    FROM activities.activity_dates ad
    WHERE ad.activity_id = a.id AND ad.deleted_at IS NULL
) fd ON TRUE
LEFT JOIN LATERAL (
    SELECT string_agg(
               TRIM(CONCAT_WS(' ', p.first_name, p.last_name)), ' · '
               ORDER BY o.sort_order, o.id) AS organisers
    FROM activities.activity_organisers o
    JOIN mdm.persons p ON p.id = o.person_id AND p.deleted_at IS NULL
    WHERE o.activity_id = a.id AND o.is_contact
) org ON TRUE
WHERE a.deleted_at IS NULL
"""

#: The comment of migration 096; a dropped view loses it, so the downgrade sets it.
D_ACTIVITY_COMMENT = (
    "Activiteit, een rij per activiteit. Soft-deleted activiteiten uitgesloten. "
    "Onderdeel en product staan NIET hier maar op f_registrations: ze liggen "
    "fijner en zouden elke maat op activiteitniveau vermenigvuldigen."
)

ANNUAL_PROGRAMME = {
    "key": "annual_programme",
    "name": "Jaarprogramma",
    "description": (
        "Elke datum van elke activiteit in het gekozen jaar, met uur, doelpubliek, "
        "locatie, organisatoren, de interne notities en de status — ook de "
        "concepten, zodat je ziet wat nog gepubliceerd moet worden."
    ),
    "selection": {
        "objects": [
            "activity_date_month",
            "activity_date_day",
            "activity_date_time",
            "activity_target_audience",
            "activity",
            "activity_location",
            "activity_organisers",
            "activity_board_notes",
            "activity_status",
        ],
        "filters": [
            {
                "object": "activity_date_year",
                "operator": "eq",
                "values": [],
                "symbolic": "dit_jaar",
            }
        ],
        "sort": [],
        "layout": "detail",
        "pivot_column": "",
    },
}


def _comment(view: str, text: str) -> None:
    op.execute(f"COMMENT ON VIEW reporting.{view} IS '{text.replace(chr(39), chr(39) * 2)}'")


def upgrade() -> None:
    op.execute(D_ACTIVITY)
    op.execute(F_ACTIVITY_DATES)
    _comment("f_activity_dates", F_ACTIVITY_DATES_COMMENT)

    bind = op.get_bind()
    tenants = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT id FROM mdm.organizations "
                "WHERE org_type = 'UNIT' AND deleted_at IS NULL ORDER BY id"
            )
        )
    ]
    for tenant_id in tenants:
        bind.execute(
            sa.text(
                "INSERT INTO reporting.saved_reports "
                "  (tenant_id, name, description, selection, is_shared, builtin_key) "
                "SELECT :t, :n, :d, CAST(:s AS json), TRUE, :k "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM reporting.saved_reports "
                "   WHERE tenant_id = :t AND builtin_key = :k AND deleted_at IS NULL)"
            ),
            {
                "t": tenant_id,
                "n": ANNUAL_PROGRAMME["name"],
                "d": ANNUAL_PROGRAMME["description"],
                "s": json.dumps(ANNUAL_PROGRAMME["selection"]),
                "k": ANNUAL_PROGRAMME["key"],
            },
        )


def downgrade() -> None:
    """Back to the reporting of migration 180, schema and seeded rows alike.

    The report is deleted, also where a board member changed it — it is the
    shipped one, recognised by its key. A copy saved under another name stays, and
    breaks on its first run because its objects are gone; that is the same for
    every shipped report a downgrade removes.

    Dropping columns from a view cannot be done with REPLACE, so `d_activity` is
    dropped and rebuilt as 147 left it, with the comment 096 gave it.
    """
    op.execute(
        f"DELETE FROM reporting.saved_reports WHERE builtin_key = '{ANNUAL_PROGRAMME['key']}'"
    )
    op.execute("DROP VIEW IF EXISTS reporting.f_activity_dates")
    op.execute("DROP VIEW IF EXISTS reporting.d_activity")
    op.execute(D_ACTIVITY_147)
    _comment("d_activity", D_ACTIVITY_COMMENT)
