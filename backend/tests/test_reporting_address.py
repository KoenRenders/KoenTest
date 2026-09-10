"""The address dimension, and the grain it stands or falls on (#850).

Koen wanted the address as a dimension of its own rather than a block of columns
on the household, because *"je kan er zeker van zijn dat adressen ooit ook buiten
members gaan terugkomen"*. The data model is untouched: an address still hangs off
a person.

**The grain is one live address per person, and the database says so — partially.**
`uq_addresses_person_id` (migration 053) is `UNIQUE (person_id) WHERE deleted_at IS
NULL`. So the constraint does not stop a person from having three addresses; it
stops them from having two *undeleted* ones. Somebody who has moved twice leaves
rows behind, and the entire grain of `d_address` rests on its `WHERE a.deleted_at
IS NULL` matching that predicate exactly.

**So the gate is not "are the rows unique today" — the index answers that.** The
gate is: does the view still filter the same way the index does? A test that only
counted rows would be green forever, because the constraint keeps it green while
the view can be broken independently.

**The counter-proof was run, not described.** `d_address` was replaced by the same
view with `WHERE a.deleted_at IS NULL` removed — the single line at issue — and
`test_the_grain_is_one_address_per_person` went red naming the person and the two
addresses; the migration's SQL was put back and it went green. That is what
`test_the_gate_goes_red_when_the_view_forgets_soft_delete` reproduces on every run,
so the gate can never quietly become a green statement about nothing.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from app.domains.mdm.api import Address, PostalCode
from app.domains.reporting.api import Selection, build_query, run_validated
from tests._reporting_seed import TENANT_A, TENANT_B, seed


def _migration():
    """The migration module, so the view SQL lives in exactly one place."""
    pad = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
           / "108_reporting_address_dimension.py")
    spec = importlib.util.spec_from_file_location("m108", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _grain_violations(db) -> list[tuple[int, int]]:
    """(person_id, aantal) for every person with more than one address row."""
    return [(row[0], row[1]) for row in db.execute(text(
        "SELECT person_id, COUNT(*) FROM reporting.d_address "
        "GROUP BY person_id HAVING COUNT(*) > 1 ORDER BY person_id"))]


def _move_house(db, person_id: int) -> None:
    """What a move looks like in the data: the old address soft-deleted, a new one.

    The partial index allows exactly this, so it is the situation the view has to
    survive — and the one it would fail if it stopped filtering.
    """
    db.execute(text("UPDATE mdm.addresses SET deleted_at = NOW() "
                    "WHERE person_id = :p AND deleted_at IS NULL"), {"p": person_id})
    pc = db.query(PostalCode).first()
    db.add(Address(tenant_id=TENANT_A, person_id=person_id, street="Nieuwstraat",
                   house_number="7", postal_code_id=pc.id))
    db.commit()


def test_the_grain_is_one_address_per_person(db_session, situation):
    """The gate this issue rests on, checked on a person who has moved.

    An unmoved seed proves nothing here: the unique index would hold the line
    whatever the view does. Only a soft-deleted address makes the view's own
    filter the thing being tested.
    """
    persoon = db_session.execute(text(
        "SELECT person_id FROM reporting.d_address WHERE tenant_id = :t "
        "ORDER BY person_id LIMIT 1"), {"t": TENANT_A}).scalar()
    assert persoon, "de seed geeft minstens één persoon met een adres"
    _move_house(db_session, persoon)

    fouten = _grain_violations(db_session)
    assert not fouten, (
        "d_address hoort één rij per persoon te zijn, anders vermenigvuldigt een "
        f"join de feiten eronder; personen met meer dan één adres: {fouten}")


def test_the_gate_goes_red_when_the_view_forgets_soft_delete(db_session, situation):
    """The counter-proof, run here rather than asserted in a comment.

    What was broken: the line `WHERE a.deleted_at IS NULL` at the bottom of
    `D_ADDRESS` in migration 108. Nothing else — same columns, same joins. With
    it gone, a person who has moved once appears twice and the grain check names
    them; putting the migration's own SQL back makes it green again.
    """
    persoon = db_session.execute(text(
        "SELECT person_id FROM reporting.d_address WHERE tenant_id = :t "
        "ORDER BY person_id LIMIT 1"), {"t": TENANT_A}).scalar()
    _move_house(db_session, persoon)
    m = _migration()
    assert "WHERE a.deleted_at IS NULL" in m.D_ADDRESS, (
        "de weergave hoort die filter te dragen; verdwijnt hij, dan gaat deze "
        "test over iets anders dan ze belooft")

    try:
        db_session.execute(text(
            m.D_ADDRESS.replace("WHERE a.deleted_at IS NULL", "")))
        db_session.commit()
        fouten = _grain_violations(db_session)
        assert (persoon, 2) in fouten, (
            "zonder de soft-delete-filter hoort de korrelgate deze persoon te "
            "noemen — doet hij dat niet, dan bewijst de gate niets")
    finally:
        db_session.execute(text(m.D_ADDRESS))
        db_session.commit()

    assert not _grain_violations(db_session), "en met de echte weergave is hij groen"


def test_a_broken_grain_would_inflate_an_additive_measure(db_session, situation):
    """Why the grain matters, shown as the damage instead of as a rule.

    The failure this prevents is not an error message. It is a number that stays
    a number and stops being the right one.
    """
    def totaal() -> int:
        resultaat = run_validated(
            db_session,
            Selection(object_keys=("address_municipality", "registration_quantity")),
            tenant_id=TENANT_A)
        return sum(r.get("registration_quantity") or 0 for r in resultaat.rows)

    persoon = db_session.execute(text(
        "SELECT r.person_id FROM activities.registrations r "
        "JOIN mdm.addresses a ON a.person_id = r.person_id AND a.deleted_at IS NULL "
        "WHERE r.tenant_id = :t LIMIT 1"), {"t": TENANT_A}).scalar()
    assert persoon, "de seed geeft een inschrijver met een adres"
    goed = totaal()
    assert goed > 0, "er valt iets te tellen, anders meet deze test niets"

    _move_house(db_session, persoon)
    m = _migration()
    try:
        db_session.execute(text(
            m.D_ADDRESS.replace("WHERE a.deleted_at IS NULL", "")))
        db_session.commit()
        assert totaal() > goed, (
            "een dubbele adresrij hoort de som op te blazen — precies de schade "
            "die de korrelgate tegenhoudt")
    finally:
        db_session.execute(text(m.D_ADDRESS))
        db_session.commit()

    assert totaal() == goed, "met de echte weergave klopt de som weer"


def test_the_address_hangs_off_the_person_and_not_off_the_household(db_session,
                                                                    situation):
    """Chaining it to the household would count a household per resident.

    Migration 044 keeps the address on the hoofdlid, so today the two grains
    coincide — but that is a rule in the write path, not a constraint, and one
    non-hoofdlid with an address is enough. Giving the seed's first family a
    second addressed member must not move a household-grain number.
    """
    def gezinnen() -> int:
        return run_validated(
            db_session, Selection(object_keys=("membership_households",)),
            tenant_id=TENANT_A).rows[0]["membership_households"]

    voor = gezinnen()
    tweede_bewoner = db_session.execute(text(
        "SELECT mp.person_id FROM mdm.member_persons mp "
        "WHERE mp.member_id = :m AND mp.relation_type <> 'HOOFDLID' "
        "  AND mp.deleted_at IS NULL LIMIT 1"),
        {"m": situation["households"]["h1"]}).scalar()
    assert tweede_bewoner, "de seed geeft een gezin met meer dan één persoon"

    pc = db_session.query(PostalCode).first()
    db_session.add(Address(tenant_id=TENANT_A, person_id=tweede_bewoner,
                           street="Andere straat", house_number="3",
                           postal_code_id=pc.id))
    db_session.commit()

    assert gezinnen() == voor, (
        "een tweede bewoner met een adres verandert het aantal gezinnen niet")
    assert not _grain_violations(db_session), "en de korrel is niet geschonden"


def test_the_address_reaches_the_universe_through_the_person(db_session, situation):
    """fact → d_person → d_address, the second chained join in the universe."""
    from app.domains.reporting.api import build_query

    plan = build_query(
        Selection(object_keys=("address_municipality", "registration_count")),
        tenant_id=TENANT_A)
    joins = plan.sql[plan.sql.index("FROM"):]
    assert "reporting.d_person" in joins and "reporting.d_address" in joins
    assert joins.index("reporting.d_person") < joins.index("reporting.d_address"), (
        "de ouder hoort vóór het kind te staan, anders joint d_address op een "
        "alias die nog niet bestaat")

    resultaat = run_validated(
        db_session,
        Selection(object_keys=("address_municipality", "registration_count")),
        tenant_id=TENANT_A)
    assert resultaat.rows, "de geketende join levert rijen"


def test_grouping_by_address_is_guarded_like_its_household_twin(db_session,
                                                                situation):
    """Municipality on person grain is no less identifying than on household grain.

    On a seed this small every group falls under the threshold, which is the point:
    the merged label proves the guard is armed for this dimension too.
    """
    from app.domains.reporting.service import MERGED_LABEL

    resultaat = run_validated(
        db_session,
        Selection(object_keys=("address_municipality", "registration_count")),
        tenant_id=TENANT_A)
    assert any(r["address_municipality"] == MERGED_LABEL for r in resultaat.rows)


def test_the_address_carries_the_reference_to_the_household(db_session, situation):
    """Koen asked for a dimension that REFERS to the household, and it does."""
    kolommen = {row[0] for row in db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'reporting' AND table_name = 'd_address'"))}
    assert "member_id" in kolommen
    assert {"street", "house_number", "bus_number", "address_line",
            "postal_code", "municipality"} <= kolommen


def test_addresses_stay_inside_their_tenant(db_session, situation):
    a = db_session.execute(text(
        "SELECT COUNT(*) FROM reporting.d_address WHERE tenant_id = :t"),
        {"t": TENANT_A}).scalar()
    b = db_session.execute(text(
        "SELECT COUNT(*) FROM reporting.d_address WHERE tenant_id = :t"),
        {"t": TENANT_B}).scalar()
    assert a >= 1 and b >= 1, "beide tenants hebben adressen uit de seed"


def test_the_household_view_still_carries_postcode_and_municipality(db_session):
    """#850 is not a clean-up: saved reports use these and they stay.

    They answer a different question — a household counts once there and once per
    addressed resident here — and the universe descriptions say so.
    """
    kolommen = {row[0] for row in db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'reporting' AND table_name = 'd_member'"))}
    assert {"postal_code", "municipality"} <= kolommen


def test_someone_without_an_address_does_not_fall_out_of_the_report(db_session,
                                                                    situation):
    """The INNER JOIN trap of #849, checked on this dimension too.

    Only the hoofdlid carries the household address (migration 044), so most
    people have none — an inner join here would drop the majority of the rows and
    the report would look tidy while being wrong. The join is LEFT and the missing
    side reads 'Geen adres', not an empty cell that reads like a rendering fault.
    """
    zonder = run_validated(
        db_session,
        Selection(object_keys=("address_line", "registration_count")),
        tenant_id=TENANT_A)
    met = run_validated(
        db_session, Selection(object_keys=("registration_count",)),
        tenant_id=TENANT_A)

    assert "LEFT JOIN reporting.d_address" in build_query(
        Selection(object_keys=("address_municipality", "registration_count")),
        tenant_id=TENANT_A).sql

    verdeeld = sum(r.get("registration_count") or 0 for r in zonder.rows)
    assert verdeeld == met.rows[0]["registration_count"], (
        "opsplitsen per adres mag geen inschrijving laten verdwijnen")
    assert any(r["address_line"] == "Geen adres" for r in zonder.rows), (
        "de seed heeft inschrijvers zonder adres, en die horen een leesbaar "
        "etiket te krijgen in plaats van een lege cel")


def test_both_roads_to_a_municipality_count_the_same_households(db_session,
                                                                situation):
    """Via `d_address` and via `d_member` — the same total, a different split.

    The issue asks whether both roads to a municipality reach the same total, and
    they do. The distribution does not match, and that is not a fault: on the
    household road a member sits under their household's municipality, on the
    address road only the hoofdlid carries an address, so everybody else lands
    under 'Geen adres'.

    The measure is deliberately the **additive** one. `COUNT(DISTINCT person_id)`
    survives a duplicated join row and would have called this test green through
    exactly the fault it exists to catch; `COUNT(person_id)` notices both a
    multiplication and a loss. The totals row is computed in SQL over the whole
    set, so it is unaffected by the small-cell guard folding the visible rows.
    """
    def totaal(dimensie: str) -> int:
        return run_validated(
            db_session,
            Selection(object_keys=(dimensie, "membership_person_count")),
            tenant_id=TENANT_A).totals["membership_person_count"]

    via_gezin = totaal("member_municipality")
    via_adres = totaal("address_municipality")
    assert via_gezin == via_adres, (
        "wijken de totalen af, dan vermenigvuldigt of verliest de join leden "
        f"— via gezin {via_gezin}, via adres {via_adres}")
