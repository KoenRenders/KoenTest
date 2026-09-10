"""Known-seed numbers per fact, and the tenant fence around them (#832).

CR-06 §9 puts this first, and it is the reason the whole star exists: *a plausible
but wrong number is reporting's worst failure*. Every assertion below is an exact
count or an exact amount, worked out by hand in `tests/_reporting_seed.py` from a
situation that contains the four things that make reporting lie — a second tenant,
a soft-deleted row, a refund, and a member price.

Would these tests be green if the subject were broken? No, and that was checked
per view rather than assumed:

- drop the tenant condition from the engine and the payment sums pick up tenant
  B's 500,00;
- lose ``deleted_at IS NULL`` in ``f_registrations`` and the count goes from 3 to
  4 and the quantity from 3 to 8;
- inner-join the registration lines and the count drops to 2;
- lose the member-price rule and the registration amount goes from 26,00 to 30,00;
- count the lapsed households as members and the last year reads 3 instead of 2.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.domains.reporting.api import (
    Filter,
    Operator,
    Selection,
    SelectionError,
    Sort,
    load_dataset,
    run_selection,
)
from tests._reporting_seed import EXPECTED, TENANT_A, TENANT_B, seed

@pytest.fixture
def situation(db_session):
    return seed(db_session)


def run(db, keys, *, tenant=TENANT_A, filters=(), sort=()):
    return run_selection(
        db, Selection(object_keys=tuple(keys), filters=tuple(filters),
                      sort=tuple(sort)),
        tenant_id=tenant)


def by(result, key):
    """The rows as a dict keyed by one column — reports are small enough."""
    return {row[key]: row for row in result.rows}


# ── f_memberships: questions 1 and 2 ─────────────────────────────────────────

def test_members_per_year_counts_households_and_persons(db_session, situation):
    """Question 1: how many members, and how does that evolve per year?"""
    y0, y1, y2, y3 = situation["years"]
    result = run(db_session, ["membership_year", "membership_households",
                              "membership_persons"])
    rows = by(result, "membership_year")

    verwacht = EXPECTED["memberships"]
    for offset, year in enumerate((y0, y1, y2, y3)):
        assert rows[year]["membership_households"] == verwacht["households"][offset], (
            f"aantal gezinnen in {year}")
        assert rows[year]["membership_persons"] == verwacht["persons"][offset], (
            f"aantal personen in {year}")


def test_new_renewed_and_lapsed_add_up_per_year(db_session, situation):
    """Question 2: how many renew, how many lapse, how many are new?

    A lapsed household has no membership row at all in that year, so this is the
    number that a fact built straight on `memberships` cannot produce — and the
    one that proves the grid in `f_memberships` does its job.
    """
    y0, y1, y2, y3 = situation["years"]
    result = run(db_session, ["membership_year", "membership_new",
                              "membership_renewed", "membership_lapsed"])
    rows = by(result, "membership_year")

    verwacht = EXPECTED["memberships"]
    for offset, year in enumerate((y0, y1, y2, y3)):
        assert rows[year]["membership_new"] == verwacht["new"][offset], f"nieuw in {year}"
        assert rows[year]["membership_renewed"] == verwacht["renewed"][offset], (
            f"vernieuwd in {year}")
        assert rows[year]["membership_lapsed"] == verwacht["lapsed"][offset], (
            f"vervallen in {year}")


def test_a_membership_taken_out_in_october_counts_in_its_own_year(db_session,
                                                                  situation):
    """From mid-September a membership can be taken out for the NEXT year.

    Its `valid_from` then falls in this year while its `year` is the next one, and
    the free tail of this year is a gift rather than a membership of this year.
    The fact must count it once, in `year` — H4 is 0 this year and 1 next year,
    and "new" next year.

    This is exactly the shape in which a star schema double-counts: read the
    validity dates instead of `year` and H4 appears in both years, with two
    numbers that each look reasonable on their own.
    """
    _y0, _y1, y2, y3 = situation["years"]
    result = run(db_session, ["membership_year", "membership_households",
                              "membership_new"])
    rows = by(result, "membership_year")

    assert rows[y2]["membership_households"] == 2, (
        "H4 is dit jaar geen lid, ook al loopt zijn lidmaatschap al")
    assert rows[y3]["membership_households"] == 1
    assert rows[y3]["membership_new"] == 1, "H4 is nieuw in het jaar waarvoor hij betaalt"

    per_household = run(db_session, ["household", "membership_year",
                                     "membership_households"],
                        filters=[Filter("household", Operator.EQ,
                                        (str(situation["households"]["h4"]),))])
    jaren = {row["membership_year"] for row in per_household.rows}
    assert jaren == {y3}, "één rij, in één jaar"


def test_membership_status_dimension_labels_the_same_rows(db_session, situation):
    """The status dimension and the three counters must tell the same story."""
    _y0, y1, _y2, _y3 = situation["years"]
    result = run(db_session, ["membership_year", "membership_status",
                              "membership_households"],
                 filters=[Filter("membership_year", Operator.EQ, (str(y1),))])
    labels = {row["membership_status"] for row in result.rows}
    assert labels == {"Vernieuwd", "Vervallen"}


def test_membership_money_is_the_charged_and_received_amount(db_session, situation):
    y0, y1, y2, y3 = situation["years"]
    result = run(db_session, ["membership_year", "membership_amount_charged",
                              "membership_amount_paid"])
    rows = by(result, "membership_year")
    verwacht = EXPECTED["memberships"]
    for offset, year in enumerate((y0, y1, y2, y3)):
        assert Decimal(rows[year]["membership_amount_charged"]) == verwacht["charged"][offset]
        assert Decimal(rows[year]["membership_amount_paid"]) == verwacht["paid"][offset]


# ── f_registrations: question 3 ──────────────────────────────────────────────

def test_registrations_per_activity_and_year(db_session, situation):
    """Question 3: which activities draw the most people?

    Three registrations, three units: one member who took two, one guest who took
    one, and one who never picked a product. That last one is the interesting case
    — it is a real registration and it must be counted.
    """
    result = run(db_session, ["activity", "activity_year", "registration_count",
                              "registration_quantity"])
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["activity"] == "Quiz"
    assert row["registration_count"] == EXPECTED["registrations"]["count"]
    assert row["registration_quantity"] == EXPECTED["registrations"]["quantity"]


def test_registration_amount_uses_the_member_price(db_session, situation):
    """The member price of the day of registration, not the list price.

    `activities.totals` decides this for the screens; the view repeats the rule in
    SQL. Both must land on 26,00 — 2 x 8,00 for the member plus 1 x 10,00 for the
    guest. At the list price it would be 30,00, which is exactly the kind of
    number nobody would question.
    """
    result = run(db_session, ["activity", "registration_amount"])
    assert Decimal(result.rows[0]["registration_amount"]) == \
        EXPECTED["registrations"]["amount"]


def test_registration_without_lines_shows_as_a_row_without_a_product(db_session,
                                                                    situation):
    result = run(db_session, ["product", "registration_count"])
    products = by(result, "product")
    assert products["Geen product"]["registration_count"] == 1
    assert products["Deelname"]["registration_count"] == 2


# ── f_payments: questions 4 to 7 ─────────────────────────────────────────────

def test_payment_totals_are_net_of_refunds(db_session, situation):
    result = run(db_session, ["payment_payable_type", "payment_amount",
                              "payment_amount_paid", "payment_open_amount",
                              "payment_refunded", "payment_count"])
    rows = by(result, "payment_payable_type")
    verwacht = EXPECTED["payments"]["per_payable_type"]
    for label, amounts in verwacht.items():
        assert Decimal(rows[label]["payment_amount"]) == amounts["amount"], label
        assert Decimal(rows[label]["payment_amount_paid"]) == amounts["paid"], label

    totals = result.totals
    assert Decimal(totals["payment_amount"]) == EXPECTED["payments"]["amount"]
    assert Decimal(totals["payment_amount_paid"]) == EXPECTED["payments"]["amount_paid"]
    assert Decimal(totals["payment_open_amount"]) == EXPECTED["payments"]["open"]
    assert Decimal(totals["payment_refunded"]) == EXPECTED["payments"]["refunded"]
    assert totals["payment_count"] == EXPECTED["payments"]["count"]


def test_revenue_per_activity(db_session, situation):
    """Question 4: what does each activity bring in?

    Membership payments have no activity, so they land on a row with an empty
    activity — that is the honest answer, not a reason to drop them.
    """
    result = run(db_session, ["activity", "payment_amount", "payment_amount_paid"])
    rows = by(result, "activity")
    verwacht = EXPECTED["payments"]["per_activity"]["Quiz"]
    assert Decimal(rows["Quiz"]["payment_amount"]) == verwacht["amount"]
    assert Decimal(rows["Quiz"]["payment_amount_paid"]) == verwacht["paid"]
    assert None in rows, "lidgeldbetalingen horen bij geen activiteit"


def test_revenue_per_month_adds_up_to_the_total(db_session, situation):
    """Question 5: revenue per month.

    The months follow from when the seed was run, so the assertion is the one that
    matters anyway: split by month, nothing may fall out and nothing may double.
    """
    result = run(db_session, ["date_month", "payment_amount"])
    som = sum((Decimal(row["payment_amount"]) for row in result.rows), Decimal("0"))
    assert som == EXPECTED["payments"]["amount"]
    assert Decimal(result.totals["payment_amount"]) == som


def test_outstanding_per_age_bucket(db_session, situation):
    """Question 6: what is outstanding, and for how long?

    The guest's charge was created 120 days ago and never settled; the second
    membership charge 10 days ago. They must land in different buckets, and the
    settled records must not land in an ageing bucket at all.
    """
    result = run(db_session, ["payment_age_bucket", "payment_open_amount"])
    buckets = by(result, "payment_age_bucket")
    assert Decimal(buckets["meer dan 90 dagen"]["payment_open_amount"]) == Decimal("10.00")
    assert Decimal(buckets["0-30 dagen"]["payment_open_amount"]) == Decimal("35.00")
    assert Decimal(buckets["Betaald"]["payment_open_amount"]) == Decimal("0.00")


def test_payment_method_and_speed(db_session, situation):
    """Question 7: how do people pay, and how fast?"""
    result = run(db_session, ["payment_method", "payment_amount",
                              "payment_days_to_paid"])
    rows = by(result, "payment_method")
    for label, amount in EXPECTED["payments"]["per_method"].items():
        assert Decimal(rows[label]["payment_amount"]) == amount, label
    assert int(result.totals["payment_days_to_paid"]) == \
        EXPECTED["payments"]["days_to_paid"]


# ── The tenant fence (CR-06 §7.1) ────────────────────────────────────────────

def test_the_same_selection_returns_only_its_own_tenant(db_session, situation):
    """Tenant B paid 500,00 that tenant A may never see, and the other way round."""
    keys = ["payment_amount", "payment_count"]
    a = run(db_session, keys, tenant=TENANT_A)
    b = run(db_session, keys, tenant=TENANT_B)

    assert Decimal(a.rows[0]["payment_amount"]) == EXPECTED["payments"]["amount"]
    assert Decimal(b.rows[0]["payment_amount"]) == EXPECTED["tenant_b"]["payments_amount"]
    assert a.rows[0]["payment_count"] == EXPECTED["payments"]["count"]
    assert b.rows[0]["payment_count"] == 1


def test_a_dimension_row_is_not_borrowed_from_another_tenant(db_session, situation):
    """The join carries `tenant_id` too, not only the fact's WHERE.

    Without that condition a household id that exists in both tenants would attach
    tenant A's municipality to tenant B's fact row — a leak the fact filter alone
    does not catch.
    """
    b = run(db_session, ["household_municipality", "membership_households"],
            tenant=TENANT_B)
    assert b.rows[0]["membership_households"] == EXPECTED["tenant_b"]["households"]


# ── The flat dataset export (#832, point 5) ──────────────────────────────────

def test_dataset_holds_every_column_of_the_view_for_one_tenant(db_session, situation):
    dataset = load_dataset(db_session, "f_payments", tenant_id=TENANT_A)
    assert "payment_id" in dataset.headers
    assert "tenant_id" in dataset.headers
    assert len(dataset.rows) == EXPECTED["payments"]["count"]

    amount_at = dataset.headers.index("amount")
    som = sum((Decimal(str(row[amount_at])) for row in dataset.rows), Decimal("0"))
    assert som == EXPECTED["payments"]["amount"], (
        "de platte export moet hetzelfde totaal geven als het rapport")


def test_dataset_refuses_a_fact_that_is_not_in_the_universe(db_session, situation):
    """The fact name reaches the SQL only through the universe's own dictionary."""
    with pytest.raises(SelectionError) as exc:
        load_dataset(db_session, "pg_class; DROP TABLE mdm.persons",
                     tenant_id=TENANT_A)
    assert "Onbekend feit" in str(exc.value)


