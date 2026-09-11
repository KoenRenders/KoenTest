"""Reporting (#871): the Leden measures, and the filter that had crept into a name.

Koen, looking at v2.3.0 on HDEV: *"Bij leden vind ik de measures moeilijk te
onderscheiden. In mijn beleving heb je: aantal leden (hoofdlid) en aantal leden
(personen), aantal leden en op basis van status zijn die actief of niet. Ik hoef
dus niet: aantal personen, gezinnen met lidmaatschap, aantal unieke personen…"*

**The fault underneath is that a filter had crept into the name of a measure.** A
measure answers *how many*; *which of them* is a dimension. Put the condition in
the name and the list multiplies with every new condition — and you end up with
two measures that differ only in something the reader cannot see. That is exactly
why they could not be told apart: the difference was nowhere on the screen. Same
shape as #852, where the universe promised a distinction it did not keep.

So *Nieuw*, *Vernieuwd* and *Vervallen* are gone as measures. They were never
three quantities; they are three states of the same membership, and
`d_membership_status` has held them as a dimension all along. *Actief* joins them
as a dimension. "How many active members" is now a count **with** a filter, and the
panel shows the filter.

**What was renamed, and why the grain is now in the name:**

| was | is | telt |
|---|---|---|
| Gezinnen met lidmaatschap | Aantal leden (hoofdlid) | één per gezin per jaar |
| Aantal personen | Aantal leden (personen) | personen in die gezinnen |
| Aantal leden (personen) | Aantal lidmaatschappen (personen) | één per persoon per jaar |
| Aantal unieke leden | Aantal unieke personen | elke persoon één keer, over alle jaren |
| Gezinnen (alle) | Aantal gezinnen | elk gezin, ook wie nooit lid was |
| Actieve lidmaatschappen | Aantal actieve lidmaatschappen | rijen, geen gezinnen |

**The two real distinctions were kept, and that is why this is not a clean-up.**

*All households* against *households with a membership* was the whole reason for
#848, and a household that was never a member has to stay visible. But it belongs
to the **fact** you query — `f_members` against `f_memberships` — and not to a
name, so the panel now says which population a report counts.

*Persons* against *unique persons* is real too: somebody in two membership years
counts twice or once. That is a matter of **grain**, so both names now say their
grain instead of sitting next to each other nearly identical.

**The numbers may not move.** The six dashboard tiles read their saved report since
#848 and Koen validated them against v2.2. `membership_active_count` therefore
keeps counting **rows** and was not folded into "households with an active
membership": those differ the moment a household has two active memberships, and
the tile counts rows. Only its name changed, to say so. `test_reporting_dashboard.py`
checks every tile along both roads and is the proof that only names moved.

The one saved report that used the three removed measures is rewritten here to the
status dimension — same three numbers, as rows instead of as columns.

## Betalingen en Formulieren

Koen asked whether the same doubling sits at Betalingen and Formulieren. It does,
once, and the other case is only a name.

**One real double at Betalingen.** *Openstaand* (`SUM(open_amount)`, arithmetic)
stood next to *Openstaand volgens status* (`SUM(amount)` with a status condition
baked into it). Two answers to one question, on one screen, both called
outstanding. The second is gone; the condition becomes a visible filter on
Betaalstatus.

The dashboard tile that read it keeps its number **exactly**, and that needs
saying out loud. `NOT IN ('paid', 'cancelled', 'failed')` over a closed list of
four codes is `= 'pending'`, so the tile becomes *Te betalen* filtered on
**In afwachting**. One edge moves with it: a record carrying a status that is not
in the code list counted as outstanding before and does not now. That is a
closed-world assumption, so `test_reporting_leden_measures.py` holds a gate on the
four codes being the whole set — a fifth status makes it fail rather than making a
number drift.

**Formulieren was a naming problem only.** *Aantal inzendingen* counts submissions
and *Aantal antwoorden* counts the filled **fields** inside them — one submission
with eight fields is 1 and 8. Both useful, neither name saying so. Renamed to
*Ingevulde velden*; nothing structural.

**De klasse *Betaaldetail* is opgegaan in *Betalingen*.** Ze was de enige klasse
die naar een **vorm** genoemd was in plaats van naar een onderwerp, en die splitsing
verborg precies wat ze had moeten tonen: twee objecten heetten *Soort* en twee
heetten *Te betalen*, elk paar met een andere betekenis. Binnen één klasse moesten
ze opgelost worden. Vier van die "details" bleken bovendien dezelfde uitdrukking als
een bestaande dimensie — alleen hun soort verschilde — en zijn weg.

Bij het oplossen bleek de botsing erger dan ze leek: *Waarvoor* en *Soort* noemden
elkáárs kolom. De dimensie *Waarvoor* stond op `payable_type_label` (lidgeld of
activiteit), terwijl het detail dat *Soort* noemde; de dimensie *Soort* stond op
`record_type_label`, dat het detail *Type* noemde. Het zijn dus de **dimensies**
die hernoemd zijn en niet de details: de details dragen de koppen van de bestaande
betalingenexport, en die pariteit is precies het punt van #841 punt 4. *Waarvoor*
wordt *Soort*, *Soort* wordt *Type*, *Betaalstatus* wordt *Status*.

Wat overblijft aan gelijke namen is *Te betalen* en *Betaald*, elk één keer als
maat en één keer als detail — dezelfde grootheid op een andere korrel, en het
soortsymbool (Σ tegenover ·) zegt dat al.

**En *Ontvangen* heet *Betaald*.** Er verandert niets aan de berekening; de rij
*Te betalen · Betaald · Openstaand* legt zichzelf uit, omdat het derde getal
zichtbaar het verschil van de eerste twee is. De omschrijving van *Openstaand* zei
letterlijk "te betalen min ontvangen" en is meegegaan — dat is het soort restje dat
een hernoeming achterlaat.

**New: *Aantal formulieren*.** With the trap of #848 in mind: counted on a new
`f_forms` fact and not on the submissions, because a form **without** submissions
would silently vanish there — and "which form is open and gets nothing" is exactly
a question a board member asks. A test seeds a form with no submissions.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "113"
down_revision = "112"
branch_labels = None
depends_on = None


# The payments listing pointed at four "details" that were the same expression as
# an existing dimension — the collision the merged class made visible (#871). Same
# columns, same order, same numbers; only the keys change.
PAYMENTS_LIST = {
    "objects": [
        "payment_payable_label", "payment_payable_type", "payment_type",
        "payment_method", "payment_status", "payment_ogm",
        "payment_due", "payment_received", "payment_balance",
        "payment_paid_on", "payment_note",
    ],
    "filters": [],
    "sort": [],
    "layout": "detail",
    "pivot_column": "",
}


# One row per form, including the ones nobody filled in. That is the entire reason
# this fact exists next to the submissions (#871).
F_FORMS = """
CREATE OR REPLACE VIEW reporting.f_forms AS
SELECT
    f.tenant_id,
    f.id                                        AS form_id,
    f.created_at,
    f.created_at::date                          AS date_key
