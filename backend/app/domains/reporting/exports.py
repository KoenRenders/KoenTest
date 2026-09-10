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

from sqlalchemy.orm import Session

from app.domains.reporting.service import Dataset, load_dataset
from app.kernel.ods import build_ods

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
