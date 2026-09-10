"""Flat dataset export per fact (CR-06 §8, phase 1).

Layer 3 of the change request and the first visible win: before there is any
screen, a board member can already take a whole fact into LibreOffice Calc and
pivot it there. One sheet, every column of the view, the tenant's rows only.

The header row carries the view's own column names. That is deliberate: those are
the names ``docs/reporting-universe.md`` documents and the names the universe
objects resolve to, so a spreadsheet somebody builds on this export keeps lining
up with the universe. Giving the same data a second vocabulary here would make
every future question "which name did you mean?".
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.reporting.chart import chart_data
from app.domains.reporting.engine import BY_KEY, Selection, build_detail_query
from app.domains.reporting.service import Dataset, ReportResult, load_dataset
from app.kernel.ods import build_ods, build_ods_multi

logger = logging.getLogger(__name__)


def _cell(value: Any) -> Any:
    """One value as the ODS kernel wants it.

    ``Decimal`` becomes a float so Calc gets a number it can sum — the kernel only
    recognises ``int`` and ``float`` as numeric, and a money column that arrives as
    text is a spreadsheet you cannot add up. Dates become ISO text, which sorts
    correctly and is unambiguous in every locale.
    """
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool):
        return "Ja" if value else "Nee"
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value


def build_dataset_ods(db: Session, fact_key: str, *,
                      tenant_id: int) -> tuple[Dataset, bytes]:
    """The whole fact as an .ods. Returns the dataset too, so a caller can log it.

    An unknown fact travels out as ``SelectionError`` — the route turns it into a
    422 with the reason.
    """
    dataset = load_dataset(db, fact_key, tenant_id=tenant_id)
    rows = [[_cell(value) for value in row] for row in dataset.rows]
    content = build_ods(dataset.fact.name, dataset.headers, rows)

    # An export is data leaving the system (CR-06 §7.6). The durable one-row-per-
    # export trail lands with the query panel (#833); this line is what phase 1 can
    # honestly promise. No e-mail address and no filter values: these logs are
    # fetched off the server with `raak fetch`, and the allowlist in
    # `logging_config` exists exactly so a log line cannot carry a person.
    logger.info("reporting dataset export: fact=%s tenant=%s rows=%s",
                dataset.fact.key, tenant_id, len(rows))
    return dataset, content


def dataset_filename(dataset: Dataset) -> str:
    """A file name a board member recognises in his download folder."""
    slug = dataset.fact.name.lower().replace(" ", "-")
    return f"rapportering-{slug}.ods"


def filter_summary(selection: Selection) -> list[str]:
    """The active filters in words — one line per filter.

    This is what goes in the header of sheet 1 (CR-06 §5). A filtered table that
    travels without saying what was filtered gets read as "everything", and that
    is how a board ends up discussing the wrong number.
    """
    woorden = {
        "eq": "is", "ne": "is niet", "in": "is een van", "lt": "is kleiner dan",
        "lte": "is hoogstens", "gt": "is groter dan", "gte": "is minstens",
        "between": "ligt tussen", "contains": "bevat",
    }
    regels = []
    for flt in selection.filters:
        obj = BY_KEY.get(flt.object_key)
        naam = obj.name if obj else flt.object_key
        waarden = " en ".join(flt.values) if flt.operator.value == "between" \
            else ", ".join(flt.values)
        regels.append(f"{naam} {woorden.get(flt.operator.value, flt.operator.value)} "
                      f"{waarden}")
    return regels


def _detail_rows(db: Session, selection: Selection, *,
                 tenant_id: int) -> tuple[list[str], list[list[Any]]]:
    """Sheet 2: the fact rows behind the report, filtered exactly the same way."""
    plan = build_detail_query(selection, tenant_id=tenant_id)
    result = db.execute(text(plan.sql), plan.params)
    headers = list(result.keys())
    rows = [[_cell(value) for value in row] for row in result]
    return headers, rows


def build_report_ods(db: Session, result: ReportResult, selection: Selection, *,
                     title: str, tenant_id: int) -> bytes:
    """The report as a spreadsheet: sheet 1 the table, sheet 2 the rows behind it.

    Sheet 1 is what is on the screen — same columns, same order, same totals row —
    with the report's name and its active filters above it. Sheet 2 is the fact at
    its own grain, so somebody can pivot it in Calc or check a total by hand.
    """
    intro: list[list[Any]] = [["Rapport", title]]
    for regel in filter_summary(selection):
        intro.append(["Filter", regel])
    if not selection.filters:
        intro.append(["Filter", "geen"])
    intro.append([])

    headers = [column.name for column in result.columns]
    rows: list[list[Any]] = [
        [_cell(row.get(column.key)) for column in result.columns]
        for row in result.rows
    ]
    if result.totals:
        rows.append([
            "Totaal" if index == 0 else _cell(result.totals.get(column.key, ""))
            for index, column in enumerate(result.columns)
        ])

    detail_headers, detail_rows = _detail_rows(db, selection, tenant_id=tenant_id)
    return build_ods_multi([
        {"name": title[:31] or "Rapport", "headers": headers, "rows": rows,
         "intro_rows": intro, "bold_last_row": bool(result.totals)},
        {"name": "Detail", "headers": detail_headers, "rows": detail_rows},
    ])


def report_filename(title: str) -> str:
    """A file name a board member recognises in his download folder."""
    veilig = "".join(c if c.isalnum() or c in " -_" else "-" for c in title).strip()
    slug = "-".join(veilig.lower().split()) or "rapport"
    return f"rapport-{slug}.ods"


def build_pivot_ods(db: Session, pivot, selection: Selection, *, title: str,
                    tenant_id: int, chart=None) -> bytes:
    """The crosstab as a spreadsheet: sheet 1 the pivot, sheet 2 the rows behind it.

    Sheet 1 is what is on the screen, subtotals included, with the report's name
    and its active filters above it. The header is two rows when there is more
    than one measure, exactly as the macro renders it, so a cell in Calc sits
    under the same two labels it sat under on screen.
    """
    maten = pivot["measures"]
    kolommen = pivot["column_values"]
    breed = len(maten)

    intro: list[list[Any]] = [["Rapport", title]]
    for regel in filter_summary(selection):
        intro.append(["Filter", regel])
    if not selection.filters:
        intro.append(["Filter", "geen"])
    intro.append([])

    # The column band: one label per column value, spanning its measures. A
    # spreadsheet has no colspan, so the label sits in the first of its cells and
    # the rest stay empty — which is how Calc shows a merged header anyway.
    kop: list[Any] = list(pivot["row_headers"])
    for waarde in kolommen:
        kop.append(waarde)
        kop += [""] * (breed - 1)
    kop.append("Totaal")
    kop += [""] * (breed - 1)

    rijen: list[list[Any]] = []
    if breed > 1:
        onder: list[Any] = [""] * len(pivot["row_headers"])
        for _waarde in kolommen:
            onder += [m["name"] for m in maten]
        onder += [m["name"] for m in maten]
        rijen.append(onder)

    for rij in pivot["rows"]:
        uit: list[Any] = list(rij["labels"])
        uit += [""] * (len(pivot["row_headers"]) - len(rij["labels"]))
        if rij["is_subtotal"]:
            uit[0] = f"Subtotaal — {rij['labels'][0]}"
        for cel in (rij["cells"] or [[None] * breed for _ in kolommen]):
            uit += [_cell(waarde) for waarde in cel]
        uit += [_cell(waarde) for waarde in rij["total"]]
        rijen.append(uit)

    eind: list[Any] = ["Eindtotaal"]
    eind += [""] * (len(pivot["row_headers"]) - 1)
    eind += [""] * (len(kolommen) * breed)
    eind += [_cell(waarde) for waarde in pivot["grand_total"]]
    rijen.append(eind)

    detail_headers, detail_rows = _detail_rows(db, selection, tenant_id=tenant_id)
    bladen = [
        {"name": title[:31] or "Draaitabel", "headers": kop, "rows": rijen,
         "intro_rows": intro, "bold_last_row": True},
        {"name": "Detail", "headers": detail_headers, "rows": detail_rows},
    ]
    if chart is not None:
        # Sheet 3: the series exactly as they were drawn (CR-06 §5). A bar you
        # can only measure with a ruler is not evidence; the number behind it is.
        data = chart_data(chart)
        bladen.append({"name": "Grafiek", "headers": data.headers,
                       "rows": [[_cell(waarde) for waarde in rij]
                                for rij in data.rows]})
    return build_ods_multi(bladen)
