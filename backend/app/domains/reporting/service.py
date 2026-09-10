"""Running a selection, and reading a fact flat (CR-06 §4, §5).

The engine builds; this module executes. That split is what lets every refusal be
proved without a database and every query be executed in exactly one place — the
place that also passes the tenant.

**The tenant is never a parameter the caller may forget.** Both entry points take
it explicitly and both hand it to the engine as a bind value; there is no code
path here that queries a reporting view without it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.reporting.engine import (
    Column,
    Selection,
    SelectionError,
    build_query,
)
from app.domains.reporting.universe import FACT_BY_KEY, Fact


@dataclass
class ReportResult:
    """One run of one selection: the columns, the rows and the totals row.

    ``rows`` are dicts keyed by object key, so a template and an export read the
    same structure and cannot disagree about column order.
    """

    columns: list[Column]
    rows: list[dict[str, Any]]
    totals: dict[str, Any]
    fact: str
    # The drill target per column key, e.g. ``{"activity": 12}`` per row, kept
    # alongside the label so the cell can become a link without a second query.
    drill_aliases: dict[str, str]

    @property
    def row_count(self) -> int:
        return len(self.rows)


@dataclass
class Dataset:
    """A whole fact, flat: every column of the view, one row per fact row."""

    fact: Fact
    headers: list[str]
    rows: list[list[Any]]


def run_selection(db: Session, selection: Selection, *,
                  tenant_id: int) -> ReportResult:
    """Execute one selection and return its rows plus the totals row.

    Two statements, not one: the totals row is the same aggregate over the whole
    filtered set, so it stays right when the table is paged. Adding up the page
    would report the page, and a board member reading "Totaal" expects the report.
    """
    plan = build_query(selection, tenant_id=tenant_id)

    rows: list[dict[str, Any]] = []
    for record in db.execute(text(plan.sql), plan.params).mappings():
        rows.append(dict(record))

    totals: dict[str, Any] = {}
    measures = [c for c in plan.columns if c.kind.value == "measure"]
    if measures:
        record = db.execute(text(plan.totals_sql), plan.params).mappings().first()
        if record is not None:
            totals = dict(record)

    return ReportResult(columns=plan.columns, rows=rows, totals=totals,
                        fact=plan.fact, drill_aliases=plan.drill_aliases)


def _fact_or_refuse(fact_key: str) -> Fact:
    """The fact, if the universe knows it — else a readable refusal.

    Looking the key up is also what keeps it out of the SQL: only a key that is
    already in ``FACT_BY_KEY`` can ever reach the statement, so the view name in
    the query is ours and never the caller's.
    """
    fact = FACT_BY_KEY.get(fact_key)
    if fact is None:
        raise SelectionError(f"Onbekend feit: '{fact_key}'.")
    return fact


def fact_columns(db: Session, fact_key: str) -> list[str]:
    """The columns of a fact view, in the order the view declares them."""
    result = db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'reporting' AND table_name = :name "
            "ORDER BY ordinal_position"
        ),
        {"name": fact_key},
    )
    return [row[0] for row in result]


def load_dataset(db: Session, fact_key: str, *, tenant_id: int,
                 limit: int = 20000) -> Dataset:
    """A whole fact for this tenant, flat — the dataset behind the reports.

    Every column of the view, under the view's own names. Those names are the ones
    ``docs/reporting-universe.md`` documents and the ones the universe objects
    point at, so a spreadsheet built on this export keeps matching the universe.
    Renaming them here would give the same data two vocabularies.
    """
    fact = _fact_or_refuse(fact_key)
    columns = fact_columns(db, fact.key)
    if not columns:
        # A fact whose view is gone is a broken deployment, not an empty report.
        raise SelectionError(
            f"De weergave reporting.{fact.key} bestaat niet. Draaide de migratie?"
        )

    quoted = ", ".join(f'"{c}"' for c in columns)
    order = ", ".join(f'"{c}"' for c in fact.dataset_key) or quoted
    sql = (f"SELECT {quoted} FROM reporting.{fact.key} "
           f"WHERE tenant_id = :tenant_id ORDER BY {order} LIMIT :limit")
    result = db.execute(text(sql), {"tenant_id": tenant_id, "limit": limit})
    rows = [list(row) for row in result]
    return Dataset(fact=fact, headers=columns, rows=rows)


__all__ = [
    "Dataset",
    "ReportResult",
    "Role",
    "fact_columns",
    "load_dataset",
    "run_selection",
]