FROM form.forms f
"""

F_FORMS_COMMENT = (
    "Feit formulier, een rij per formulier — ook een zonder inzendingen. Op het "
    "inzendingenfeit verdwijnt zo'n formulier stilzwijgend uit een telling, en "
    "\'welk formulier staat open en krijgt niets binnen\' is juist een "
    "bestuurdersvraag. Dezelfde val als bij de activiteiten in #848."
)

# The tile summed `amount` where the status is not paid, cancelled or failed. Over
# the closed list of four codes that is exactly "pending", so the same number now
# comes from a measure plus a filter you can see.
DASHBOARD_OUTSTANDING = {
    "objects": ["payment_amount"],
    "filters": [{"object": "payment_status", "operator": "eq",
                 "values": ["In afwachting"]}],
    "sort": [], "layout": "table", "pivot_column": "",
}


# Same question, same numbers: what used to be three measures side by side is now
# one count grouped by the status.
#
# The count is `membership_count` and NOT `membership_households`, and that
# difference is the whole subtlety of this conversion. "Aantal leden (hoofdlid)"
# sums `is_member`, and a LAPSED household has no membership that year — so it
# would correctly report zero lapsed households, which is the one number question
# 2 exists to produce. Households in the grid is a different quantity, not the same
# one under a condition.
#
# One thing does look different on screen, and it is worth knowing before somebody
# reports it: a status with nobody in it now has NO row, where the three measures
# showed a literal 0. That is what grouping does, and adding an empty row back
# would mean inventing a row the data does not have.
MEMBERSHIP_FLOW = {
    "objects": ["membership_year", "membership_status", "membership_count"],
    "filters": [],
    "sort": [{"object": "membership_year", "direction": "desc"}],
    "layout": "table",
    "pivot_column": "",
}


def upgrade() -> None:
    op.execute(F_FORMS)
    op.execute(f"COMMENT ON VIEW reporting.f_forms IS "
               f"'{F_FORMS_COMMENT.replace(chr(39), chr(39) * 2)}'")

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE reporting.saved_reports SET selection = CAST(:s AS json) "
            "WHERE builtin_key = 'payments_list' "
            "  AND selection::text LIKE '%payment_kind_label%'"
        ),
        {"s": json.dumps(PAYMENTS_LIST)},
    )
    bind.execute(
        sa.text(
            "UPDATE reporting.saved_reports SET selection = CAST(:s AS json) "
            "WHERE builtin_key = 'dashboard_outstanding' "
            "  AND selection::text LIKE '%payment_outstanding%'"
        ),
        {"s": json.dumps(DASHBOARD_OUTSTANDING)},
    )
    # Only rows that still carry the removed keys, so a report a board member has
    # already adjusted is left alone.
    bind.execute(
        sa.text(
            "UPDATE reporting.saved_reports SET selection = CAST(:s AS json) "
            "WHERE builtin_key = 'membership_flow_per_year' "
            "  AND selection::text LIKE '%membership_new%'"
        ),
        {"s": json.dumps(MEMBERSHIP_FLOW)},
    )

    # Anything a person built themselves that names a removed measure would fail
    # to load. There is no silent repair for that — the selection asked for
    # something that no longer exists — so they are reported rather than rewritten.
    resterend = bind.execute(sa.text(
        "SELECT id, name FROM reporting.saved_reports "
        "WHERE deleted_at IS NULL AND builtin_key IS NULL "
        "  AND (selection::text LIKE '%membership_new%' "
        "    OR selection::text LIKE '%membership_renewed%' "
        "    OR selection::text LIKE '%membership_lapsed%' "
        "    OR selection::text LIKE '%payment_outstanding%')"
    )).fetchall()
    for rij in resterend:
        print(f"  #871: bewaard rapport {rij[0]} ({rij[1]}) gebruikt een "
              f"verwijderde maat; open het en kies Lidmaatschapsstatus.")


def downgrade() -> None:
    pass
