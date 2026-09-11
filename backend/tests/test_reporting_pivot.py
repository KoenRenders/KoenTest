"""The crosstab (#834, CR-06 §5): one selection, drawn as a pivot.

The pivot reads exactly the objects the table form reads; it only moves one
dimension to the column axis. So the first test is not "the numbers look right"
but **the numbers are the same numbers** — a crosstab that disagrees with its own
table form is the failure that makes a board distrust every report after it.

Would these be green if the subject were broken? The cells come from the known
seed of #832, worked out by hand below, including the one cell that must stay
EMPTY: nobody paid an activity in cash. Sum the columns in Python instead of
asking SQL for the row totals and the counts still match — but the average would
not, and that is written down as its own test.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import pytest

from app.domains.reporting.api import (
    MAX_PIVOT_COLUMNS, Filter, Operator, Selection, SelectionError, build_pivot,
    run_validated,
)
from tests._reporting_seed import EXPECTED, TENANT_A, TENANT_B, seed
from tests.test_reporting_panel_ui import ADMIN_EMAIL, login


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def pivot(db, objects, column, *, tenant=TENANT_A, filters=()):
    return build_pivot(
        db,
        Selection(object_keys=tuple(objects), filters=tuple(filters),
                  layout="pivot", pivot_column=column, limit=5000),
        tenant_id=tenant)


# ── Known cells (#834 test 2) ────────────────────────────────────────────────

def test_the_cells_are_the_seed_s_numbers_and_the_empty_one_stays_empty(
        db_session, situation):
    """Betaalwijze × Waarvoor. Nobody paid an activity in cash — that cell is empty.

    An empty cell is not a zero, and rendering it as one would be a lie a reader
    cannot see: "we took nothing in cash for activities" and "no cash activity
    payment exists" are different statements.
    """
    kruis = pivot(db_session, ["payment_method", "payment_payable_type",
                               "payment_amount"], "payment_payable_type")
    context = kruis.as_context()

    assert context["row_headers"] == ["Betaalwijze"]
    assert context["column_values"] == ["Activiteit", "Lidgeld"]

    per_rij = {rij["labels"][0]: rij for rij in context["rows"]}
    assert Decimal(per_rij["Online"]["cells"][0][0]) == Decimal("10.00")
    assert Decimal(per_rij["Online"]["cells"][1][0]) == Decimal("35.00")
    assert Decimal(per_rij["Overschrijving"]["cells"][0][0]) == Decimal("10.00")
    assert Decimal(per_rij["Overschrijving"]["cells"][1][0]) == Decimal("35.00")
    assert per_rij["Cash"]["cells"][0][0] is None, (
        "er is geen activiteit cash betaald — die cel hoort leeg te blijven")
    assert Decimal(per_rij["Cash"]["cells"][1][0]) == Decimal("30.00")

    for label, verwacht in EXPECTED["payments"]["per_method"].items():
        assert Decimal(per_rij[label]["total"][0]) == verwacht, label
    assert Decimal(context["grand_total"][0]) == EXPECTED["payments"]["amount"]


def test_registrations_per_activity_per_year_as_a_crosstab(db_session, situation):
    """Question 3 of CR-06 §3, in its second shape."""
    _y0, _y1, y2, _y3 = situation["years"]
    kruis = pivot(db_session, ["activity", "activity_year", "registration_count"],
                  "activity_year").as_context()
    assert kruis["column_values"] == [str(y2)]
    assert kruis["rows"][0]["labels"] == ["Quiz"]
    assert kruis["rows"][0]["cells"][0][0] == EXPECTED["registrations"]["count"]
    assert kruis["grand_total"][0] == EXPECTED["registrations"]["count"]


# ── Equivalence (#834 test 1) ────────────────────────────────────────────────

def test_the_grand_total_equals_the_table_form_s_total(db_session, situation):
    """Same selection, two shapes, one number — because it is one query."""
    objecten = ("payment_method", "payment_payable_type", "payment_amount")
    tabel = run_validated(db_session, Selection(object_keys=objecten),
                          tenant_id=TENANT_A)
    kruis = pivot(db_session, list(objecten), "payment_payable_type").as_context()
    assert Decimal(kruis["grand_total"][0]) == Decimal(tabel.totals["payment_amount"])


def test_each_subtotal_is_the_sum_of_its_rows(db_session, situation):
    """Two row dimensions, so every group closes with a subtotal."""
    kruis = pivot(db_session, ["payment_payable_type", "payment_method",
                               "payment_status", "payment_amount"],
                  "payment_status").as_context()
    assert kruis["row_headers"] == ["Soort", "Betaalwijze"]

    som_per_groep: dict[str, Decimal] = {}
    subtotalen: dict[str, Decimal] = {}
    for rij in kruis["rows"]:
        if rij["is_subtotal"]:
            subtotalen[rij["labels"][0]] = Decimal(rij["total"][0])
        else:
            groep = rij["labels"][0]
            som_per_groep[groep] = som_per_groep.get(groep, Decimal("0")) + \
                Decimal(rij["total"][0])

    assert subtotalen == {"Activiteit": Decimal("20.00"),
                          "Lidgeld": Decimal("100.00")}
    assert subtotalen == som_per_groep, "elk subtotaal is de som van zijn rijen"
    assert sum(subtotalen.values()) == Decimal(kruis["grand_total"][0])


def test_a_single_row_dimension_gets_no_subtotals(db_session, situation):
    """A subtotal per row would just repeat the line above it."""
    kruis = pivot(db_session, ["payment_method", "payment_payable_type",
                               "payment_amount"], "payment_payable_type")
    assert not any(rij.is_subtotal for rij in kruis.rows)


def test_an_average_is_asked_of_sql_and_not_added_up(db_session, situation):
    """The reason nothing here is summed in Python.

    Every paid record in the seed took four days, so both the row total and the
    grand total of the average must read 4 — while the sum of the per-column
    averages would read 8. This test is the one that goes red the day somebody
    "simplifies" the row totals into a Python sum.
    """
    kruis = pivot(db_session, ["payment_method", "payment_payable_type",
                               "payment_days_to_paid"],
                  "payment_payable_type").as_context()
    per_rij = {rij["labels"][0]: rij for rij in kruis["rows"]}
    assert int(per_rij["Online"]["total"][0]) == 4
    assert int(kruis["grand_total"][0]) == 4


# ── The column cap (#834 test 3) ─────────────────────────────────────────────

def _extra_payments(db, aantal: int) -> None:
    """`aantal` payments on distinct days, so `Datum` has that many members."""
    from datetime import datetime, timezone
    from app.domains.payment.api import PaymentRecord

    nu = datetime.now(timezone.utc)
    for dag in range(aantal):
        db.add(PaymentRecord(
            tenant_id=TENANT_A, payable_type="membership", payable_id=900 + dag,
            amount=Decimal("1.00"), method="cash", status="paid",
            amount_paid=Decimal("1.00"), type="charge",
            created_at=nu - timedelta(days=400 + dag),
            paid_at=nu - timedelta(days=399 + dag)))
    db.commit()


def test_a_column_dimension_with_too_many_members_is_refused_by_name(db_session,
                                                                    situation):
    """No query runs: the count is asked first, under the same filters."""
    _extra_payments(db_session, MAX_PIVOT_COLUMNS + 5)
    with pytest.raises(SelectionError) as exc:
        pivot(db_session, ["payment_method", "date_day", "payment_amount"],
              "date_day")
    melding = str(exc.value)
    assert "'Datum'" in melding, "de melding noemt de dimensie"
    assert str(MAX_PIVOT_COLUMNS) in melding


def test_exactly_the_cap_still_works(db_session, situation):
    """The counter-proof of the cap: exactly at the line is not refused.

    Without it, "too many columns" could be a check that always fires — and a cap
    that always fires and a cap that works look identical from the green side.

    It also pins the second half of the rule: the count is taken **under the
    active filters**. The seed has 31 distinct payment days here; filtering to
    cash leaves exactly 30, and that must be allowed — filtering is how a user
    makes a crosstab fit, and a cap that ignored the filter would refuse a report
    that fits.
    """
    from sqlalchemy import text

    # 29 extra plus the one cash payment of the seed makes exactly the cap.
    _extra_payments(db_session, MAX_PIVOT_COLUMNS - 1)
    alle_dagen = db_session.execute(text(
        "SELECT COUNT(DISTINCT date_key) FROM reporting.f_payments "
        "WHERE tenant_id = :t"), {"t": TENANT_A}).scalar()
    assert alle_dagen > MAX_PIVOT_COLUMNS, "ongefilterd zit het erboven"

    kruis = pivot(db_session, ["payment_method", "date_day", "payment_amount"],
                  "date_day",
                  filters=[Filter("payment_method", Operator.EQ, ("Cash",))])
    assert len(kruis.column_values) == MAX_PIVOT_COLUMNS


def test_a_pivot_without_a_column_dimension_is_a_grouped_listing(db_session,
                                                                 situation):
    """This used to be refused, and #850 needed it.

    "Leden per bestuurslid" is one row per household with a subtotal of households
    per board member — a pivot whose only column is the total. Everything in
    `build_pivot` already handled an empty column dimension; only the refusal
    stood in the way, and what it protected against is exactly the shape being
    asked for.
    """
    pivot = build_pivot(db_session,
                        Selection(object_keys=("payment_method", "payment_amount"),
                                  layout="pivot"),
                        tenant_id=TENANT_A)
    assert pivot.rows, "een kolomloze draaitabel levert gewoon rijen"
    assert pivot.column_column is None, "geen kolomas, want die is niet gekozen"
    assert not pivot.column_values
    assert all(rij.total for rij in pivot.rows), "elke rij draagt haar totaal"


def test_a_pivot_needs_a_row_dimension_too(db_session, situation):
    with pytest.raises(SelectionError) as exc:
        pivot(db_session, ["payment_method", "payment_amount"], "payment_method")
    assert "rijen van de draaitabel" in str(exc.value)


def test_a_measure_cannot_be_the_column_axis(db_session, situation):
    with pytest.raises(SelectionError) as exc:
        pivot(db_session, ["payment_method", "payment_amount"], "payment_amount")
    assert "'Te betalen'" in str(exc.value)
    assert "maat" in str(exc.value)


# ── Tenant (#834 test 4) ─────────────────────────────────────────────────────

def test_a_crosstab_holds_only_its_own_tenant(db_session, situation):
    a = pivot(db_session, ["payment_method", "payment_payable_type",
                           "payment_amount"], "payment_payable_type")
    b = pivot(db_session, ["payment_method", "payment_payable_type",
                           "payment_amount"], "payment_payable_type",
              tenant=TENANT_B)
    assert Decimal(a.grand_total["payment_amount"]) == EXPECTED["payments"]["amount"]
    assert Decimal(b.grand_total["payment_amount"]) == \
        EXPECTED["tenant_b"]["payments_amount"]


# ── The panel and the export (#834 test 5) ───────────────────────────────────

def test_the_panel_renders_a_crosstab(client, db_session, situation):
    login(client, db_session)
    fragment = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_payable_type"
        "&object=payment_amount&layout=pivot&pivot_column=payment_payable_type")
    assert fragment.status_code == 200
    assert "Eindtotaal" in fragment.text
    assert "Activiteit" in fragment.text and "Lidgeld" in fragment.text
    assert "120,00" in fragment.text


def test_choosing_the_crosstab_picks_a_column_axis_by_itself(client, db_session,
                                                             situation):
    """One click on "Draaitabel" has to produce a crosstab, not a question."""
    login(client, db_session)
    fragment = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_payable_type"
        "&object=payment_amount&set_layout=pivot")
    assert fragment.status_code == 200
    assert 'name="pivot_column" value="payment_payable_type"' in fragment.text
    assert "Eindtotaal" in fragment.text


def test_the_crosstab_export_has_both_sheets(client, db_session, situation):
    from odf.opendocument import load
    from odf.table import Table, TableCell, TableRow
    from odf.text import P

    login(client, db_session)
    antwoord = client.get(
        "/admin/rapporten/export.ods?object=payment_method"
        "&object=payment_payable_type&object=payment_amount"
        "&layout=pivot&pivot_column=payment_payable_type")
    assert antwoord.status_code == 200

    document = load(BytesIO(antwoord.content))
    bladen = {}
    for tabel in document.getElementsByType(Table):
        bladen[tabel.getAttribute("name")] = [
            ["".join(str(p) for p in cel.getElementsByType(P))
             for cel in rij.getElementsByType(TableCell)]
            for rij in tabel.getElementsByType(TableRow)]

    blad1 = bladen["Rapport"]
    assert blad1[0][:2] == ["Rapport", "Rapport"]
    kop = next(rij for rij in blad1 if rij[:1] == ["Betaalwijze"])
    assert kop[1:] == ["Activiteit", "Lidgeld", "Totaal"]
    inhoud = blad1[blad1.index(kop) + 1:]
    assert inhoud[-1][0] == "Eindtotaal"
    assert Decimal(inhoud[-1][-1]) == EXPECTED["payments"]["amount"]

    assert "Detail" in bladen
    # Sheet 2 is the flat selection: one row per payment record of this tenant.
    assert len(bladen["Detail"]) == EXPECTED["payments"]["count"] + 1


def test_a_saved_crosstab_keeps_its_shape(client, db_session, situation):
    from app.domains.reporting.api import list_saved_reports

    csrf = login(client, db_session)
    client.post("/admin/rapporten",
                headers={"X-CSRF-Token": csrf,
                         "Content-Type": "application/x-www-form-urlencoded"},
                content=("name=Kruistabel&is_shared=1&layout=pivot"
                         "&pivot_column=payment_payable_type"
                         "&object=payment_method&object=payment_payable_type"
                         "&object=payment_amount"))
    bewaard = [r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                             viewer=ADMIN_EMAIL)
               if r.name == "Kruistabel"][0]
    assert bewaard.selection["layout"] == "pivot"
    assert bewaard.selection["pivot_column"] == "payment_payable_type"

    pagina = client.get(f"/admin/rapporten/{bewaard.id}")
    assert "Eindtotaal" in pagina.text
    lijst = client.get("/admin/rapporten/lijst?q=Kruistabel")
    assert "Draaitabel" in lijst.text, "de kaart toont de vorm"
