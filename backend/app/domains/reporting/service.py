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
from datetime import date
import logging
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.domains.reporting.engine import (
    PEOPLE_ALIAS,
    SMALL_CELL_THRESHOLD,
    SYMBOLIC_ME,
    SYMBOLIC_THIS_YEAR,
    SYMBOLIC_TODAY,
    Column,
    Filter,
    Operator,
    Selection,
    SelectionError,
    build_query,
    selection_from_dict,
    selection_to_dict,
)
from app.domains.reporting.models import ExportLog, SavedReport
from app.domains.reporting.universe import BY_KEY, FACT_BY_KEY, Fact, UniverseObject


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
    if plan.has_totals:
        record = db.execute(text(plan.totals_sql), plan.params).mappings().first()
        if record is not None:
            totals = dict(record)

    if plan.guarded:
        rows = merge_small_cells(rows, plan.columns)

    return ReportResult(columns=plan.columns, rows=rows, totals=totals,
                        fact=plan.fact, drill_aliases=plan.drill_aliases)


# The label of the row that every group below the threshold ends up in. One row
# and not one per group: two merged rows of four are still two groups of four.
MERGED_LABEL = f"Samengevoegd (minder dan {SMALL_CELL_THRESHOLD})"


def merge_small_cells(rows: list[dict[str, Any]],
                      columns: list[Column]) -> list[dict[str, Any]]:
    """Fold every group that covers fewer than five people into one row (#841).

    A report that says "one member in Balen, aged 41-60, female" names somebody
    without writing a name. Merging and not dropping, because the totals row comes
    from SQL over the whole set: dropping would leave a table whose rows no longer
    add up to their own total, and a reader would sooner distrust the total than
    guess that something was withheld.

    **Only an additive measure is added up in the merged row.** An average or a
    distinct count over merged groups is not the average or the count of the
    whole, and there is no way to ask SQL for it afterwards — the groups are gone.
    Those cells stay empty, which reads as "not available here" instead of as a
    number that happens to be wrong.
    """
    klein = [r for r in rows if (r.get(PEOPLE_ALIAS) or 0) < SMALL_CELL_THRESHOLD]
    groot = [r for r in rows if (r.get(PEOPLE_ALIAS) or 0) >= SMALL_CELL_THRESHOLD]
    for rij in groot:
        rij.pop(PEOPLE_ALIAS, None)
    if not klein:
        return groot

    samen: dict[str, Any] = {}
    eerste = True
    for kolom in columns:
        if kolom.kind.value == "measure":
            if not kolom.additive:
                samen[kolom.key] = None
                continue
            waarden = [r.get(kolom.key) for r in klein if r.get(kolom.key) is not None]
            samen[kolom.key] = sum(waarden) if waarden else None
        else:
            samen[kolom.key] = MERGED_LABEL if eerste else None
            eerste = False
    # The merged row points nowhere: a link would lead back to one of the records
    # the merge exists to hide.
    for kolom in columns:
        samen.pop(f"{kolom.key}__drill", None)
    return groot + [samen]


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




# ── The values a dimension can take ──────────────────────────────────────────
# The filter bar offers them, and the engine checks a filter against them. Both
# read the same list, so a value the panel offered can never be refused and a
# value it did not offer can never quietly match nothing.

# Above this many distinct values a dimension is not a `<select>` any more — a
# municipality list of four hundred is a search box, not a dropdown. It is also
# the point where the check below stops requiring a known value: we cannot demand
# a choice from a list we did not offer.
OFFER_LIMIT = 60


