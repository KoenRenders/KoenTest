"""The joined organiser column names every organiser, not only the contacts (#1441).

Since #1077 (migration 147) `d_activity.activity_organisers` joined only the
organisers ticked as contact: it was meant to say what the poster prints. In the
annual programme (#1428, #1439) that column became the list of who carries an
activity, and there it was nearly always empty — measured on PROD: 38 activities
have organisers, the view filled the column for 1. Ticking "contact" is a choice
about the poster, not about who organises. Koen, 1 October 2026: drop the filter.

What stays: the order (`sort_order`, then `id`) and the middle dot between names.
What changes: nothing else in the view; the replacement keeps every column of
migration 181 in its place.

`d_activity_organiser`, one row per organiser, already held everyone; its view
comment contrasted itself with this column and is rewritten to say they now
agree on who is in it.

Idempotent by nature: replacing a view twice leaves the same view. The downgrade
puts the contact filter back, which is a schema change only — no data moves.
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
revision = "183_2026_10_01_150044"
down_revision = "182_2026_10_01_134818"
branch_labels = None
depends_on = None


def _d_activity(organiser_filter: str) -> str:
    """The view of migration 181; only the organiser filter differs."""
    return f"""
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
    WHERE o.activity_id = a.id{organiser_filter}
) org ON TRUE
LEFT JOIN activities.activity_status_labels sl
       ON sl.code = a.status AND sl.language = 'nl'
LEFT JOIN activities.target_audience_labels tl
       ON tl.code = a.target_audience AND tl.language = 'nl'
WHERE a.deleted_at IS NULL
"""


ORGANISER_COMMENT = (
    "Eén rij per organisator van een activiteit. Sluit uit: organisatoren "
    "waarvan de persoon verwijderd is. Bevat iedereen, ook wie niet als "
    "contactpersoon aangevinkt staat — net als de samengevoegde kolom op "
    "d_activity (#1441)."
)

#: The comment of migration 147, for the downgrade.
ORGANISER_COMMENT_147 = (
    "Eén rij per organisator van een activiteit. Sluit uit: organisatoren "
    "waarvan de persoon verwijderd is. Bevat OOK wie niet als contactpersoon "
    "aangevinkt staat — de samengevoegde kolom op d_activity doet dat niet, want "
    "die zegt wat er op de affiche komt."
)


def _comment(text: str) -> None:
    escaped = text.replace("'", "''")
    op.execute(f"COMMENT ON VIEW reporting.d_activity_organiser IS '{escaped}'")


def upgrade() -> None:
    op.execute(_d_activity(""))
    _comment(ORGANISER_COMMENT)


def downgrade() -> None:
    op.execute(_d_activity(" AND o.is_contact"))
    _comment(ORGANISER_COMMENT_147)