# ── Equivalence and ordering ─────────────────────────────────────────────────

def test_the_totals_row_equals_the_sum_of_the_rows(db_session, situation):
    """CR-06 §9: the totals row is not a second story.

    True for a SUM by construction; the point of the test is that both come from
    the same filtered set. Change the filter on one and not the other and this
    goes red.
    """
    result = run(db_session, ["payment_method", "payment_amount"])
    som = sum((Decimal(row["payment_amount"]) for row in result.rows), Decimal("0"))
    assert Decimal(result.totals["payment_amount"]) == som


def test_the_default_order_is_stable_after_an_update(db_session, situation):
    """#761: a default sort that ends in a unique key survives a row being touched.

    Postgres moves an updated row to the end of the heap, so a `GROUP BY` without a
    deterministic `ORDER BY` hands back a different order afterwards. This test
    reads the report, touches a payment, and reads it again.
    """
    from app.domains.payment.api import PaymentRecord

    keys = ["payment_method", "payment_payable_type", "payment_amount"]
    before = [(row["payment_method"], row["payment_payable_type"])
              for row in run(db_session, keys).rows]

    record = db_session.query(PaymentRecord).filter(
        PaymentRecord.method == "transfer").first()
    record.note = "aangeraakt"
    db_session.commit()

    after = [(row["payment_method"], row["payment_payable_type"])
             for row in run(db_session, keys).rows]
    assert before == after
    assert after == sorted(after), "de standaardsortering is de groepering zelf"


