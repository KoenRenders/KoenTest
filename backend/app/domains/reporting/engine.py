"""The engine: one selection in, one SQL query out (CR-06 §2.2, §7).

A report is a *selection* — which objects, which filters, which sort — and never a
query. This module turns such a selection into exactly one statement over the
``reporting`` views: it resolves the joins from the universe's graph, aggregates
the measures, groups by everything else, and adds the tenant filter and the role
fence itself so that no caller can forget them.

**Everything that ends up in the SQL comes from the universe declaration; every
value a user typed becomes a bind parameter.** That is the whole of "no free SQL,
ever" (CR-06 §7.5): object keys are looked up, unknown ones are refused before a
query runs, and filter values never touch the statement text.

**No per-object role fence in this release** (decision of 10 September 2026, #832):
reporting sits behind `require_admin_ui` like every other admin screen, and the
roles in the universe are a declaration of what must hold once that switch is
built. Half a fence would suggest a protection that is not there. The tenant
filter is a different matter and is applied unconditionally, here, on every
statement.

**Building is pure.** ``build_query`` takes no session and reads no database, so
the refusals — an unknown object, a role that is not granted, measures from two
facts — are provable without one, and the service layer decides when to execute.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.domains.reporting.universe import (
    BY_KEY,
    FACT_BY_KEY,
    ObjectKind,
    UniverseObject,
    joins_for,
)


class SelectionError(ValueError):
    """A selection the universe refuses, with the reason in the message.

    Not an ``HTTPException``: the rule belongs to the engine, not to the door. The
    route turns it into a 422 with this text; a script may do something else with
    it. Every message names the object or the fact it is about — a refusal that
    only says "not allowed" costs the reader a search (#680).
    """


class Operator(str, Enum):
    """The comparisons a filter may use. Anything else is refused by name."""

    EQ = "eq"
    NE = "ne"
    IN = "in"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    BETWEEN = "between"
    CONTAINS = "contains"


class Direction(str, Enum):
    ASC = "asc"
    DESC = "desc"


_SQL_OPERATOR = {
    Operator.EQ: "=",
    Operator.NE: "<>",
    Operator.LT: "<",
    Operator.LTE: "<=",
    Operator.GT: ">",
    Operator.GTE: ">=",
}


@dataclass(frozen=True)
class Filter:
    """One condition on one object."""

    object_key: str
    operator: Operator
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class Sort:
    object_key: str
    direction: Direction = Direction.ASC


@dataclass(frozen=True)
class Selection:
    """What the user composed. Data, not a query — this is what gets saved."""

    object_keys: tuple[str, ...]
    filters: tuple[Filter, ...] = ()
    sort: tuple[Sort, ...] = ()
    limit: int = 200
    offset: int = 0


@dataclass
class Column:
    """One column of the result, as the panel and the export need it."""

    key: str
    name: str
    kind: ObjectKind
    format: str
    drill: str | None = None


@dataclass
class QueryPlan:
    """The built statement plus everything the caller needs to read its result."""

    sql: str
    totals_sql: str
    params: dict[str, object]
    columns: list[Column]
    fact: str
    # Column aliases that carry a drill target next to their label.
    drill_aliases: dict[str, str] = field(default_factory=dict)


# A hard ceiling on what one report may return. At this scale it never fires; it
# is here for the day a selection is wrong (CR-06 §7.7).
MAX_ROWS = 5000


def _object(key: str) -> UniverseObject:
    obj = BY_KEY.get(key)
    if obj is None:
        raise SelectionError(f"Onbekend object: '{key}'.")
    return obj


def _resolve_fact(objects: list[UniverseObject]) -> str:
    """Which fact this selection is about — and the fan-trap refusal (CR-06 §2.6).

    Measures from two facts in one query multiply each other: three registrations
    and two payments for the same activity give six rows, and every sum is wrong by
    a factor nobody notices. BusinessObjects calls it a fan trap; here it is simply
    refused, by name, until multi-fact synchronisation exists.
    """
    facts = {o.fact for o in objects if o.is_measure and o.fact}
    if not facts:
        raise SelectionError(
            "Kies minstens één maat: zonder maat weet het rapport niet op welk "
            "detailniveau het moet tellen."
        )
    if len(facts) > 1:
        namen = sorted(FACT_BY_KEY[f].name for f in facts)
        raise SelectionError(
            "Maten uit twee feiten in één rapport kunnen niet: "
            f"{' en '.join(namen)}. De aantallen zouden elkaar vermenigvuldigen. "
            "Maak er twee rapporten van."
        )
    return facts.pop()


def _view_alias(view: str) -> str:
    """The alias a view gets in the statement. Its own name — no ``t1``/``t2``."""
    return view


def _expression(obj: UniverseObject) -> str:
    return obj.sql.format(view=_view_alias(obj.view))


def _drill_expression(obj: UniverseObject) -> str | None:
    if not obj.drill_sql:
        return None
    return obj.drill_sql.format(view=_view_alias(obj.view))


def _needed_views(objects: list[UniverseObject], fact: str) -> list[str]:
    """The dimension views this selection reaches, in a stable order.

    Stable because the statement must be byte-for-byte the same for the same
    selection: a query that changes shape between two runs is a query you cannot
    reason about from a log.
    """
    seen: list[str] = []
    for obj in objects:
        if obj.view != fact and obj.view not in seen:
            seen.append(obj.view)
    return sorted(seen)


def _check_joinable(views: list[str], fact: str) -> dict[str, object]:
    available = joins_for(fact)
    for view in views:
        if view not in available:
            raise SelectionError(
                f"'{FACT_BY_KEY[fact].name}' heeft geen verband met de dimensie "
                f"'{view}'. Kies objecten die bij hetzelfde feit horen."
            )
    return {v: available[v] for v in views}


def _from_clause(fact: str, views: list[str], joins: dict) -> str:
    lines = [f"reporting.{fact} AS {_view_alias(fact)}"]
    for view in views:
        join = joins[view]
        alias = _view_alias(view)
        # tenant_id is part of EVERY join, unconditionally: without it a dimension
        # row could be borrowed from another tenant even though the fact is
        # filtered correctly. That is the classic leak this design refuses to make
        # a habit (CR-06 §2.4).
        conditions = [f"{alias}.tenant_id = {_view_alias(fact)}.tenant_id"]
        conditions += [
            f"{alias}.{dim_col} = {_view_alias(fact)}.{fact_col}"
            for fact_col, dim_col in join.pairs
        ]
        lines.append(f"LEFT JOIN reporting.{view} AS {alias} ON " + " AND ".join(conditions))
    return "\n".join(lines)


def _where_clause(filters: tuple[Filter, ...],
                  fact: str) -> tuple[list[str], dict[str, object], list[UniverseObject]]:
    """Conditions plus their bind parameters. Values never enter the SQL text."""
    conditions = [f"{_view_alias(fact)}.tenant_id = :tenant_id"]
    params: dict[str, object] = {}
    used: list[UniverseObject] = []

    for index, flt in enumerate(filters):
        obj = _object(flt.object_key)
        if obj.is_measure:
            raise SelectionError(
                f"Op de maat '{obj.name}' kun je niet filteren. Filter op een "
                "dimensie, of laat de maat weg."
            )
        used.append(obj)
        expr = _expression(obj)
        name = f"f{index}"

        if flt.operator is Operator.IN:
            if not flt.values:
                raise SelectionError(
                    f"Het filter op '{obj.name}' heeft geen waarden."
                )
            placeholders = []
            for i, value in enumerate(flt.values):
                key = f"{name}_{i}"
                params[key] = value
                placeholders.append(f":{key}")
            conditions.append(f"{expr} IN ({', '.join(placeholders)})")
        elif flt.operator is Operator.BETWEEN:
            if len(flt.values) != 2:
                raise SelectionError(
                    f"Het filter op '{obj.name}' verwacht een van- en een tot-waarde."
                )
            params[f"{name}_van"] = flt.values[0]
            params[f"{name}_tot"] = flt.values[1]
            conditions.append(f"{expr} BETWEEN :{name}_van AND :{name}_tot")
        elif flt.operator is Operator.CONTAINS:
            if len(flt.values) != 1:
                raise SelectionError(
                    f"Het filter op '{obj.name}' verwacht één zoekterm."
                )
            params[name] = f"%{flt.values[0]}%"
            conditions.append(f"CAST({expr} AS text) ILIKE :{name}")
        else:
            if len(flt.values) != 1:
                raise SelectionError(
                    f"Het filter op '{obj.name}' verwacht één waarde."
                )
            params[name] = flt.values[0]
            conditions.append(f"{expr} {_SQL_OPERATOR[flt.operator]} :{name}")

    _check_joinable([o.view for o in used if o.view != fact], fact)
    return conditions, params, used


def build_query(selection: Selection, *, tenant_id: int) -> QueryPlan:
    """Build the one statement this selection means.

    Refuses, in this order and always by name: an unknown object, a selection
    without a measure, measures from two facts, and a dimension that has no path
    to the fact. The order matters for the message: "unknown object" is more
    useful than "not joinable" for a typo.
    """
    if not selection.object_keys:
        raise SelectionError("Kies eerst objecten voor je rapport.")

    objects = [_object(key) for key in selection.object_keys]

    # No role check on the fact itself: the fence sits on the objects, and a
    # selection cannot exist without a measure, so every fact a report reaches is
    # reached through a measure that was already checked. `Fact.role` governs the
    # flat dataset dump, where there is no selection to check.
    fact = _resolve_fact(objects)

    conditions, params, filter_objects = _where_clause(selection.filters, fact)
    views = _needed_views(objects + filter_objects, fact)
    joins = _check_joinable(views, fact)

    grouped = [o for o in objects if not o.is_measure]
    measures = [o for o in objects if o.is_measure]

    select_parts: list[str] = []
    drill_aliases: dict[str, str] = {}
    for obj in objects:
        select_parts.append(f'{_expression(obj)} AS "{obj.key}"')
        drill_expr = _drill_expression(obj)
        if drill_expr is not None:
            alias = f"{obj.key}__drill"
            select_parts.append(f'{drill_expr} AS "{alias}"')
            drill_aliases[obj.key] = alias

    from_clause = _from_clause(fact, views, joins)
    where = "\n  AND ".join(conditions)

    group_by = [_expression(o) for o in grouped]
    group_by += [d for d in (_drill_expression(o) for o in grouped) if d]

    # #761: the default sort ends in a unique key. Appending every grouping
    # expression is exactly that — a group-by set identifies its row by
    # construction. Without it Postgres hands back whatever order the heap has,
    # and a row that was updated moves to the end.
    order_parts: list[str] = []
    already_sorted: set[str] = set()
    selected = set(selection.object_keys)
    for sort in selection.sort:
        if sort.object_key not in selected:
            raise SelectionError(
                f"Je kunt niet sorteren op '{_object(sort.object_key).name}': dat "
                "object staat niet in het rapport."
            )
        order_parts.append(f'"{sort.object_key}" {sort.direction.value.upper()}')
        already_sorted.add(sort.object_key)
    # Deduplicated by COLUMN, not by the whole term: a column the user sorted
    # descending would otherwise come back as a second, ascending term. Postgres
    # ignores that second mention, so nothing breaks — which is exactly why it
    # would have stayed in the statement, unread, until somebody debugging an order
    # spent an afternoon on it.
    order_by = order_parts + [f'"{o.key}" ASC' for o in grouped
                              if o.key not in already_sorted]

    limit = max(1, min(selection.limit, MAX_ROWS))
    params["tenant_id"] = tenant_id
    params["limit"] = limit
    params["offset"] = max(0, selection.offset)

    sql = "SELECT\n  " + ",\n  ".join(select_parts) + f"\nFROM {from_clause}\nWHERE {where}"
    if group_by:
        sql += "\nGROUP BY " + ", ".join(group_by)
    if order_by:
        sql += "\nORDER BY " + ", ".join(order_by)
    sql += "\nLIMIT :limit OFFSET :offset"

    # The totals row is the SAME aggregate over the whole set, not the sum of the
    # page. For a SUM that is the same number; for an average or a distinct count
    # it is the only right one, and adding up the rows would quietly lie.
    totals_select = ", ".join(
        f'{_expression(o)} AS "{o.key}"' for o in measures) or "1"
    totals_sql = f"SELECT {totals_select}\nFROM {from_clause}\nWHERE {where}"

    columns = [
        Column(key=o.key, name=o.name, kind=o.kind, format=o.format.value,
               drill=o.drill)
        for o in objects
    ]
    return QueryPlan(sql=sql, totals_sql=totals_sql, params=params,
                     columns=columns, fact=fact, drill_aliases=drill_aliases)
