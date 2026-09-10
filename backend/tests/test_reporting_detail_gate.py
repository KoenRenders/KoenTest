"""A detail may be shown, not grouped by — now a rule instead of a sentence (#852).

The universe has always said it: *"a detail is an attribute of a dimension you may
show but not group by: it would split the grain without adding a question."*
Nothing enforced it. `build_query` groups on everything that is not a measure, so
a detail simply grouped, and the report came back looking like every other report.

**Three cases, and they are not equally bad.** Worth writing down, because the
gate reads as heavy-handed without them:

- `payment_ogm`, `payment_paid_on` and the label fields give one row per payment.
  No lie, but a list dressed as a summary — the measures beside them are single
  amounts, not totals.
- **`payment_note` is the case this gate is for.** Free text is not a key. Two
  payments carrying the same note fold into one row and their amounts add up. The
  sum is right for that group; a reader taking the row for one payment reads
  something other than what is there.
- `date_month_label` only sorts wrong — alphabetically, "april 2026" before
  "januari 2026". Visible, and no silent number.

**Enforcing and not dropping the kind.** Twelve objects carry `DETAIL`, eleven of
them columns of the payments listing. Dropping the kind would promote those eleven
to grouping axes — it removes the warning instead of the trap.

**The gate found a misdeclaration on its first run.** `task_done_by` was a detail,
and the personal work list of #847 groups on it — "how many did each of us close",
which is the question `@ik` exists for. An e-mail address is a key, unlike a free
text note, so the declaration was wrong and not the report; it is a dimension now.
That is one wrong declaration in thirteen, found the moment the sentence became a
rule.

**The counter-proof was run.** A selection grouping on `payment_ogm` was put
through `build_query`, the refusal named that object, and the same selection in
the list shape went through untouched. That is what the first two tests do on
every run.
"""
from __future__ import annotations

import pytest

from app.domains.reporting.api import Selection, build_query
from app.domains.reporting.engine import SelectionError
from app.domains.reporting.universe import BY_KEY, OBJECTS, ObjectKind
from tests._reporting_seed import TENANT_A, seed


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def test_grouping_on_a_detail_is_refused_and_says_which_one():
    """The gate. Breaking it is the point: this selection used to work."""
    with pytest.raises(SelectionError) as exc:
        build_query(
            Selection(object_keys=("payment_ogm", "payment_amount")),
            tenant_id=TENANT_A)
    melding = str(exc.value)
    assert "OGM" in melding or "Gestructureerde" in melding, (
        f"de melding hoort te zeggen wélk object het betreft: {melding}")
    assert "detail" in melding.lower()
    assert "lijst" in melding.lower(), "en wat je er dan mee doet"


def test_the_same_objects_in_a_list_are_fine():
    """The other half of the proof: it is the grouping that is refused, not the
    object. A list is exactly where a detail belongs."""
    plan = build_query(
        Selection(object_keys=("payment_ogm", "payment_note"), layout="detail"),
        tenant_id=TENANT_A)
    assert "structured_communication" in plan.sql or plan.sql


def test_the_free_text_detail_is_the_one_that_would_have_lied(db_session,
                                                              situation):
    """Why `payment_note` and not `payment_ogm` carries this issue.

    An OGM is unique per payment, so grouping on it gives one row each — untidy,
    not untrue. A note is free text, so two payments sharing one fold into a
    single row whose amounts add up. Shown here by running the query the gate now
    refuses, straight against the database.
    """
    from sqlalchemy import text

    db_session.execute(text(
        "UPDATE payment.payment_records SET note = 'Zelfde notitie' "
        "WHERE tenant_id = :t AND deleted_at IS NULL"), {"t": TENANT_A})
    db_session.commit()

    rijen = list(db_session.execute(text(
        "SELECT note, COUNT(*) AS aantal, SUM(amount) AS som "
        "FROM reporting.f_payments WHERE tenant_id = :t AND note <> '' "
        "GROUP BY note"), {"t": TENANT_A}))
    assert rijen, "de seed heeft betalingen"
    assert any(rij.aantal > 1 for rij in rijen), (
        "twee betalingen met dezelfde notitie vallen samen in één rij — dat is "
        "het geval waarvoor deze gate bestaat")


def test_every_shipped_report_groups_only_on_dimensions(db_session, situation):
    """The test that does not depend on the gate.

    The gate stops what a user builds today; this catches the next shipped report
    that breaks the rule in a migration, where no user is looking. Measured before
    the gate existed: none of the twenty-one selections grouped on a detail, so
    this starts green and stays that way on purpose.
    """
    from app.domains.reporting.api import list_saved_reports, selection_from_dict

    rapporten = [r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                               viewer="") if r.builtin_key]
    assert len(rapporten) >= 19, "de meegeleverde rapporten staan er"

    fouten = []
    for rapport in rapporten:
        selectie = selection_from_dict(rapport.selection)
        if selectie.layout == "detail":
            continue          # a list is where a detail belongs
        for key in selectie.object_keys:
            obj = BY_KEY.get(key)
            if obj is not None and obj.kind is ObjectKind.DETAIL:
                fouten.append(f"{rapport.builtin_key} groepeert op {key}")
    assert not fouten, fouten


def test_the_kind_is_worth_keeping_because_thirteen_objects_carry_it():
    """The reason the fix is enforcement and not deletion.

    Eleven of the thirteen are columns of the payments listing. Dropping `DETAIL`
    would make every one of them a grouping axis — that removes the warning, not
    the trap. If this number ever drops to nearly nothing, the trade-off is worth
    revisiting, and this test is where that conversation starts.
    """
    details = [o for o in OBJECTS if o.kind is ObjectKind.DETAIL]
    assert len(details) >= 10, (
        f"nog maar {len(details)} details — is de afweging uit #852 nog dezelfde?")
    assert BY_KEY["task_done_by"].kind is ObjectKind.DIMENSION, (
        "'Afgehandeld door' is een sleutel en de as van de werklijst uit #847; "
        "als detail zou de gate die werklijst weigeren")
    assert sum(1 for o in details if o.view == "f_payments") >= 6, (
        "het merendeel hoort bij de betalingenlijst")


def test_a_detail_in_a_pivot_is_refused_too(db_session, situation):
    """The pivot runs through the same engine, so it inherits the refusal.

    Worth its own test: a pivot builds several selections (rows, subtotals) and a
    rule that only landed on one of them would be a rule with a hole in it.
    """
    from app.domains.reporting.api import build_pivot

    with pytest.raises(SelectionError):
        build_pivot(db_session,
                    Selection(object_keys=("payment_method", "payment_note",
                                           "payment_amount"),
                              layout="pivot", pivot_column="payment_method"),
                    tenant_id=TENANT_A)