def dimension_values(db: Session, object_key: str, *, tenant_id: int) -> list[str]:
    """The distinct values of one dimension for this tenant, in reading order.

    Empty when there are more than `OFFER_LIMIT` of them: that is the signal to
    the panel to render a text field instead of a dropdown, and to the check below
    to let any value through.
    """
    obj = BY_KEY.get(object_key)
    if obj is None or obj.is_measure:
        return []
    expression = obj.sql.format(view=obj.view)
    # A code list carries its own reading order; anything else sorts on itself.
    order = "2" if _has_column(db, obj.view, "sort_order") else "1"
    sort_column = (", MIN(sort_order) AS sort_order"
                   if _has_column(db, obj.view, "sort_order") else "")
    rows = db.execute(
        text(f"SELECT {expression} AS value{sort_column} "
             f"FROM reporting.{obj.view} "
             f"WHERE tenant_id = :tenant_id AND {expression} IS NOT NULL "
             f"GROUP BY {expression} ORDER BY {order} LIMIT :limit"),
        {"tenant_id": tenant_id, "limit": OFFER_LIMIT + 1},
    ).all()
    if len(rows) > OFFER_LIMIT:
        return []
    return [str(row[0]) for row in rows]


def _has_column(db: Session, view: str, column: str) -> bool:
    return bool(db.execute(
        text("SELECT 1 FROM information_schema.columns "
             "WHERE table_schema = 'reporting' AND table_name = :v "
             "  AND column_name = :c"),
        {"v": view, "c": column}).scalar())


# The operators that name a value from the dimension. A range or a search term is
# a different kind of question and is not checked against a list.
_VALUE_OPERATORS = (Operator.EQ, Operator.NE, Operator.IN)


def validate_filter_values(db: Session, selection: Selection, *,
                           tenant_id: int) -> None:
    """Refuse a filter value a CLOSED list does not have — before a query runs.

    CR-06 §7.5: object keys, filter values and layout are validated against the
    universe before anything is executed. For a code list that is exactly right:
    "Bancontact" is not a payment method, and saying so beats an empty table that
    reads as "no data".

    **Only for a closed list, and that distinction was learned the hard way.** An
    open dimension — a municipality, a required role, an activity name — has the
    values the data happens to have today. A saved report that filters on
    "ADMIN" is not wrong on the morning there is no task for an admin; it is a
    report with no rows. Demanding a value from a list that changes under the
    report turns a legitimate empty result into an error, and it did: the
    dashboard's "Open taken" report refused itself on a seed without such a task.

    A code list is recognised by having a `code` column — the same shape the three
    of them share — rather than by a list kept here, which would go stale the
    first time somebody adds a fourth.
    """
    for flt in selection.filters:
        if flt.operator not in _VALUE_OPERATORS:
            continue
        if flt.symbolic:
            # A resolved "today" or "me" is legitimate by construction. Checking
            # it against the dimension's values would refuse a personal report
            # for the one person who has no rows yet — and seeing nothing is the
            # right answer there, not an error.
            continue
        obj = BY_KEY[flt.object_key]
        if not _has_column(db, obj.view, "code"):
            continue
        toegestaan = dimension_values(db, flt.object_key, tenant_id=tenant_id)
        if not toegestaan:
            continue
        onbekend = [v for v in flt.values if v not in toegestaan]
        if onbekend:
            raise SelectionError(
                f"'{onbekend[0]}' is geen waarde van '{obj.name}'. "
                f"Kies er een uit de lijst."
            )


# ── Resolving "now" and "me" (#847) ──────────────────────────────────────────

