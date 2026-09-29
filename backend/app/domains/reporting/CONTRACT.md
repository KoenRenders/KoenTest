# reporting — component contract (CR-06, #832; written in CR-13 phase 4)

**Purpose.** Reports over the whole association: a universe of objects (dimensions
and facts, in Dutch labels) that a board member picks from, run as a selection over
the `reporting` views, shown as a table, a pivot or a chart, saved, shared and
exported; the dashboard's numbers; and the assistant that turns a question into a
selection, with every name masked on its way to the language model (CR-07).

## Facade (`api.py`) — the only door for other components and for this component's screens

- **The universe** (`universe.py`): `OBJECTS`, `BY_KEY`, `CLASSES`, `DIMENSIONS`,
  `FACTS`, `HIERARCHIES`, `HIERARCHY_OF`, `JOINS`, `UniverseObject`, `Fact`,
  `Format`, `ObjectKind`, `Role`, `classes_with_objects`, `joins_for`,
  `objects_in_pane_order` — the vocabulary; the key is an identifier, the label copy.
- **Running a selection** (`engine.py`, `service.py`): `Selection`, `Filter`,
  `Sort`, `Column`, `Direction`, `Operator`, `Layout`, `QueryPlan`,
  `SelectionError`, `build_query`, `build_detail_query`, `build_member_count_query`,
  `run_selection`, `run_validated`, `resolve_selection`, `validate_filter_values`,
  `dimension_values`, `fact_columns`, `load_dataset`, `population_of`,
  `selection_from_dict`, `selection_to_dict`, `values_from_fact_sql`, and the
  symbolic values (`SYMBOLIC_TODAY`, `SYMBOLIC_THIS_YEAR`, `SYMBOLIC_ME`, …).
- **Saved reports**: `save_report`, `update_report`, `copy_report`, `delete_report`,
  `may_delete`, `get_saved_report`, `list_saved_reports`, `is_personal`,
  `mark_run`, `selection_of`, `classes_of`, `SavedReportError`.
- **Showing and exporting** (`pivot.py`, `chart.py`, `exports.py`): `build_pivot`,
  `check_column_cap`, `Pivot`, `PivotRow`, `build_chart`, `chart_data`, `Chart`,
  `ChartData`, `CHART_LAYOUTS`, `SERIES_COLORS`, `build_report_ods`,
  `build_pivot_ods`, `build_dataset_ods`, `report_filename`, `dataset_filename`,
  `filter_summary`, `log_export`, `ExportKind`, `EXPORT_KIND`.
- **The dashboard**: `dashboard_numbers`, `dashboard_tile_of`, `DASHBOARD_TEGELS`,
  `TileNumber` — used by `app/ui/system_ui.py`, the one module outside this domain
  that imports it.

## Data

Schema `reporting`: `saved_reports`, `export_log`, and the code list
`export_kind_codes`/`export_kind_labels`. The views the reports read (`d_*`, `f_*`)
are created by this domain's migrations over the other domains' tables.

**The dependency runs one way.** Reporting reads from everywhere through its views
and is imported by nobody but the dashboard; it writes only its own tables. A
report computes in SQL what an owner computes in Python — the one declared second
computation of CR-13 (§B4.3), bound by parity tests (the open amount against
`registration_balance`, #1249).

## Events

None published, none subscribed.

## JSON routes

None. The screens are server-rendered (`admin_ui.py`); there is no `/api/v1` route.
