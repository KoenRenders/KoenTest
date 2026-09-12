"""Public facade of the reporting domain (#832, CR-06).

Reporting is the one domain that reads from everywhere and is imported by nobody:
it consumes the `reporting` views, which the migrations of this domain create over
the other domains' tables. The dependency runs one way only, and
`test_import_boundaries.py` keeps it that way without an allowlist entry.

That is also why this facade exports no ORM class: there is nothing to write here.
A report is a selection over views, and the only thing another module ever needs
from this domain is the vocabulary (the universe) and the two entry points that
run it.
"""
from app.domains.reporting.engine import (  # noqa: F401
    LAYOUTS,
    SYMBOLIC_LABELS,
    SYMBOLIC_ME,
    SYMBOLIC_THIS_YEAR,
    SYMBOLIC_TODAY,
    SYMBOLIC_VALUES,
    MAX_PIVOT_COLUMNS,
    MAX_ROWS,
    PEOPLE_ALIAS,
    SMALL_CELL_THRESHOLD,
    Column,
    Direction,
    Filter,
    Operator,
    QueryPlan,
    Selection,
    SelectionError,
    Sort,
    build_detail_query,
    build_member_count_query,
    build_query,
    population_of,
    selection_from_dict,
    selection_to_dict,
)
from app.domains.reporting.exports import (  # noqa: F401
    build_dataset_ods,
    build_pivot_ods,
    build_report_ods,
    dataset_filename,
    filter_summary,
    report_filename,
)
from app.domains.reporting.chart import (  # noqa: F401
    CHART_LAYOUTS,
    SERIES_COLORS,
    Chart,
    ChartData,
    build_chart,
    chart_data,
)
from app.domains.reporting.pivot import (  # noqa: F401
    Pivot,
    PivotRow,
    build_pivot,
    check_column_cap,
)
from app.domains.reporting.service import (  # noqa: F401
    MERGED_LABEL,
    OFFER_LIMIT,
    Dataset,
    ReportResult,
    SavedReportError,
    classes_of,
    copy_report,
    delete_report,
    dimension_values,
    fact_columns,
    get_saved_report,
    list_saved_reports,
    TileNumber,
    dashboard_numbers,
    is_personal,
    load_dataset,
    log_export,
    merge_small_cells,
    resolve_selection,
    mark_run,
    run_selection,
    run_validated,
    save_report,
    selection_of,
    update_report,
    validate_filter_values,
)
from app.domains.reporting.universe import (  # noqa: F401
    BY_KEY,
    CLASSES,
    DIMENSIONS,
    FACTS,
    JOINS,
    OBJECTS,
    Fact,
    Format,
    ObjectKind,
    Role,
    UniverseObject,
    classes_with_objects,
    joins_for,
    objects_in_pane_order,
)

__all__ = [
    "BY_KEY", "CHART_LAYOUTS", "CLASSES", "DIMENSIONS", "FACTS", "JOINS",
    "LAYOUTS", "MERGED_LABEL", "PEOPLE_ALIAS", "SERIES_COLORS",
    "SMALL_CELL_THRESHOLD", "SYMBOLIC_LABELS", "SYMBOLIC_ME",
    "SYMBOLIC_THIS_YEAR", "SYMBOLIC_TODAY", "SYMBOLIC_VALUES",
    "MAX_PIVOT_COLUMNS", "MAX_ROWS", "OBJECTS", "OFFER_LIMIT",
    "Chart", "ChartData", "Column", "Dataset", "Direction", "Fact", "Filter",
    "Format", "ObjectKind",
    "Operator", "Pivot", "PivotRow", "QueryPlan", "ReportResult", "Role",
    "SavedReportError", "Selection", "SelectionError", "Sort", "TileNumber",
    "UniverseObject",
    "build_dataset_ods", "build_detail_query", "build_member_count_query",
    "build_chart", "build_pivot", "build_pivot_ods", "build_query",
    "build_report_ods", "chart_data",
    "check_column_cap", "classes_of", "classes_with_objects", "copy_report",
    "dashboard_numbers", "dataset_filename",
    "delete_report", "dimension_values", "fact_columns", "filter_summary",
    "population_of",
    "get_saved_report", "joins_for", "list_saved_reports", "load_dataset",
    "is_personal", "log_export", "mark_run", "merge_small_cells",
    "objects_in_pane_order", "report_filename", "resolve_selection",
    "run_selection", "run_validated", "save_report", "selection_from_dict",
    "selection_of", "selection_to_dict", "update_report", "validate_filter_values",
]
