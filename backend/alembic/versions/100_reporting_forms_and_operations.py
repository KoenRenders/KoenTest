"""Reporting phase 5 (#841): the remaining facts.

Three facts and one dimension, additive on top of the star of #832.

Question 8 of CR-06 §3 — *who are our members: age groups, municipality, household
size* — names its fact as "memberships (persons)", and that is a grain the star
did not have: `f_memberships` is one row per household per year, and an age group
belongs to a person. Hence `f_membership_persons`, one row per person per
membership year. Questions 9 and 10 need `f_form_submissions` and `f_operations`.

**`f_operations` is a union over three domains** — the workbench, the mail log and
the payments — and that is exactly the shape a reporting view is for. Each of
those domains keeps its own table and its own rules; the view reads all three and
gives them one grain, one age and one label. The dependency stays one-way: the
reporting domain reads everybody, nobody reads the reporting domain.

**No names, no addresses, no e-mail.** A submission carries whether it had a
contact, never who; an operation carries what kind of item it is and how old, plus
the internal id to reach the record. Same rule as in #832 (CR-06 §7.3), and the
same gate keeps it honest.

The tables behind these views carry no `deleted_at`: forms, submissions, tasks and
the mail log are not soft-deletable in this code base. The view comments say so,
so a reader does not go looking for a filter that cannot exist.
"""
from alembic import op

revision = "100"
down_revision = "099"
branch_labels = None
depends_on = None


# One row per person per membership year — the grain question 8 asks for. A person
# who belongs to two households in the same year appears ONCE, under the lowest
# household id: "how many members do we have" must not count anybody twice, and
# picking deterministically beats picking at random.
#
# Counting rows is therefore counting people, which is what makes the measure
# additive — and additivity is what lets the small-cell threshold merge groups
# without the merged row becoming a lie.
F_MEMBERSHIP_PERSONS = """
CREATE OR REPLACE VIEW reporting.f_membership_persons AS
SELECT DISTINCT ON (ms.tenant_id, mp.person_id, ms.year)
    ms.tenant_id,
    mp.person_id,
    ms.member_id                                AS household_id,
    ms.year,
    ms.membership_id
FROM (
    SELECT tenant_id, member_id, year, MIN(id) AS membership_id
    FROM membership.memberships
    WHERE deleted_at IS NULL
    GROUP BY tenant_id, member_id, year
) ms
JOIN mdm.member_persons mp
  ON mp.member_id = ms.member_id AND mp.tenant_id = ms.tenant_id
 AND mp.deleted_at IS NULL
JOIN mdm.persons p
  ON p.id = mp.person_id AND p.deleted_at IS NULL AND p.superseded_by_id IS NULL
ORDER BY ms.tenant_id, mp.person_id, ms.year, ms.member_id
"""

D_FORM = """
CREATE OR REPLACE VIEW reporting.d_form AS
SELECT
    f.tenant_id,
    f.id                                        AS form_id,
    f.title                                     AS form_name,
    f.status                                    AS form_status,
    CASE f.status
        WHEN 'draft' THEN 'Concept'
        WHEN 'open' THEN 'Open'
        WHEN 'closed' THEN 'Gesloten'
        ELSE f.status
    END                                         AS form_status_label,
    CASE WHEN f.is_anonymous THEN 'Ja' ELSE 'Nee' END AS is_anonymous_label
FROM form.forms f
"""

# One row per submission. The answers themselves stay out: they are free text a
# person typed, and a report counts submissions — the form screen is where you
# read what somebody wrote.
F_FORM_SUBMISSIONS = """
CREATE OR REPLACE VIEW reporting.f_form_submissions AS
SELECT
    s.tenant_id,
    s.id                                        AS submission_id,
    s.form_id,
    s.submitted_at,
    s.submitted_at::date                        AS date_key,
    (s.updated_at IS NOT NULL)                  AS was_edited,
    (s.submitter_email IS NOT NULL AND s.submitter_email <> '') AS has_contact,
    COALESCE(a.answer_count, 0)                 AS answer_count
FROM form.form_submissions s
LEFT JOIN LATERAL (
    SELECT COUNT(*)::int AS answer_count
    FROM form.form_submission_answers fa
    WHERE fa.submission_id = s.id
) a ON TRUE
"""

