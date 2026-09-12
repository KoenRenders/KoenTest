"""The crosstab: the same selection, drawn as a pivot (#834, CR-06 §5).

A pivot is not a second report. It reads exactly the objects the table form reads;
it only moves one dimension from the columns of the table to the column axis of a
crosstab. That is why its grand total equals the table's total for the same
selection and the same filters — not because two computations agree, but because
there is one selection.

**Every number here comes out of SQL; nothing is added up in Python.** The
temptation is obvious — the cells are on screen, so summing a row looks free — and
it is wrong for exactly the measures where nobody would notice: an average over
three columns is not the average of three averages, and a distinct count over two
months is not the sum of two distinct counts. So a row total is its own `GROUP BY`
without the column dimension, a subtotal is its own `GROUP BY` on the leading row
dimensions, and the grand total is the one the table form already computes. Four
groupings of one query shape, and every cell is an aggregate over the rows it
claims to describe.

The layout below is only that: layout. It reads the four results and puts them in
the shape the macro renders.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.reporting.engine import (
    MAX_PIVOT_COLUMNS,
    Column,
    Selection,
    SelectionError,
    build_member_count_query,
)
from app.domains.reporting.universe import BY_KEY


@dataclass
class PivotRow:
    """One line of the crosstab: its labels, its cells and its own total."""

    labels: list[Any]
    # Per column value, per measure key.
    cells: dict[str, dict[str, Any]]
    total: dict[str, Any]
    # A subtotal line closes a row group; it carries the label of that group only.
    is_subtotal: bool = False


@dataclass
class Pivot:
    """A crosstab, ready to render."""

    row_columns: list[Column]
    column_column: Column | None
    column_values: list[str]
    measures: list[Column]
    rows: list[PivotRow] = field(default_factory=list)
    grand_total: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        """The shape `ui.pivot_table()` reads.

        Plain lists and dicts, on purpose: the macro is kit code and may not know
        this domain. Jinja resolves `pivot.rows` on a dict as well as on an
        object, so the design-system page can hand the same macro a literal
        example without importing anything from here.
        """
        return {
            "row_headers": [c.name for c in self.row_columns],
            "column_header": self.column_column.name if self.column_column else "",
            "column_values": self.column_values,
            "measures": [{"key": m.key, "name": m.name, "format": m.format}
                         for m in self.measures],
            "rows": [
                {
                    "labels": [_label(v) for v in row.labels],
                    "cells": [[row.cells.get(waarde, {}).get(m.key)
                               for m in self.measures]
                              for waarde in self.column_values],
                    "total": [row.total.get(m.key) for m in self.measures],
                    "is_subtotal": row.is_subtotal,
                }
                for row in self.rows
            ],
            "grand_total": [self.grand_total.get(m.key) for m in self.measures],
        }


def _natural_key(waarde: str) -> tuple:
    """Sort key that reads a number in a label as a number.

    The pivot orders its rows in Python, not in SQL, so the natural sort the
    engine puts in the ORDER BY does not reach here — and a house number is text,
    so "10" would come before "9" and a street would come back shuffled (#850).
    Splitting on digit runs fixes that for every label that carries a number:
    house numbers, but also "Onderdeel 2" next to "Onderdeel 10".

    Digits sort as (0, number) and text as (1, text), so a numeric part always
    precedes a textual one and the two never compare against each other.
    """
    delen: list[tuple[int, Any]] = []
    getal = ""
    tekst = ""
    for teken in waarde:
        if teken.isdigit():
            if tekst:
                delen.append((1, tekst.lower()))
                tekst = ""
            getal += teken
        else:
            if getal:
                delen.append((0, int(getal)))
                getal = ""
            tekst += teken
    if getal:
        delen.append((0, int(getal)))
    if tekst:
        delen.append((1, tekst.lower()))
    return tuple(delen)


def _label(value: Any) -> str:
    """A cell label a person reads. An empty group is "Onbekend", never blank.

    A blank row header in a crosstab is unreadable: you cannot tell a missing
    value from a rendering bug, and both look like the table is broken.
    """
    return "Onbekend" if value is None or value == "" else str(value)


def check_column_cap(db: Session, selection: Selection, *, tenant_id: int) -> None:
    """Refuse a column dimension that is too wide, before the wide query runs."""
    if selection.layout != "pivot" or not selection.pivot_column:
        return
    sql, params = build_member_count_query(selection, selection.pivot_column,
                                           tenant_id=tenant_id)
    aantal = db.execute(text(sql), params).scalar() or 0
    if aantal > MAX_PIVOT_COLUMNS:
        naam = BY_KEY[selection.pivot_column].name
        raise SelectionError(
            f"'{naam}' heeft {aantal} waarden; een draaitabel toont er hoogstens "
            f"{MAX_PIVOT_COLUMNS}. Filter eerst, of zet een andere dimensie op de "
            "kolomas."
        )


def _without(selection: Selection, keys: set[str], *, limit: int) -> Selection:
    """The same selection with some objects left out — same fact, same filters.

    Dropping objects narrows the `GROUP BY` and nothing else, which is exactly
    what a total is: the same question asked at a coarser grain.
    """
    return Selection(
        object_keys=tuple(k for k in selection.object_keys if k not in keys),
        filters=selection.filters,
        sort=(),
        limit=limit,
        offset=0,
        layout="table",
    )


def build_pivot(db: Session, selection: Selection, *, tenant_id: int) -> Pivot:
    """Run the crosstab and lay it out.

    Raises `SelectionError` with the reason when the selection cannot be a pivot:
    no column dimension, a column dimension that is not in the selection, or one
    with too many members.
    """
    from app.domains.reporting.service import run_selection, validate_filter_values

    validate_filter_values(db, selection, tenant_id=tenant_id)

    # A pivot without a column dimension is not an error: it is a grouped listing
    # with a subtotal per group, which is what "Leden per bestuurslid" (#850) is —
    # one row per household, a subtotal of households per board member. Everything
    # below already handles an empty `pivot_column`; only this refusal stood in
    # the way. What it protected against is a table with a single Totaal column,
    # and that is exactly the shape being asked for.
    if selection.pivot_column and selection.pivot_column not in selection.object_keys:
        raise SelectionError(
            f"'{BY_KEY[selection.pivot_column].name}' staat niet in het rapport, "
            "dus kan het ook niet de kolomas zijn.")

    objects = [BY_KEY[k] for k in selection.object_keys]
    measures = [o for o in objects if o.is_measure]
    row_objects = [o for o in objects
                   if not o.is_measure and o.key != selection.pivot_column]
    if not measures:
        raise SelectionError(
            "Kies minstens één maat: een draaitabel zonder maat heeft niets te "
            "tonen in haar cellen.")
    # No row dimension is NOT refused (#877). `engine.py` says both shapes read
    # the same objects and the pivot only moves one of them to the column axis —
    # so a selection that gives €1059 in the table may not come back empty here.
    # One cell with the grand total is the right answer: the degenerate case, and
    # what a spreadsheet does too. A pivot without a MEASURE stays refused; there
    # is nothing to put in the cells.

    check_column_cap(db, selection, tenant_id=tenant_id)

    # The grid: one row per (row values, column value). Without a column axis —
    # a bar or a line chart does not need one — the grid IS the row totals, and
    # asking for it twice would be two queries for one answer.
    grid = run_selection(
        db,
        Selection(object_keys=selection.object_keys, filters=selection.filters,
                  sort=(), limit=selection.limit or 5000, offset=0),
        tenant_id=tenant_id)

    # The row totals: the same question without the column dimension. With no
    # column axis that IS the grid, so there is nothing to ask twice.
    row_totals = grid if not selection.pivot_column else run_selection(
        db, _without(selection, {selection.pivot_column}, limit=5000),
        tenant_id=tenant_id)

    row_keys = [o.key for o in row_objects]
    kolom_key = selection.pivot_column
    measure_keys = [m.key for m in measures]

    def _sleutel(row: dict) -> tuple:
        return tuple(_label(row.get(k)) for k in row_keys)

    cellen: dict[tuple, dict[str, dict[str, Any]]] = {}
    kolomwaarden: list[str] = []
    if kolom_key:
        for row in grid.rows:
            waarde = _label(row.get(kolom_key))
            if waarde not in kolomwaarden:
                kolomwaarden.append(waarde)
            cellen.setdefault(_sleutel(row), {})[waarde] = {
                k: row.get(k) for k in measure_keys}
        kolomwaarden.sort(key=_natural_key)

    totalen = {_sleutel(row): {k: row.get(k) for k in measure_keys}
               for row in row_totals.rows}

    # Subtotals only make sense with more than one row dimension: with one, every
    # row is its own group and a subtotal would repeat the line above it.
    subtotalen: dict[str, dict[str, Any]] = {}
    if len(row_objects) > 1:
        weg = set(row_keys[1:])
        if selection.pivot_column:
            weg.add(selection.pivot_column)
        groep = run_selection(db, _without(selection, weg, limit=5000),
                              tenant_id=tenant_id)
        subtotalen = {_label(row.get(row_keys[0])): {k: row.get(k)
                                                     for k in measure_keys}
                      for row in groep.rows}

    rijen: list[PivotRow] = []
    vorige_groep: str | None = None
    for sleutel in sorted(totalen,
                          key=lambda s: tuple(_natural_key(deel) for deel in s)):
        # `sleutel` is empty when there is no row dimension (#877) — one cell with
        # the grand total. `subtotalen` is empty in that case too (they need more
        # than one row dimension), so the guard below never indexes it; the
        # explicit length check says so instead of leaving it to that coincidence.
        if (subtotalen and len(sleutel) > 0 and vorige_groep is not None
                and sleutel[0] != vorige_groep):
            rijen.append(PivotRow(labels=[vorige_groep], cells={},
                                  total=subtotalen.get(vorige_groep, {}),
                                  is_subtotal=True))
        rijen.append(PivotRow(labels=list(sleutel),
                              cells=cellen.get(sleutel, {}),
                              total=totalen[sleutel]))
        vorige_groep = sleutel[0] if sleutel else None
    if subtotalen and vorige_groep is not None:
        rijen.append(PivotRow(labels=[vorige_groep], cells={},
                              total=subtotalen.get(vorige_groep, {}),
                              is_subtotal=True))

    def _column(obj) -> Column:
        return Column(key=obj.key, name=obj.name, kind=obj.kind,
                      format=obj.format.value, drill=obj.drill)

    return Pivot(
        row_columns=[_column(o) for o in row_objects],
        column_column=_column(BY_KEY[kolom_key]) if kolom_key else None,
        column_values=kolomwaarden,
        measures=[_column(m) for m in measures],
        rows=rijen,
        # The grand total is the one the table form already computes: same WHERE,
        # no grouping. Never the sum of the subtotals.
        grand_total=grid.totals,
    )