def resolve_selection(selection: Selection, *, today: date | None = None,
                      viewer: str = "") -> Selection:
    """Replace every symbolic filter value with what it means right now.

    **This is where identity and the clock enter, and nowhere deeper.**
    `build_query` takes a selection and a tenant and nothing else; by the time it
    sees this selection every value is literal. That is what keeps `ik` a filter
    value instead of quietly becoming a role fence — which is a different
    question, and still open (CR-06 §5.1, #847 point 1).

    Pure, and it takes `today` as an argument rather than reading the clock: a
    test that can only go red next January is not a test.

    The stored selection is not touched. What is saved stays relative; only the
    copy that runs is literal — otherwise opening a report once would freeze it.
    """
    if not any(f.symbolic for f in selection.filters):
        return selection

    nu = today or date.today()
    opgelost: list[Filter] = []
    for flt in selection.filters:
        if not flt.symbolic:
            opgelost.append(flt)
            continue
        if flt.symbolic == SYMBOLIC_TODAY:
            waarden = (nu.isoformat(),)
        elif flt.symbolic == SYMBOLIC_THIS_YEAR:
            waarden = (str(nu.year),)
        elif flt.symbolic == SYMBOLIC_ME:
            if not viewer:
                if flt.values:
                    # Already resolved by a caller that DID know who was looking.
                    # Resolving twice happens — the panel resolves before it
                    # dispatches and the service resolves again — and the second
                    # pass must not throw the first one's answer away. That is
                    # what "idempotent" has to mean here, and it cost an hour to
                    # learn: without it the panel rendered nothing at all.
                    opgelost.append(flt)
                    continue
                raise SelectionError(
                    "Dit rapport filtert op de aangemelde gebruiker, en er is er "
                    "geen. Meld je aan en open het opnieuw.")
            waarden = (viewer,)
        else:  # pragma: no cover - `selection_from_dict` refuses anything else
            raise SelectionError(f"Onbekende relatieve waarde: '{flt.symbolic}'.")
        opgelost.append(Filter(flt.object_key, flt.operator, waarden, flt.symbolic))

    return Selection(
        object_keys=selection.object_keys, filters=tuple(opgelost),
        sort=selection.sort, limit=selection.limit, offset=selection.offset,
        layout=selection.layout, pivot_column=selection.pivot_column)


def is_personal(selection: Selection) -> bool:
    """Does this report show a different answer per person? (#847 point 2)

    A report that fills in your own name has to say so, or somebody shares a link
    and the receiver cannot explain why he sees something else.
    """
    return any(f.symbolic == SYMBOLIC_ME for f in selection.filters)


def run_validated(db: Session, selection: Selection, *, tenant_id: int,
                  today: date | None = None, viewer: str = "") -> ReportResult:
    """Resolve, validate, run. The panel's single entry point."""
    concreet = resolve_selection(selection, today=today, viewer=viewer)
    validate_filter_values(db, concreet, tenant_id=tenant_id)
    return run_selection(db, concreet, tenant_id=tenant_id)


# ── Saved reports (CR-06 §5) ─────────────────────────────────────────────────

class SavedReportError(ValueError):
    """A saved report that cannot be saved, with the reason in the message."""


def _visible(db: Session, tenant_id: int):
    """Base query: this tenant's live reports, shared ones and your own.

    The tenant condition is written out here rather than left to the ORM's global
    filter, because these functions also run from a request that has no tenant
    context (a script, a test) and a report list that silently spans tenants is
    exactly the leak CR-06 §7.1 is about.
    """
    return (db.query(SavedReport)
            .filter(SavedReport.tenant_id == tenant_id,
                    SavedReport.deleted_at.is_(None))
            .execution_options(include_all_tenants=True))


def list_saved_reports(db: Session, *, tenant_id: int, viewer: str,
                       q: str = "", owner: str = "all",
                       shared: str = "all") -> list[SavedReport]:
    """The reports this person may open, filtered as the list screen asks.

    Sorted by name and then by id: the name is what a board member scans for, and
    the id is the unique tail that keeps the order the same after an edit (#761).
    """
    query = _visible(db, tenant_id).filter(
        (SavedReport.is_shared.is_(True)) | (SavedReport.owner_email == viewer))
    if q:
        needle = f"%{q.strip()}%"
        query = query.filter(SavedReport.name.ilike(needle)
                             | SavedReport.description.ilike(needle))
    if owner == "mine":
        query = query.filter(SavedReport.owner_email == viewer)
    elif owner == "builtin":
        query = query.filter(SavedReport.builtin_key.isnot(None))
    if shared == "shared":
        query = query.filter(SavedReport.is_shared.is_(True))
    elif shared == "private":
        query = query.filter(SavedReport.is_shared.is_(False))
    return query.order_by(SavedReport.name, SavedReport.id).all()


