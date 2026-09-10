"""The report "Leden per bestuurslid" (#850).

This report exists already — the penningmeester makes it by hand for the
voorzitter — so the question is not whether it is useful but whether it is right.
Its grain is **one row per household**, and three things could quietly break that
or its order.

**The house numbers are the trap worth the most.** `house_number` is a
`String(10)`, so alphabetically "10" comes before "9" and this report sorts on
exactly that column. The seed carries 2, 9, 10 and 12A in one street for this
reason: an all-1s seed would let the wrong order pass unseen.
"""
from __future__ import annotations

import pytest

from app.domains.mdm.api import Member, MemberPerson, Person
from app.domains.reporting.api import (
    Selection, build_pivot, list_saved_reports, run_validated,
    selection_from_dict,
)
from tests._reporting_seed import TENANT_A, seed


LISTING = ("board_member", "address_street", "address_house_number",
           "address_bus", "member_head_name", "member_partner_name",
           "member_total_count")


@pytest.fixture
def situation(db_session):
    gegevens = seed(db_session)
    bestuur = Person(tenant_id=TENANT_A, first_name="Anna", last_name="Bestuur")
    db_session.add(bestuur)
    db_session.flush()
    # H1, H2 and H3 are assigned; H4 deliberately is not.
    for sleutel in ("h1", "h2", "h3"):
        gezin = db_session.get(Member, gegevens["households"][sleutel])
        gezin.board_member_id = bestuur.id
    db_session.commit()
    gegevens["board_member_id"] = bestuur.id
    return gegevens


def _rows(db, extra_filters=()):
    sel = Selection(object_keys=LISTING, filters=tuple(extra_filters))
    return run_validated(db, sel, tenant_id=TENANT_A).rows


def test_the_report_is_shipped_and_readable(db_session, situation):
    rapport = next(r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                                 viewer="")
                   if r.builtin_key == "members_per_board_member")
    assert rapport.name == "Leden per bestuurslid"
    sel = selection_from_dict(rapport.selection)
    resultaat = run_validated(db_session, sel, tenant_id=TENANT_A)
    assert {"board_member", "address_street", "address_house_number",
            "member_head_name", "member_partner_name"} <= set(resultaat.rows[0])


def test_house_numbers_sort_naturally_and_not_alphabetically(db_session,
                                                             situation):
    """The trap this report walks into if nobody looks.

    The seed's street runs 2, 9, 10, 12A. Alphabetically that is 10, 12A, 2, 9 —
    a street shuffled in a way that reads as a data problem rather than a sorting
    one. Assert the natural order, and assert that it is *not* the alphabetical
    one, so the test still means something if both ever coincide by accident.
    """
    nummers = [row["address_house_number"] for row in _rows(db_session)
               if row["address_house_number"]]
    assert nummers == ["2", "9", "10", "12A"]
    assert nummers != sorted(nummers), (
        "als natuurlijke en alfabetische volgorde samenvallen, toetst deze test "
        "niets — kies dan andere nummers in de seed")


def test_the_pivot_orders_its_rows_naturally_too(db_session, situation):
    """The pivot sorts in Python, so the SQL order does not reach it.

    Two mechanisms, one result: the engine's ORDER BY for a table and a natural
    key for the pivot. Miss the second and the shipped report — a pivot, because
    it carries a subtotal per board member — comes back shuffled anyway. Run here
    without the valid-today filter, so all four house numbers are in play; the
    shipped selection itself is exercised by the tests above and below.
    """
    from app.domains.reporting.engine import Sort

    pivot = build_pivot(
        db_session,
        Selection(object_keys=LISTING, layout="pivot",
                  sort=(Sort("address_house_number"),)),
        tenant_id=TENANT_A)
    nummers = [rij.labels[2] for rij in pivot.rows
               if not rij.is_subtotal and rij.labels[2]]
    assert nummers == ["2", "9", "10", "12A"], f"gekregen: {nummers}"
    assert nummers != sorted(nummers), (
        "vallen natuurlijke en alfabetische volgorde samen, dan toetst deze test "
        "niets")