def test_a_filter_value_is_a_value_and_never_sql(db_session, situation):
    """No free SQL (CR-06 §7.5): a value travels as a bind parameter.

    If it did not, this filter would end the statement and the test would fail on
    a database error instead of an empty result.
    """
    result = run(db_session, ["payment_method", "payment_amount"], filters=[Filter("payment_method", Operator.EQ,
                                 ("Online' OR '1'='1",))])
    assert result.rows == []


def test_sorting_puts_the_requested_column_first(db_session, situation):
    from app.domains.reporting.api import Direction

    result = run(db_session, ["payment_method", "payment_amount"], sort=[Sort("payment_amount", Direction.DESC)])
    amounts = [Decimal(row["payment_amount"]) for row in result.rows]
    assert amounts == sorted(amounts, reverse=True)


# ── The filter forms the panel will use (#833) ───────────────────────────────

def test_every_filter_form_narrows_the_same_report(db_session, situation):
    """One operator per form, each against a number we already know.

    Written here and not with the refusals, because a filter that parses and then
    matches the wrong rows is a different failure than one that is refused: the
    first one gives you a report, and the report is wrong.
    """
    keys = ["payment_method", "payment_amount"]
    verwacht = EXPECTED["payments"]["per_method"]

    alleen_online = run(db_session, keys, filters=[Filter("payment_method", Operator.EQ, ("Online",))])
    assert len(alleen_online.rows) == 1
    assert Decimal(alleen_online.rows[0]["payment_amount"]) == verwacht["Online"]

    twee = run(db_session, keys, filters=[Filter("payment_method", Operator.IN, ("Online", "Cash"))])
    assert {row["payment_method"] for row in twee.rows} == {"Online", "Cash"}

    niet_cash = run(db_session, keys, filters=[Filter("payment_method", Operator.NE, ("Cash",))])
    assert "Cash" not in {row["payment_method"] for row in niet_cash.rows}

    zoek = run(db_session, keys, filters=[Filter("payment_method", Operator.CONTAINS, ("schrijv",))])
    assert {row["payment_method"] for row in zoek.rows} == {"Overschrijving"}

    y0, _y1, y2, y3 = situation["years"]
    bereik = run(db_session, ["membership_year", "membership_households"],
                 filters=[Filter("membership_year", Operator.BETWEEN,
                                 (str(y0), str(y0)))])
    assert [row["membership_year"] for row in bereik.rows] == [y0]

    vanaf = run(db_session, ["membership_year", "membership_households"],
                filters=[Filter("membership_year", Operator.GTE, (str(y2),))])
    assert [row["membership_year"] for row in vanaf.rows] == [y2, y3]