def get_saved_report(db: Session, report_id: int, *, tenant_id: int,
                     viewer: str) -> SavedReport | None:
    """One report, or None — including when it belongs to another tenant.

    None and not a refusal: the route turns it into a 404, and a 404 is the right
    answer for "not yours". A 403 would confirm that the report exists.
    """
    report = _visible(db, tenant_id).filter(SavedReport.id == report_id).first()
    if report is None:
        return None
    if not report.is_shared and report.owner_email != viewer:
        return None
    return report


def _check_name(db: Session, name: str, *, tenant_id: int,
                exclude_id: int | None = None) -> str:
    schoon = (name or "").strip()
    if not schoon:
        raise SavedReportError("Geef het rapport een naam.")
    if len(schoon) > 120:
        raise SavedReportError("De naam is te lang (maximaal 120 tekens).")
    botsing = _visible(db, tenant_id).filter(SavedReport.name == schoon)
    if exclude_id is not None:
        botsing = botsing.filter(SavedReport.id != exclude_id)
    if botsing.first() is not None:
        raise SavedReportError(f"Er bestaat al een rapport '{schoon}'.")
    return schoon


def save_report(db: Session, *, tenant_id: int, owner: str, name: str,
                selection: Selection, description: str = "",
                is_shared: bool = True) -> SavedReport:
    """Store a new report. Commits — the transaction boundary lives here (#635)."""
    schoon = _check_name(db, name, tenant_id=tenant_id)
    report = SavedReport(
        tenant_id=tenant_id, name=schoon,
        description=(description or "").strip() or None,
        owner_email=owner, selection=selection_to_dict(selection),
        is_shared=is_shared,
    )
    db.add(report)
    db.commit()
    return report


def update_report(db: Session, report: SavedReport, *, editor: str, name: str,
                  selection: Selection, description: str = "",
                  is_shared: bool = True) -> SavedReport:
    """Change an existing report. Only its owner may — a shipped report has none.

    A report without an owner (one of the seven that ship with the release) is
    everybody's, so anyone who may see it may adjust it. That is deliberate: they
    belong to the tenant, and a board that cannot fix a shipped report would build
    a copy beside it and end up with two.
    """
    if report.owner_email is not None and report.owner_email != editor:
        raise SavedReportError(
            "Dit rapport is van iemand anders. Gebruik 'Kopiëren' om je eigen "
            "versie te maken.")
    report.name = _check_name(db, name, tenant_id=report.tenant_id,
                              exclude_id=report.id)
    report.description = (description or "").strip() or None
    report.selection = selection_to_dict(selection)
    report.is_shared = is_shared
    db.commit()
    return report


def copy_report(db: Session, report: SavedReport, *, owner: str) -> SavedReport:
    """"Kopiëren": your own copy, which never touches the original.

    The copy is private by default. Sharing is a decision, and copying something
    to try it out is not the moment to make it for somebody.
    """
    naam = f"{report.name} (kopie)"
    nummer = 2
    while _visible(db, report.tenant_id).filter(SavedReport.name == naam).first():
        naam = f"{report.name} (kopie {nummer})"
        nummer += 1
    kopie = SavedReport(
        tenant_id=report.tenant_id, name=naam[:120], description=report.description,
        owner_email=owner, selection=report.selection, is_shared=False,
    )
    db.add(kopie)
    db.commit()
    return kopie


def delete_report(db: Session, report: SavedReport, *, actor: str) -> None:
    """Remove a report. A shipped one comes back on the next deploy, by design."""
    from app.soft_delete import soft_delete

    if report.owner_email is not None and report.owner_email != actor:
        raise SavedReportError("Dit rapport is van iemand anders.")
    soft_delete(report)
    db.commit()


