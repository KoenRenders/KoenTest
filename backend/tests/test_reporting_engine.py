"""What the engine refuses, and why it says so (#832 tests 3 to 7, CR-06 §7).

Every test here asserts the **reason**, not the failure. `pytest.raises(
SelectionError)` alone would stay green if a selection were refused for the wrong
reason — a typo in a key passing as a missing measure, a fan trap passing as an
unjoinable dimension (#680: assert the reason, not a status).

Building is pure, so none of this needs a database: that is the point of keeping
`build_query` free of a session.

**There is no per-object role fence in v2.3.0** (decision of 10 September 2026):
the roles are declared in the universe and reporting sits behind
`require_admin_ui`. The tests at the bottom pin that down in both directions — the
declaration is complete, and it is not enforced — so that neither half can drift
without somebody noticing.
"""
from __future__ import annotations

import pytest

from app.domains.reporting.api import (
    FACTS,
    Direction,
    Filter,
    Format,
    MAX_ROWS,
    OBJECTS,
    ObjectKind,
    Operator,
    Role,
    Selection,
    SelectionError,
    Sort,
    build_query,
    classes_with_objects,
    objects_in_pane_order,
)


def plan(keys, *, tenant=2, **kwargs):
    return build_query(Selection(object_keys=tuple(keys), **kwargs),
                       tenant_id=tenant)


# ── Refusals ─────────────────────────────────────────────────────────────────

def test_an_unknown_object_is_refused_by_name():
    with pytest.raises(SelectionError) as exc:
        plan(["aantal_bananen", "payment_amount"])
    assert "Onbekend object" in str(exc.value)
    assert "aantal_bananen" in str(exc.value)


def test_measures_from_two_facts_are_refused_as_a_fan_trap():
    """#832 test 5. Both fact names in the message, so the user knows what to split."""
    with pytest.raises(SelectionError) as exc:
        plan(["activity", "registration_count", "payment_amount"])
    melding = str(exc.value)
    assert "Inschrijvingen" in melding and "Betalingen" in melding
    assert "vermenigvuldigen" in melding


def test_a_selection_without_a_measure_is_refused():
    with pytest.raises(SelectionError) as exc:
        plan(["activity", "date_year"])
    assert "minstens één maat" in str(exc.value)


def test_an_empty_selection_is_refused():
    with pytest.raises(SelectionError) as exc:
        plan([])
    assert "Kies eerst objecten" in str(exc.value)


def test_a_dimension_without_a_path_to_the_fact_is_refused():
    """`d_person` hangs off registrations, not off memberships."""
    with pytest.raises(SelectionError) as exc:
        plan(["person_age_group", "membership_households"])
    melding = str(exc.value)
    assert "Lidmaatschappen" in melding and "d_person" in melding


def test_the_date_dimension_does_not_reach_the_membership_fact():
    """A membership has a year, not a date — and the universe says so out loud.

    Silently joining `d_date` on 1 January would give every membership the month
    "januari", which is the kind of answer that looks right on a chart.
    """
    with pytest.raises(SelectionError) as exc:
        plan(["date_month", "membership_households"])
    assert "d_date" in str(exc.value)


def test_sorting_on_something_that_is_not_in_the_report_is_refused():
    with pytest.raises(SelectionError) as exc:
        plan(["payment_method", "payment_amount"],
             sort=(Sort("payment_status", Direction.ASC),))
    assert "'Betaalstatus'" in str(exc.value)


def test_filtering_on_a_measure_is_refused():
    with pytest.raises(SelectionError) as exc:
        plan(["payment_method", "payment_amount"],
             filters=(Filter("payment_amount", Operator.GT, ("10",)),))
    assert "'Te betalen'" in str(exc.value)


def test_a_filter_needs_the_right_number_of_values():
    with pytest.raises(SelectionError) as exc:
        plan(["payment_method", "payment_amount"],
             filters=(Filter("payment_method", Operator.BETWEEN, ("a",)),))
    assert "van- en een tot-waarde" in str(exc.value)

    with pytest.raises(SelectionError) as exc:
        plan(["payment_method", "payment_amount"],
             filters=(Filter("payment_method", Operator.IN, ()),))
    assert "geen waarden" in str(exc.value)


# ── What the built statement looks like ──────────────────────────────────────

def test_the_tenant_filter_is_always_there_and_always_a_parameter():
    built = plan(["payment_method", "payment_amount"])
    assert "f_payments.tenant_id = :tenant_id" in built.sql
    assert built.params["tenant_id"] == 2
    assert "f_payments.tenant_id = :tenant_id" in built.totals_sql


def test_every_join_matches_on_tenant_as_well():
    """CR-06 §2.4: a dimension row is never borrowed from another tenant."""
    built = plan(["activity", "payment_method", "payment_amount"])
    assert "d_activity.tenant_id = f_payments.tenant_id" in built.sql
    assert "d_payment_method.tenant_id = f_payments.tenant_id" in built.sql


