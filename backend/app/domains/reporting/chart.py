"""A chart is the crosstab, drawn (#835, CR-06 §6).

Not a second story and not a second query: this module takes the `Pivot` that the
table and the crosstab already produced and turns it into coordinates. That is the
whole reason a chart is cheap here, and the whole reason it can never disagree
with the number in the table above it.

Three kinds, and no more: **bar** and **line** put the row dimension on the x-axis
with one series per measure; **stacked** puts the column dimension's members on
top of each other, for the first measure. A board member needs those three. A pie
chart makes a share look like a quantity, and a second y-axis makes two unrelated
scales look comparable — neither is worth the misreading.

**Scaling happens here, drawing happens in the macro.** The macro places rects and
polylines from values and a stated domain; deciding *what* the domain is — where
zero sits, how far the axis reaches, which ticks are round — is a rule, and a rule
in a template is a rule in two places (design-system §8.3).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.domains.reporting.engine import SelectionError
from app.domains.reporting.pivot import Pivot

CHART_LAYOUTS = ("bar", "line", "stacked")

# The categorical scale, as CSS custom properties. Tokens and not hex, so the lint
# gate can keep proving that no screen invents a colour (#652).
#
# The order is chosen, not alphabetical: brand blue first because a single-series
# chart is the common case and it must look like the rest of the application; then
# the hues that stay apart from it and from each other. `danger` and `warning`
# come last — they mean something in this kit, and a bar that is red for no reason
# reads as a problem.
SERIES_COLORS = (
    "var(--brand-ocean)", "var(--brand-teal)", "var(--brand-indigo)",
    "var(--brand-green)", "var(--brand-pink)", "var(--brand-accent)",
    "var(--brand-warning)", "var(--brand-danger)",
)


@dataclass
class Series:
    name: str
    values: list[float | None]
    color: str


@dataclass
class Chart:
    kind: str
    title: str
    x_labels: list[str]
    series: list[Series]
    y_min: float
    y_max: float
    y_ticks: list[float]
    money: bool = False
    # The measure names, for the description a screen reader gets.
    description: str = ""
    empty_message: str = ""

    def as_context(self) -> dict[str, Any]:
        """The shape `ui.chart_*()` reads — plain lists and dicts, like the pivot."""
        return {
            "kind": self.kind,
            "title": self.title,
            "x_labels": self.x_labels,
            # `points` and not `values`: on a dict Jinja resolves an attribute
            # before an item, so `series.values` would hand the template the
            # built-in `dict.values` method instead of the numbers.
            "series": [{"name": s.name, "points": s.values, "color": s.color}
                       for s in self.series],
            "y_min": self.y_min,
            "y_max": self.y_max,
            "y_ticks": self.y_ticks,
            "money": self.money,
            "description": self.description,
        }


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nice(value: float) -> float:
    """The nearest round number at or beyond ``value``, keeping its sign.

    An axis that stops at 37 makes every gridline a number nobody can hold. 1, 2,
    2.5 and 5 times a power of ten are the steps that read as round in every
    magnitude.
    """
    if value == 0:
        return 0.0
    macht = 10 ** math.floor(math.log10(abs(value)))
    for factor in (1, 2, 2.5, 5, 10):
        if abs(value) <= factor * macht:
            return math.copysign(factor * macht, value)
    return math.copysign(10 * macht, value)


def _domain(values: list[float]) -> tuple[float, float, list[float]]:
    """Where the axis starts, where it ends, and its ticks.

    Zero is always in the domain. A bar chart whose baseline is not zero
    exaggerates every difference on it, and that is the single most common way a
    chart lies without anybody writing anything false.
    """
    hoog = max([v for v in values] + [0.0])
    laag = min([v for v in values] + [0.0])
    boven = _nice(hoog) if hoog else 0.0
    onder = _nice(laag) if laag else 0.0
    if boven == onder:
        boven = 1.0
    stap = (boven - onder) / 4
    ticks = [onder + stap * i for i in range(5)]
    return onder, boven, ticks


def build_chart(pivot: Pivot, kind: str, *, title: str = "") -> Chart:
    """Turn a crosstab into a chart of this kind.

    Subtotal rows are left out: they are a reading aid in a table, and drawn as
    bars beside their own parts they would count the same money twice.
    """
    if kind not in CHART_LAYOUTS:
        raise SelectionError(f"De grafieksoort '{kind}' bestaat niet.")

    rijen = [r for r in pivot.rows if not r.is_subtotal]
    x_labels = [" · ".join(str(label) for label in r.labels) for r in rijen]
    geld = bool(pivot.measures) and pivot.measures[0].format == "money"

    if kind == "stacked":
        if not pivot.column_values:
            raise SelectionError(
                "Een gestapelde staaf heeft een kolomdimensie nodig: kies er een "
                "voor de stapeling.")
        maat = pivot.measures[0]
        reeksen = [
            Series(name=str(waarde),
                   values=[_number(r.cells.get(waarde, {}).get(maat.key))
                           for r in rijen],
                   color=SERIES_COLORS[index % len(SERIES_COLORS)])
            for index, waarde in enumerate(pivot.column_values)
        ]
        # A stack is as tall as its parts together, so the axis has to reach the
        # sum and not the tallest part.
        stapels = [sum(v or 0.0 for v in kolom)
                   for kolom in zip(*[s.values for s in reeksen])] if reeksen else []
        y_min, y_max, ticks = _domain([float(v) for v in stapels])
        beschrijving = (f"{maat.name} per "
                        f"{pivot.column_column.name if pivot.column_column else ''}")
    else:
        reeksen = [
            Series(name=maat.name,
                   values=[_number(r.total.get(maat.key)) for r in rijen],
                   color=SERIES_COLORS[index % len(SERIES_COLORS)])
            for index, maat in enumerate(pivot.measures)
        ]
        alle = [v for s in reeksen for v in s.values if v is not None]
        y_min, y_max, ticks = _domain(alle)
        beschrijving = ", ".join(m.name for m in pivot.measures)

    as_naam = ", ".join(c.name for c in pivot.row_columns)
    return Chart(
        kind=kind,
        title=title or f"{beschrijving} per {as_naam}",
        x_labels=x_labels,
        series=reeksen,
        y_min=y_min,
        y_max=y_max,
        y_ticks=ticks,
        money=geld,
        description=f"{beschrijving}, per {as_naam}."
                    + (f" Gestapeld per {pivot.column_column.name}."
                       if kind == "stacked" and pivot.column_column else ""),
    )


@dataclass
class ChartData:
    """The rows behind a chart, for sheet 3 of the export (CR-06 §5)."""

    headers: list[str]
    rows: list[list[Any]] = field(default_factory=list)


def chart_data(chart: Chart) -> ChartData:
    """The chart's own numbers as a flat table.

    Sheet 3 of the export: the series exactly as they were drawn, so somebody can
    check a bar against a number instead of measuring it with a ruler.
    """
    headers = ["Categorie"] + [s.name for s in chart.series]
    rows: list[list[Any]] = []
    for index, label in enumerate(chart.x_labels):
        rij: list[Any] = [label]
        for reeks in chart.series:
            waarde = reeks.values[index]
            rij.append("" if waarde is None else waarde)
        rows.append(rij)
    return ChartData(headers=headers, rows=rows)