def test_a_filter_may_use_a_dimension_that_is_not_a_column(db_session, situation):
    """CR-06 §5: "a filter per chosen **or extra** dimension".

    Filtering on the payment status without showing it must still narrow the
    report — and it must bring its dimension view along in the join.
    """
    result = run(db_session, ["payment_payable_type", "payment_amount"],
                 filters=[Filter("payment_status", Operator.EQ, ("Betaald",))])
    som = sum((Decimal(row["payment_amount"]) for row in result.rows), Decimal("0"))
    assert som == EXPECTED["payments"]["amount_paid"], (
        "alleen de betaalde records; hun bedrag is per definitie het ontvangen bedrag")


def test_paging_walks_the_report_without_losing_or_repeating_a_row(db_session,
                                                                   situation):
    """Paging is only safe because the order ends in a unique key (#761)."""
    from app.domains.reporting.api import Selection

    keys = ("payment_method", "payment_payable_type", "payment_amount")
    heel = run_selection(db_session, Selection(object_keys=keys),
                         tenant_id=TENANT_A).rows
    stukjes = []
    for offset in range(0, len(heel), 2):
        deel = run_selection(
            db_session, Selection(object_keys=keys, limit=2, offset=offset),
            tenant_id=TENANT_A)
        stukjes.extend(deel.rows)
    assert stukjes == heel