def test_no_filter_value_ever_reaches_the_statement_text():
    """No free SQL (CR-06 §7.5), stated structurally rather than hoped for."""
    gevaarlijk = "Online'; DROP TABLE mdm.persons; --"
    built = plan(["payment_method", "payment_amount"],
                 filters=(Filter("payment_method", Operator.EQ, (gevaarlijk,)),))
    assert gevaarlijk not in built.sql
    assert "DROP" not in built.sql.upper()
    assert gevaarlijk in built.params.values()


def test_the_order_ends_in_the_grouping_which_is_the_unique_key():
    """#761: a default sort without a unique tail is not a sort."""
    built = plan(["payment_method", "payment_payable_type", "payment_amount"])
    order = built.sql.split("ORDER BY")[1]
    assert '"payment_method" ASC' in order
    assert '"payment_payable_type" ASC' in order


def test_an_explicit_sort_comes_first_and_the_tiebreaker_still_follows():
    built = plan(["payment_method", "payment_payable_type", "payment_amount"],
                 sort=(Sort("payment_payable_type", Direction.DESC),))
    order = built.sql.split("ORDER BY")[1].strip()
    assert order.startswith('"payment_payable_type" DESC')
    assert '"payment_method" ASC' in order
    assert order.count('"payment_payable_type"') == 1, (
        "een kolom hoort niet twee keer in de sortering te staan")


def test_a_report_is_capped_even_when_the_selection_asks_for_more():
    built = plan(["payment_method", "payment_amount"], limit=999_999)
    assert built.params["limit"] == MAX_ROWS


def test_the_totals_query_has_no_grouping_and_only_the_measures():
    built = plan(["payment_method", "payment_amount"])
    assert "GROUP BY" not in built.totals_sql
    assert '"payment_amount"' in built.totals_sql
    assert '"payment_method"' not in built.totals_sql


def test_a_drill_column_travels_next_to_its_label():
    built = plan(["activity", "payment_amount"])
    assert built.drill_aliases["activity"] == "activity__drill"
    assert '"activity__drill"' in built.sql
    assert "d_activity.activity_id" in built.sql.split("GROUP BY")[1]


def test_the_same_selection_builds_the_same_statement_twice():
    """A statement you cannot recognise in a log is a statement you cannot debug."""
    keys = ["activity", "date_year", "payment_method", "payment_amount"]
    assert plan(keys).sql == plan(keys).sql


# ── The declaration: complete, and deliberately not enforced ─────────────────

def test_every_object_is_offered_to_whoever_gets_through_the_door():
    """v2.3.0 adds no new security surface (#832, 10 September 2026).

    `require_admin_ui` is the whole fence. The objects pane therefore shows every
    object, and this test is the one that goes red if somebody re-introduces a
    half fence without also building — and testing — the switch.
    """
    pane = objects_in_pane_order()
    assert len(pane) == len(OBJECTS)
    assert {o.key for o in pane} == {o.key for o in OBJECTS}


def test_the_engine_takes_no_roles_at_all():
    """Stated on the signature, so it cannot be passed by accident."""
    import inspect

    parameters = set(inspect.signature(build_query).parameters)
    assert parameters == {"selection", "tenant_id"}


def test_every_money_measure_is_declared_finance():
    """#832 test 4: the declaration is what this release ships.

    CR-06 §2.5 puts money behind FINANCE. Adding a money measure and forgetting
    its role turns the build red here, so the declaration stays complete while the
    enforcement is still absent.
    """
    fouten = [f"{o.name} (`{o.key}`)" for o in OBJECTS
              if o.format is Format.MONEY and o.role is not Role.FINANCE]
    assert not fouten, f"geldmaten zonder de rol finance: {fouten}"


def test_the_payments_class_is_declared_finance_end_to_end():
    fouten = [o.key for o in OBJECTS
              if o.klass == "Betalingen" and o.role is not Role.FINANCE]
    assert not fouten, f"objecten in Betalingen zonder de rol finance: {fouten}"

    # A fact's role governs its flat dump, and a dump carries every column. The
    # three money facts therefore declare finance; the three that #841 added carry
    # no amount at all — a form submission and an open task are not money — so
    # they declare admin. The rule is "the strictest role any column needs", not
    # "finance everywhere".
    per_feit = {f.key: f.role for f in FACTS}
    assert per_feit["f_memberships"] is Role.FINANCE
    assert per_feit["f_registrations"] is Role.FINANCE
    assert per_feit["f_payments"] is Role.FINANCE
    assert per_feit["f_form_submissions"] is Role.ADMIN
    assert per_feit["f_tasks"] is Role.ADMIN
    assert per_feit["f_membership_persons"] is Role.ADMIN


def test_every_measure_and_detail_carries_a_role():
    fouten = [o.key for o in OBJECTS
              if o.kind in (ObjectKind.MEASURE, ObjectKind.DETAIL)
              and not isinstance(o.role, Role)]
    assert not fouten, f"maten of details zonder rol: {fouten}"


def test_the_objects_pane_is_grouped_in_declared_class_order():
    classes = [name for name, _objects in classes_with_objects()]
    assert classes == ["Leden", "Activiteiten", "Betalingen", "Betaaldetail",
                       "Formulieren", "Taken", "Tijd"]
    assert all(objects for _name, objects in classes_with_objects())