# One row per open item, over three domains. `subject_type` and `subject_id` are
# what the panel turns into a link; they are internal ids and carry no person.
#
# `item_id` is prefixed with the leg it came from, and that is not decoration: a
# task with id 1 and a mail with id 1 are two different items, and without the
# prefix a COUNT(DISTINCT item_id) folds them into one. The measure reported three
# open items where there were four, and only a test with known numbers caught it.
F_OPERATIONS = """
CREATE OR REPLACE VIEW reporting.f_operations AS
SELECT
    x.*,
    (CURRENT_DATE - x.created_at::date)         AS age_days,
    CASE
        WHEN CURRENT_DATE - x.created_at::date <= 7 THEN '0-7 dagen'
        WHEN CURRENT_DATE - x.created_at::date <= 30 THEN '8-30 dagen'
        WHEN CURRENT_DATE - x.created_at::date <= 90 THEN '31-90 dagen'
        ELSE 'meer dan 90 dagen'
    END                                         AS age_bucket,
    x.created_at::date                          AS date_key
FROM (
    SELECT
        t.tenant_id,
        'task'                                  AS kind,
        'Open taak'                             AS kind_label,
        t.kind                                  AS detail,
        t.subject_type,
        t.subject_id::text                      AS subject_id,
        'task:' || t.id::text                   AS item_id,
        t.created_at
    FROM workflow.workflow_tasks t
    WHERE t.status = 'open'

    UNION ALL

    SELECT
        m.tenant_id,
        'mail_failed'                           AS kind,
        'Mislukte e-mail'                       AS kind_label,
        m.email_type                            AS detail,
        'email'                                 AS subject_type,
        m.id::text                              AS subject_id,
        'mail:' || m.id::text                   AS item_id,
        m.created_at
    FROM mail.email_log m
    WHERE m.status <> 'sent'

    UNION ALL

    SELECT
        p.tenant_id,
        'payment_open'                          AS kind,
        'Openstaande betaling'                  AS kind_label,
        p.payable_type                          AS detail,
        'payment'                               AS subject_type,
        p.id                                    AS subject_id,
        'payment:' || p.id                      AS item_id,
        p.created_at
    FROM payment.payment_records p
    WHERE p.deleted_at IS NULL AND p.status = 'pending'
) x
"""

COMMENTS = {
    "f_membership_persons": (
        "Feit lid-persoon, een rij per persoon per lidmaatschapsjaar. Een persoon "
        "in twee gezinnen telt één keer, onder het laagste gezin. Soft-deleted "
        "lidmaatschappen, gezinskoppelingen en personen uitgesloten, net als "
        "samengevoegde personen."
    ),
    "d_form": (
        "Formulier, een rij per formulier. `form.forms` kent geen soft delete, "
        "dus er valt niets uit te sluiten."
    ),
    "f_form_submissions": (
        "Feit formulierinzending, een rij per inzending. GEEN naam, e-mailadres "
        "of antwoordtekst (CR-06 §7.3) — enkel of er een contact bij zat en "
        "hoeveel antwoorden er zijn. `form.form_submissions` kent geen soft "
        "delete."
    ),
    "f_operations": (
        "Feit operaties, een rij per open item. Unie over drie domeinen: open "
        "werkbanktaken, mislukte e-mails en betalingen in afwachting. Alleen de "
        "betalingen kennen soft delete; die zijn uitgesloten. Ouderdom wordt "
        "tegen CURRENT_DATE gemeten, dus deze weergave antwoordt morgen anders — "
        "dat is de bedoeling van een werkvoorraad."
    ),
}

VIEWS = [
    ("f_membership_persons", F_MEMBERSHIP_PERSONS),
    ("d_form", D_FORM),
    ("f_form_submissions", F_FORM_SUBMISSIONS),
    ("f_operations", F_OPERATIONS),
]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS reporting")
    for name, sql in VIEWS:
        op.execute(f"DROP VIEW IF EXISTS reporting.{name} CASCADE")
        op.execute(sql)
        comment = COMMENTS[name].replace("'", "''")
        op.execute(f"COMMENT ON VIEW reporting.{name} IS '{comment}'")


def downgrade() -> None:
    for name, _sql in reversed(VIEWS):
        op.execute(f"DROP VIEW IF EXISTS reporting.{name} CASCADE")
