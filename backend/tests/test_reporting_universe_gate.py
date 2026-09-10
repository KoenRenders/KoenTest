"""Universe gate (#832 test 6, CR-06 §4.3): the declaration resolves, both ways.

The universe is a promise about columns that live in views somebody else may
change. This gate makes a broken promise a red build with the object's name in the
message, instead of a 500 in front of a board member who picked the wrong object
by no fault of his own.

It works because the declaration cannot lie about its own sources: an object's SQL
is a template over `{view}`, so every column it touches is literally
`{view}.<column>` and can be extracted rather than believed.

**The counter-proof (#678).** Run against a live database:

- `ALTER TABLE ... ` is not possible on a view, so the break was done at the
  source: `DROP VIEW reporting.d_activity CASCADE` followed by a recreate without
  `activity_year`. `test_every_object_resolves_against_the_database` failed with
  *"Jaar van de activiteit (`activity_year`) verwijst naar d_activity.activity_year,
  die niet bestaat"*. Restored by re-running migration 096.
- Adding an object with `fact="f_nothing"` made
  `test_every_measure_belongs_to_a_fact_that_exists` fail by name.
- Deleting one line from `docs/reporting-universe.md` made
  `test_the_generated_document_matches_the_declaration` fail with the regenerate
  command in the message.
- The two privacy tests that used to live here were removed on 10 September 2026
  when CR-06 §7.3 changed; the comment where they stood explains why, and what
  guards the rule now. Their counter-proof at the time: recreating
  `reporting.d_person` with a `last_name` column, and separately adding an object
  whose SQL reads one, made each of them fail naming what it found.

And it refuses an empty scan: no objects, no joins or no views means the gate is
looking at the wrong thing, not that everything is fine.
"""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import text

from app.domains.reporting.docs import DOC_PATH, render
from app.domains.reporting.universe import (
    CLASSES,
    DIMENSIONS,
    FACTS,
    FACT_BY_KEY,
    JOINS,
    OBJECTS,
    ObjectKind,
    Role,
)

_COLUMN_REFERENCE = re.compile(r"\{view\}\.([a-z_][a-z0-9_]*)", re.IGNORECASE)


def _schema_columns(db) -> dict[str, set[str]]:
    rows = db.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'reporting'"))
    per_view: dict[str, set[str]] = {}
    for view, column in rows:
        per_view.setdefault(view, set()).add(column)
    return per_view


def test_the_gate_has_something_to_check(db_session):
    """Nothing declared and nothing in the database reads the same as "all fine"."""
    assert len(OBJECTS) >= 30, f"de universe telt {len(OBJECTS)} objecten"
    assert len(JOINS) >= 10, f"de joingraaf telt {len(JOINS)} verbanden"
    assert len(_schema_columns(db_session)) >= 10, (
        "geen weergaven gevonden in schema 'reporting' — draaide de migratie?")


def test_every_object_resolves_against_the_database(db_session):
    """Every `{view}.column` an object names exists in that view."""
    per_view = _schema_columns(db_session)
    fouten = []
    for obj in OBJECTS:
        columns = per_view.get(obj.view)
        if columns is None:
            fouten.append(f"{obj.name} (`{obj.key}`) verwijst naar de weergave "
                          f"{obj.view}, die niet bestaat")
            continue
        for source in (obj.sql, obj.drill_sql or ""):
            for column in _COLUMN_REFERENCE.findall(source):
                if column not in columns:
                    fouten.append(
                        f"{obj.name} (`{obj.key}`) verwijst naar "
                        f"{obj.view}.{column}, die niet bestaat")
    assert not fouten, "objecten wijzen naar kolommen die er niet zijn:\n" + \
        "\n".join(sorted(fouten))


def test_every_object_names_at_least_one_column(db_session):
    """An object whose SQL touches no column of its view is a constant.

    Without this rule a typo like `sum(amount)` — without the `{view}.` prefix —
    would slip past the resolver above, because there is nothing left to resolve.
    """
    fouten = [f"{obj.name} (`{obj.key}`)" for obj in OBJECTS
              if not _COLUMN_REFERENCE.findall(obj.sql)]
    assert not fouten, ("elk object noemt minstens één {view}.kolom, anders kan de "
                        f"gate hem niet toetsen: {fouten}")


def test_every_measure_belongs_to_a_fact_that_exists():
    """A measure decides the grain, so it must say which fact it aggregates."""
    fouten = []
    for obj in OBJECTS:
        if obj.kind is not ObjectKind.MEASURE:
            continue
        if not obj.fact:
            fouten.append(f"{obj.name} (`{obj.key}`) noemt geen feit")
        elif obj.fact not in FACT_BY_KEY:
            fouten.append(f"{obj.name} (`{obj.key}`) noemt het onbekende feit "
                          f"{obj.fact}")
        elif obj.view != obj.fact:
            fouten.append(f"{obj.name} (`{obj.key}`) aggregeert {obj.view} maar "
                          f"hoort bij feit {obj.fact}")
    assert not fouten, "\n".join(fouten)


