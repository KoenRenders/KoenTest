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
    MAX_ROWS,
    Column,
    Direction,
    Filter,
    Operator,
    QueryPlan,
    Selection,
    SelectionError,
    Sort,
    build_query,
)
from app.domains.reporting.exports import (  # noqa: F401
    build_dataset_ods,
    dataset_filename,
)
from app.domains.reporting.service import (  # noqa: F401
    Dataset,
    ReportResult,
    fact_columns,
    load_dataset,
    run_selection,
)
from app.domains.reporting.universe import (  # noqa: F401
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
    "CLASSES", "DIMENSIONS", "FACTS", "JOINS", "MAX_ROWS", "OBJECTS",
    "Column", "Dataset", "Direction", "Fact", "Filter", "Format", "ObjectKind",
    "Operator", "QueryPlan", "ReportResult", "Role", "Selection",
    "SelectionError", "Sort", "UniverseObject",
    "build_dataset_ods", "build_query", "classes_with_objects", "dataset_filename",
    "fact_columns", "joins_for", "load_dataset", "objects_in_pane_order",
    "run_selection",
]
