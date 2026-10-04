"""How an answer of the assistant shows the report behind it (CR-11 block 10, #1562; §3.15).

The model answers in words. What it counted comes from `run_report`, and the
panel shows that as what it is, beside the words:

- **a figure** — the report gave one row with one measure: the number large,
  with its label, its range (the filters it was counted over) and its source;
- **a small table** — several rows: the first five, and "Bekijk alle n …" that
  opens the same selection in the reporting panel, where the whole list stands.

Nothing here is the model's: the numbers are the engine's result of the last
report the model ran in this turn, formatted by the kit like every other
report value — so a figure in the balloon and the same figure in the panel
cannot differ. No report in the turn, no figure and no table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.domains.reporting.engine import Layout, Selection
from app.domains.reporting.service import ReportResult
from app.domains.reporting.universe import FACTS, OBJECTS, Format, ObjectKind
from app.i18n import _

#: A table in a balloon shows this many rows and columns; the rest is behind
#: "Bekijk alle n …".
TABLE_ROWS = 5
TABLE_COLUMNS = 4

#: The formats that read as a number, and stand right-aligned.
_NUMERIC = frozenset({Format.COUNT, Format.MONEY, Format.PERCENTAGE, Format.DAYS})


@dataclass(frozen=True)
class SeenReport:
    """One report the model ran in this turn: what was asked and what came back."""

    selection: Selection
    result: ReportResult


@dataclass(frozen=True)
class AnswerFigure:
    label: str
    value: Any
    format: str
    range: str
    source: str


@dataclass(frozen=True)
class AnswerTable:
    #: Per column shown: its `name`, its `format` and whether it is a number
    #: (`numeric` — right-aligned; decided here, not compared in the template).
    columns: list[dict[str, Any]]
    #: Per row its cells, in the order of `columns`.
    rows: list[list[Any]]
    total: int
    #: What the rows are, in the plural and in lower case ("betalingen").
    noun: str
    range: str


@dataclass(frozen=True)
class StructuredAnswer:
    figure: Optional[AnswerFigure] = None
    table: Optional[AnswerTable] = None
    #: The selection behind it, for the link into the reporting panel.
    selection: Optional[Selection] = None
    extra: dict[str, Any] = field(default_factory=dict)


def _names() -> dict[str, str]:
    return {obj.key: obj.name for obj in OBJECTS}


def _range_of(selection: Selection, scope_label: str, scope_keys: frozenset[str]) -> str:
    """What the report ran over, in words: "Status: Openstaand · Jaar: 2026".
    The filters the conversation's scope forces are said as the reader knows that
    scope — the record's name, not "Activiteitnummer: 22"."""
    names = _names()
    parts = [scope_label] if scope_label else []
    for flt in selection.filters:
        if flt.object_key in scope_keys:
            continue
        values = ([flt.symbolic] if getattr(flt, "symbolic", None) else []) + [
            str(v) for v in flt.values
        ]
        if values:
            parts.append(f"{names.get(flt.object_key, flt.object_key)}: {', '.join(values)}")
    return " · ".join(parts) or _("alles")


def _fact_name(key: str) -> str:
    return next((fact.name for fact in FACTS if fact.key == key), _("Rapportering"))


def structured(
    seen: list[SeenReport], *, scope_label: str = "", scope_keys: frozenset[str] = frozenset()
) -> StructuredAnswer:
    """What the last report of this turn shows beside the model's words.
    `scope_label` and `scope_keys`: the conversation's scope in the reader's
    words, and the objects its forced filters stand on."""
    last = next((s for s in reversed(seen) if s.result.rows), None)
    if last is None:
        return StructuredAnswer()
    result, selection = last.result, last.selection
    measures = [c for c in result.columns if c.kind is ObjectKind.MEASURE]
    fact = _fact_name(result.fact)
    if (
        len(result.rows) == 1
        and len(measures) == 1
        # A sum over nothing is no figure: the words say there is nothing.
        and result.rows[0].get(measures[0].key) is not None
    ):
        measure = measures[0]
        return StructuredAnswer(
            figure=AnswerFigure(
                label=measure.name,
                value=result.rows[0].get(measure.key),
                format=measure.format,
                range=_range_of(selection, scope_label, scope_keys),
                source=_("Rapportering · %(fact)s") % {"fact": fact},
            ),
            selection=selection,
        )
    if len(result.rows) >= 2:
        columns = result.columns[:TABLE_COLUMNS]
        return StructuredAnswer(
            table=AnswerTable(
                columns=[
                    {"name": c.name, "format": c.format, "numeric": c.format in _NUMERIC}
                    for c in columns
                ],
                rows=[[row.get(c.key) for c in columns] for row in result.rows[:TABLE_ROWS]],
                total=result.total_rows if result.total_rows is not None else len(result.rows),
                # A listing's rows are the fact's own ("betalingen"); a grouped
                # table's rows are groups.
                noun=fact.lower() if selection.layout == Layout.DETAIL else _("rijen"),
                range=_range_of(selection, scope_label, scope_keys),
            ),
            selection=selection,
        )
    return StructuredAnswer()