def test_a_second_partner_does_not_double_the_household(db_session, situation):
    """The grain is one row per household, and nothing forbids two partners.

    H3 already carries two rows with a partner relation type. Adding a third must
    change which name shows at most, never how many rows come back.
    """
    voor = _rows(db_session)
    extra = Person(tenant_id=TENANT_A, first_name="Extra", last_name="Partner")
    db_session.add(extra)
    db_session.flush()
    db_session.add(MemberPerson(tenant_id=TENANT_A,
                                member_id=situation["households"]["h1"],
                                person_id=extra.id, relation_type="PARTNER"))
    db_session.commit()

    na = _rows(db_session)
    assert len(na) == len(voor), (
        "een tweede partner mag het gezin niet verdubbelen")
    assert all(r["member_total_count"] == 1 for r in na), (
        "elke rij hoort precies één gezin te zijn")


def test_a_household_without_a_board_member_is_in_the_report(db_session,
                                                             situation):
    """For the voorzitter one of the most useful lines, so an INNER JOIN is out."""
    labels = {row["board_member"] for row in _rows(db_session)}
    assert "Niet toegewezen" in labels
    assert "Anna Bestuur" in labels


def test_the_scope_is_a_membership_valid_today_and_not_a_year(db_session,
                                                             situation):
    """H4 joins in October for next year: valid today, and not a member this year.

    That is the whole reason this filter is not `dit_jaar`. The two answers differ
    by exactly this household, and picking the wrong one is invisible until
    somebody counts.
    """
    from app.domains.reporting.engine import Filter, Operator

    binnen = _rows(db_session, [Filter("member_valid_today",
                                       Operator.EQ, ("Ja",))])
    alles = _rows(db_session)
    assert len(binnen) < len(alles), "de filter hoort iets weg te laten"

    h4_nummers = {r["address_house_number"] for r in binnen}
    assert "12A" not in h4_nummers, (
        "H4's lidmaatschap loopt pas volgend jaar, dus vandaag is het niet geldig")
    assert "12A" in {r["address_house_number"] for r in alles}


def test_the_head_and_the_partner_are_two_columns_on_one_row(db_session,
                                                             situation):
    """Koen asked for hoofdlid and partner side by side, not two rows."""
    rijen = {row["address_house_number"]: row for row in _rows(db_session)}
    h1 = rijen["2"]
    assert h1["member_head_name"] == "Persoon0 Test"
    assert h1["member_partner_name"] == "Persoon1 Test"
    # H2 is a household of one: a partner column that is empty, not absent.
    assert rijen["9"]["member_partner_name"] == ""


def test_children_are_not_in_the_report(db_session, situation):
    """H3 has three people. Two columns, so the third never shows."""
    kolommen = set(_rows(db_session)[0])
    assert not any("child" in k or "kind" in k for k in kolommen)
    h3 = next(r for r in _rows(db_session) if r["address_house_number"] == "10")
    assert h3["member_total_count"] == 1, "drie personen, één gezin, één rij"


def test_the_subtotal_per_board_member_counts_households(db_session, situation):
    """The count the voorzitter reads first, and it is not the sum of the page."""
    rapport = next(r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                                 viewer="")
                   if r.builtin_key == "members_per_board_member")
    pivot = build_pivot(db_session, selection_from_dict(rapport.selection),
                        tenant_id=TENANT_A)
    subtotalen = {rij.labels[0]: rij.total.get("member_total_count")
                  for rij in pivot.rows if rij.is_subtotal}
    gewone = [rij for rij in pivot.rows if not rij.is_subtotal]
    assert subtotalen, "meer dan één rijdimensie, dus er horen subtotalen te zijn"
    assert sum(subtotalen.values()) == len(gewone), (
        "elke rij is één gezin, dus de subtotalen tellen op tot het aantal rijen")


def test_the_address_columns_are_three_and_not_one(db_session, situation):
    """Composed into one string it sorts wrong — that is why they are split.

    Proof rather than assertion: sorting the composed labels puts 10 before 2.
    """
    rijen = _rows(db_session)
    samengesteld = [f"{r['address_street']} {r['address_house_number']}"
                    for r in rijen if r["address_house_number"]]
    assert sorted(samengesteld) != samengesteld, (
        "juist dit is de reden voor drie kolommen: als één tekst sorteert het "
        "adres alfabetisch en staat de straat door elkaar")
