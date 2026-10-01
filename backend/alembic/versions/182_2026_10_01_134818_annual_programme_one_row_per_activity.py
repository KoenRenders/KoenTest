"""The annual programme lists every activity once (#1439, after #1428).

Koen, validating #1428 on HDEV: a monthly bike ride or a weekend stood in the
programme once per date. He wants every activity **once**, with its first date
in the year and its time, and — adjusted the same day — one cell "Datums" with
all its dates in that year, joined like the organisers.

**A view per activity and year, beside `f_activity_dates`.** "The first date in
the year" depends on the year, so the grain is one row per activity per year in
which it has a date — not one per activity, which would have to choose a year
before the filter does. The date fact stays: it answers "how many evenings",
which this one cannot. "Datum" (the first) and "Maand" keep the sort.

**Which year a date belongs to: the year of its start day.** Measured against
the two ways an activity crosses New Year:

* dates in two years (a series from November to February) — the activity is a
  row in **each** year, with the dates of that year: first, last and count;
* one date that runs across New Year (31 December to 2 January, one row with an
  end date) — it belongs to the year it **starts**, and its cell reads
  "31-12-2026–02-01-2027". It does not reappear in the next year, where no date
  starts.

**"Datums"**, the cell: every date of the activity in that year, in order, with
the middle dot the organiser column uses (migration 147), in the `DD-MM-YYYY`
the panel shows for a date. A date with an end date reads "start–end". The
**time is added only when it differs between the dates** of that year: when they
all start at 19:30 — or none has a time — "Uur" already says it, and repeating
it on every date is noise. When they differ, each date that has a time carries
it ("05-03-2027 19:30"); a date without one carries none.

The shipped report is repointed in place (by its `builtin_key`, every tenant):
same name, its columns now on this fact, plus "Datums".
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
revision = "182_2026_10_01_134818"
down_revision = "181_2026_10_01_080312"
branch_labels = None
depends_on = None


F_ACTIVITY_YEARS = """
CREATE OR REPLACE VIEW reporting.f_activity_years AS
WITH d AS (
    SELECT
        a.tenant_id,
        ad.id,
        ad.activity_id,
        ad.start_date,
        ad.end_date,
        ad.start_time,
        EXTRACT(YEAR FROM ad.start_date)::int       AS year
    FROM activities.activity_dates ad
    JOIN activities.activities a
      ON a.id = ad.activity_id AND a.deleted_at IS NULL
    WHERE ad.deleted_at IS NULL
),
t AS (
    SELECT
        d.*,
        -- Do the dates of this activity in this year start at different times?
        MIN(COALESCE(to_char(start_time, 'HH24:MI'), '')) OVER w
            <> MAX(COALESCE(to_char(start_time, 'HH24:MI'), '')) OVER w AS times_differ,
        ROW_NUMBER() OVER (w ORDER BY start_date, start_time NULLS LAST, id) AS n
    FROM d
    WINDOW w AS (PARTITION BY activity_id, year)
)
SELECT
    t.tenant_id,
    t.activity_id,
    t.year,
    MIN(t.start_date)                           AS first_date,
    MIN(t.start_time) FILTER (WHERE t.n = 1)    AS first_time,
    COALESCE(to_char(MIN(t.start_time) FILTER (WHERE t.n = 1), 'HH24:MI'), '')
                                                AS first_time_label,
    string_agg(
        to_char(t.start_date, 'DD-MM-YYYY')
        || CASE WHEN t.end_date > t.start_date
                THEN '–' || to_char(t.end_date, 'DD-MM-YYYY') ELSE '' END
        || CASE WHEN t.times_differ AND t.start_time IS NOT NULL
                THEN ' ' || to_char(t.start_time, 'HH24:MI') ELSE '' END,
        ' · ' ORDER BY t.n)                     AS dates_label
FROM t
GROUP BY t.tenant_id, t.activity_id, t.year
"""

F_ACTIVITY_YEARS_COMMENT = (
    "Eén rij per activiteit per jaar waarin ze een datum heeft — de korrel van het "
    "jaarprogramma. Een datum telt in het jaar van haar startdag. Sluit uit: "
    "verwijderde datums en verwijderde activiteiten. Bevat OOK concepten en "
    "geannuleerde activiteiten."
)

SELECTION = {
    "objects": [
        "year_first_date_month",
        "year_first_date_day",
        "year_first_time",
        "year_dates",
        "activity_target_audience",
        "activity",
        "activity_location",
        "activity_organisers",
        "activity_board_notes",
        "activity_status",
    ],
    "filters": [
        {"object": "year_first_date_year", "operator": "eq", "values": [], "symbolic": "dit_jaar"}
    ],
    "sort": [],
    "layout": "detail",
    "pivot_column": "",
}
DESCRIPTION = (
    "Elke activiteit van het gekozen jaar, één keer: haar eerste datum met uur, al "
    "haar datums in dat jaar, het doelpubliek, de locatie, de organisatoren, de "
    "interne notities en de status — ook de concepten, zodat je ziet wat nog "
    "gepubliceerd moet worden."
)

#: What migration 181 seeded, for the downgrade.
SELECTION_181 = {
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
        {"object": "activity_date_year", "operator": "eq", "values": [], "symbolic": "dit_jaar"}
    ],
    "sort": [],
    "layout": "detail",
    "pivot_column": "",
}
DESCRIPTION_181 = (
    "Elke datum van elke activiteit in het gekozen jaar, met uur, doelpubliek, "
    "locatie, organisatoren, de interne notities en de status — ook de "
    "concepten, zodat je ziet wat nog gepubliceerd moet worden."
)


def _repoint(selection: dict, description: str) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE reporting.saved_reports SET selection = CAST(:s AS json), description = :d "
            "WHERE builtin_key = 'annual_programme'"
        ),
        {"s": json.dumps(selection), "d": description},
    )


def upgrade() -> None:
    op.execute(F_ACTIVITY_YEARS)
    comment = F_ACTIVITY_YEARS_COMMENT.replace("'", "''")
    op.execute(f"COMMENT ON VIEW reporting.f_activity_years IS '{comment}'")
    _repoint(SELECTION, DESCRIPTION)


def downgrade() -> None:
    """Back to one row per date: the shipped report as 181 seeded it, and no view.

    The report is restored by its key, so a board member's change to the shipped
    report is lost both ways; a copy saved under another name that uses the new
    objects breaks, as with every downgrade that removes objects.
    """
    _repoint(SELECTION_181, DESCRIPTION_181)
    op.execute("DROP VIEW IF EXISTS reporting.f_activity_years")