def mark_run(db: Session, report: SavedReport) -> None:
    """Stamp when a report was last opened, for the "laatst gedraaid" on its card."""
    from datetime import datetime, timezone

    report.last_run_at = datetime.now(timezone.utc)
    db.commit()


def selection_of(report: SavedReport, *, limit: int = 200,
                 offset: int = 0) -> Selection:
    """The stored selection, validated against today's universe.

    A report that references an object which no longer exists fails here with that
    object's name, rather than producing a table that is quietly missing a column.
    """
    return selection_from_dict(report.selection, limit=limit, offset=offset)


def classes_of(report: SavedReport) -> list[str]:
    """The universe classes a report touches — the list screen filters on them."""
    keys = (report.selection or {}).get("objects") or []
    gezien: list[str] = []
    for key in keys:
        obj: UniverseObject | None = BY_KEY.get(key)
        if obj is not None and obj.klass not in gezien:
            gezien.append(obj.klass)
    return gezien


# ── The export trail (CR-06 §7.6) ────────────────────────────────────────────

def log_export(db: Session, *, tenant_id: int, actor: str | None, kind: str,
               subject: str, row_count: int, filters: object = None,
               saved_report_id: int | None = None) -> None:
    """One row per export: who took what out, with which filters, how many rows.

    Commits on its own. An export that succeeded and a trail that did not is the
    one outcome this must never produce, and the export itself writes nothing
    else, so there is no transaction to join.
    """
    db.add(ExportLog(
        tenant_id=tenant_id, actor=actor, kind=kind, subject=subject[:200],
        row_count=row_count, filters=filters, saved_report_id=saved_report_id,
    ))
    db.commit()


@dataclass
class TileNumber:
    """One number for one dashboard tile, and the report it came from."""

    value: Any
    report_id: int | None


def dashboard_numbers(db: Session, wanted: Sequence[tuple[str, str]], *,
                      tenant_id: int, viewer: str = "") -> dict[str, TileNumber]:
    """Run one shipped report per tile and return its single number (#848).

    The dashboard is a **consumer** of reporting now, not a second implementation.
    Each of these reports is a selection with one measure and no grouping, so it
    returns one row with one number — which is what a tile is.

    **A report that fails gives an empty tile, not a broken page.** This is the
    landing page of the back office; one selection that no longer resolves —
    because an object was renamed, say — must not be the reason nobody can get in.
    The failure is logged, and the tile shows a dash, which is visibly different
    from a zero.
    """
    reports = {r.builtin_key: r for r in
               list_saved_reports(db, tenant_id=tenant_id, viewer=viewer)
               if r.builtin_key}

    uitkomst: dict[str, TileNumber] = {}
    for sleutel, maat in wanted:
        rapport = reports.get(sleutel)
        if rapport is None:
            logger.warning("dashboard tile without report: %s", sleutel)
            uitkomst[sleutel] = TileNumber(None, None)
            continue
        try:
            resultaat = run_validated(db, selection_of(rapport),
                                      tenant_id=tenant_id, viewer=viewer)
            waarde = resultaat.rows[0].get(maat) if resultaat.rows else None
        except SelectionError as exc:
            logger.warning("dashboard tile %s could not run: %s", sleutel, exc)
            waarde = None
        uitkomst[sleutel] = TileNumber(waarde, rapport.id)
    return uitkomst


__all__ = [
    "Dataset",
    "MERGED_LABEL",
    "OFFER_LIMIT",
    "ReportResult",
    "SavedReportError",
    "classes_of",
    "copy_report",
    "delete_report",
    "dimension_values",
    "TileNumber",
    "dashboard_numbers",
    "fact_columns",
    "get_saved_report",
    "list_saved_reports",
    "is_personal",
    "load_dataset",
    "log_export",
    "merge_small_cells",
    "resolve_selection",
    "mark_run",
    "run_selection",
    "run_validated",
    "save_report",
    "selection_of",
    "update_report",
    "validate_filter_values",
]