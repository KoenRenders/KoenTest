"""The activity's description, board notes and organisers reach the reporting (#1077).

Koen wants to pull an activity report out of the reporting and forward it. The three
fields it needs exist on the activity but not in `d_activity`, so nothing — neither
the report panel nor Raakje — could ever name them.

`d_activity` is a VIEW (migration 096), so this is a replacement and not an ALTER.
`CREATE OR REPLACE VIEW` keeps the column order of the original and appends the new
ones, which is what the engine expects; a dropped-and-recreated view would break
every grant and dependency for no gain.

**The organisers arrive twice, and that is the point** (Koen, 20 September 2026):
*"Ik wil de lijst kunnen afdrukken met één rij per activiteit maar ik wil wel dat
Raakje kan vertellen wie een activiteit organiseert."*

* one TEXT column on `d_activity` — `"Jan · Marie"` — which reads like a line in a
  report and keeps a report about activities at one row per activity;
* one VIEW with its own grain, `d_activity_organiser`, one row per organiser, so a
  report can group by organiser and the assistant can answer who carries what.

The second multiplies rows, which is why it is a separate object the user chooses
rather than a column that is always there. It is joined **only to `f_activities`**,
and that is measured, not cautious: that fact carries exactly one measure and it is
`COUNT(DISTINCT activity_id)`, so the fan-out cannot inflate it. Joining the same
dimension to `f_payments` would double a `SUM(amount)` for an activity with two
organisers — silently, and in money.

The separator is the middle dot, the same one the screens use between an e-mail and
a phone number, so a reader recognises it as "and" rather than as punctuation of a
name.

Only organisers who are actually ticked as contact count — the same ones the poster
prints. An organiser who carries the activity without being published is not part of
what a report about the outside world says.

Idempotent by nature: replacing a view twice leaves the same view.
"""
from alembic import op


# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '147_2026_09_20_165122'
down_revision = '146_2026_09_20_150848'
branch_labels = None
depends_on = None

#: De view zoals migratie 096 hem schreef, plus de drie velden van #1077.
NIEUW = """
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

#: Exact de view van migratie 096 — voor de downgrade.
OUD = """
CREATE OR REPLACE VIEW reporting.d_activity AS
SELECT
    a.tenant_id,
    a.id                                        AS activity_id,
    a.name                                      AS activity_name,
    COALESCE(a.location, 'Onbekend')            AS location,
    a.is_cancelled,
    a.members_only,
    fd.first_date,
    EXTRACT(YEAR FROM fd.first_date)::int       AS activity_year
FROM activities.activities a
LEFT JOIN LATERAL (
    SELECT MIN(ad.start_date) AS first_date
    FROM activities.activity_dates ad
    WHERE ad.activity_id = a.id AND ad.deleted_at IS NULL
) fd ON TRUE
WHERE a.deleted_at IS NULL
"""


#: Eén rij per organisator (#1077). Een eigen korrel, naast de samengevoegde
#: kolom hierboven — Koen wil de lijst kunnen afdrukken met één rij per activiteit
#: én Raakje kunnen vragen wie iets organiseert. Wie het object niet in zijn
#: rapport zet, merkt van deze view niets.
#:
#: `organiser_id` is de sleutel en niet `person_id`: dezelfde persoon trekt
#: meerdere activiteiten, dus alleen de rij zelf is uniek.
ORGANISATOR = """
CREATE OR REPLACE VIEW reporting.d_activity_organiser AS
SELECT
    o.tenant_id,
    o.id                                        AS organiser_id,
    o.activity_id,
    o.person_id,
    TRIM(CONCAT_WS(' ', p.first_name, p.last_name)) AS organiser_name
FROM activities.activity_organisers o
JOIN mdm.persons p ON p.id = o.person_id AND p.deleted_at IS NULL
"""


#: Elke weergave in `reporting` draagt een COMMENT dat zegt wat ze UITSLUIT — een
#: poort toetst dat (`test_reporting_schema_gate.py`). Wie een rapport leest moet
#: kunnen weten wat er niet in zit zonder de view te openen.
COMMENTAAR = (
    "COMMENT ON VIEW reporting.d_activity_organiser IS "
    "'Eén rij per organisator van een activiteit. Sluit uit: organisatoren "
    "waarvan de persoon verwijderd is. Bevat OOK wie niet als contactpersoon "
    "aangevinkt staat — de samengevoegde kolom op d_activity doet dat niet, want "
    "die zegt wat er op de affiche komt.'"
)


def upgrade() -> None:
    op.execute(NIEUW)
    op.execute(ORGANISATOR)
    op.execute(COMMENTAAR)


def downgrade() -> None:
    """Terug naar de view van migratie 096.

    Kolommen laten vallen uit een view kan niet met REPLACE — Postgres weigert een
    vervanging die kolommen weghaalt — dus de view wordt eerst geschrapt. Wie iets
    op deze view gebouwd heeft, verliest dat; er staat vandaag niets anders op dan
    de rapportage-engine zelf, die haar per query samenstelt.
    """
    op.execute("DROP VIEW IF EXISTS reporting.d_activity_organiser CASCADE")
    op.execute("DROP VIEW IF EXISTS reporting.d_activity CASCADE")
    op.execute(OUD)