def test_every_object_declared_on_a_fact_names_that_fact():
    """A degenerate dimension lives on the fact, and has to admit it.

    Without the `fact` field the engine would treat `component_name` as a
    dimension view and look for a join that cannot exist.
    """
    fact_keys = set(FACT_BY_KEY)
    fouten = [f"{obj.name} (`{obj.key}`)" for obj in OBJECTS
              if obj.view in fact_keys and obj.fact != obj.view]
    assert not fouten, ("objecten op een feitweergave moeten dat feit noemen: "
                        f"{fouten}")


def test_every_join_key_exists(db_session):
    per_view = _schema_columns(db_session)
    fouten = []
    for join in JOINS:
        for view in (join.fact, join.dimension):
            if view not in per_view:
                fouten.append(f"join {join.fact} -> {join.dimension}: "
                              f"{view} bestaat niet")
        for fact_column, dim_column in join.pairs:
            if fact_column not in per_view.get(join.fact, set()):
                fouten.append(f"join {join.fact} -> {join.dimension}: "
                              f"{join.fact}.{fact_column} bestaat niet")
            if dim_column not in per_view.get(join.dimension, set()):
                fouten.append(f"join {join.fact} -> {join.dimension}: "
                              f"{join.dimension}.{dim_column} bestaat niet")
    assert not fouten, "\n".join(sorted(fouten))


def test_every_dimension_can_identify_its_own_row(db_session):
    """#761 again: the tiebreaker has to exist before it can be appended."""
    per_view = _schema_columns(db_session)
    fouten = [f"{dim.key}.{dim.key_column}" for dim in DIMENSIONS
              if dim.key_column not in per_view.get(dim.key, set())]
    assert not fouten, f"sleutelkolommen die niet bestaan: {fouten}"


def test_every_people_count_resolves_too(db_session):
    """The small-cell threshold reads `Fact.people_sql`, so it is a source as well.

    Without this the threshold could point at a column that no longer exists and
    fail at the moment a privacy rule was supposed to apply — the worst possible
    moment for a query to break.
    """
    per_view = _schema_columns(db_session)
    fouten = []
    for fact in FACTS:
        if not fact.people_sql:
            continue
        kolommen = _COLUMN_REFERENCE.findall(fact.people_sql)
        assert kolommen, f"{fact.key}: people_sql noemt geen {{view}}.kolom"
        for kolom in kolommen:
            if kolom not in per_view.get(fact.key, set()):
                fouten.append(f"{fact.key}.{kolom}")
    assert not fouten, f"people_sql wijst naar kolommen die er niet zijn: {fouten}"


def test_every_fact_can_identify_its_own_row(db_session):
    per_view = _schema_columns(db_session)
    fouten = []
    for fact in FACTS:
        assert fact.dataset_key, f"{fact.key} heeft geen dataset_key"
        for column in fact.dataset_key:
            if column not in per_view.get(fact.key, set()):
                fouten.append(f"{fact.key}.{column}")
    assert not fouten, f"sleutelkolommen die niet bestaan: {fouten}"


def test_keys_are_unique_and_names_are_unique_within_a_class():
    """A duplicate key silently shadows an object; a duplicate name confuses a user."""
    keys = [o.key for o in OBJECTS]
    assert len(keys) == len(set(keys)), "dubbele objectsleutels"
    per_class: dict[str, list[str]] = {}
    for obj in OBJECTS:
        per_class.setdefault(obj.klass, []).append(obj.name)
    for klass, names in per_class.items():
        assert len(names) == len(set(names)), f"dubbele objectnamen in {klass}"


def test_every_object_sits_in_a_declared_class_and_carries_a_role():
    fouten = []
    for obj in OBJECTS:
        if obj.klass not in CLASSES:
            fouten.append(f"{obj.key}: onbekende klasse {obj.klass}")
        if not isinstance(obj.role, Role):
            fouten.append(f"{obj.key}: geen geldige rol")
        if not obj.description.strip():
            fouten.append(f"{obj.key}: geen beschrijving voor de tooltip")
    assert not fouten, "\n".join(fouten)


# ── Where the person fence moved to (CR-06 §7.3, 10 September 2026) ─────────
#
# Two tests stood here and they are gone on purpose, so this comment is the
# record of why — in half a year "the privacy test was deleted" must not be the
# whole story anybody can find.
#
# They were `test_no_object_reads_a_name_or_a_contact_column` and
# `test_the_person_dimension_does_not_even_offer_a_name`, and they enforced CR-06
# §7.3 as it read until 10 September 2026: *a count is a report, a list of people
# is a screen*. Koen reversed that rule. **Person-level data is allowed in the
# universe**, and the reason it is defensible is not that names became less
# sensitive — it is that the whole reporting screen sits behind
# `require_admin_ui`. Only ADMIN and OPERATOR reach it, and those are the same
# roles that already open the member screens and already export those names. The
# universe therefore reveals nothing to anybody who could not already see it.
#
# **Which makes the role boundary the thing that now has to be guarded**, and the
# test below is that guard. It is a condition and not a free hand: the day
# "Rapporten" opens to another role — FINANCE-only is already on the table in
# §5.1 — the per-object fence has to exist *first*, or that switch hands names to
# a role that does not have them today.
#
# The threshold of five stays and keeps its honest scope: it protects a GROUPED
# result from a group of one naming itself. It does not protect a row list, which
# identifies people by construction. That is what the role boundary is for.

_ADMIN_UI = (Path(__file__).resolve().parents[1] / "app" / "domains" / "reporting"
             / "admin_ui.py")
_REPORTING_UI = _ADMIN_UI.read_text(encoding="utf-8")


def test_every_reporting_route_sits_behind_require_admin_ui():
    """The whole fence, in one place — CR-06 §7.3 leans on exactly this.

    Every route in the reporting UI is ADMIN/OPERATOR only, whether it renders a
    screen, a fragment or a spreadsheet. A route that slipped out from behind
    that door would hand names to whoever could reach it, because the universe no
    longer keeps them out.

    Counter-proof: replacing one `require_admin_ui` with `require_finance_ui`
    made this fail naming that route; restored afterwards.
    """
    import re

    routes = re.findall(r'@router\.(?:get|post)\((.*?)\)\n(?:async )?def (\w+)',
                        _REPORTING_UI, re.S)
    assert len(routes) >= 8, (
        f"deze gate vond {len(routes)} routes in admin_ui.py — leest ze het goede "
        "bestand? (#678)")

    fouten = []
    for decorator, naam in routes:
        # The door is either on the decorator or on the signature; both count.
        signatuur = _REPORTING_UI.split(f"def {naam}(", 1)[1].split("):", 1)[0]
        if "require_admin_ui" not in decorator and "require_admin_ui" not in signatuur:
            fouten.append(naam)
        for zwakker in ("require_finance_ui", "require_operator_ui"):
            if zwakker in decorator or zwakker in signatuur:
                fouten.append(f"{naam} gebruikt {zwakker}")
    assert not fouten, (
        "elke rapportageroute hoort achter require_admin_ui (CR-06 §7.3): "
        f"{fouten}")


def test_no_per_object_role_fence_has_quietly_appeared():
    """The other half of §7.3: the switch is not half-built.

    The roles on objects are a declaration until somebody builds the fence and
    tests it. Half a fence is worse than none — it suggests a protection that is
    not there — so `build_query` takes no roles, and this says so on the
    signature where it cannot be passed by accident.
    """
    import inspect

    from app.domains.reporting.api import build_query

    assert set(inspect.signature(build_query).parameters) == {"selection", "tenant_id"}


def test_every_object_still_declares_its_role():
    """The declaration has to stay complete, precisely because it is not enforced.

    It is what the later switch will be built on. A person-level detail that
    forgets `member_details` would be invisible to that switch and would stay
    readable for a role that should not have it.
    """
    fouten = [o.key for o in OBJECTS if not isinstance(o.role, Role)]
    assert not fouten, f"objecten zonder rol: {fouten}"

    # This used to also demand that a `member_details` object be a DETAIL and
    # never a DIMENSION — "you do not group by a name". #849 is the case that
    # shows the rule was too wide: grouping households by their responsible board
    # member is the whole point of that report, and the name is what a reader
    # recognises. Grouping by a person's name is a report about the STAFF member
    # who carries the households, not about the households' members.
    #
    # What still has to hold is that such an object declares the role, so the
    # later per-object switch (CR-06 §5.1) has something to turn on. That is the
    # assertion above, and it is the one that matters.
    persoonlijk = [o for o in OBJECTS if o.role is Role.MEMBER_DETAILS]
    assert persoonlijk, "de rol member_details hoort ergens gebruikt te worden"


def test_a_drill_target_comes_with_the_sql_that_produces_it():
    fouten = [o.key for o in OBJECTS if bool(o.drill) != bool(o.drill_sql)]
    assert not fouten, f"doorklik zonder bron of omgekeerd: {fouten}"


def test_the_generated_document_matches_the_declaration():
    """`docs/reporting-universe.md` is rendered, never written (CR-06 §4.3)."""
    assert DOC_PATH.exists(), f"{DOC_PATH} bestaat niet"
    op_schijf = DOC_PATH.read_text(encoding="utf-8")
    assert op_schijf == render(), (
        "docs/reporting-universe.md loopt niet gelijk met universe.py. "
        "Draai: python -m app.domains.reporting.docs")
