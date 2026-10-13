# reporting — component contract (CR-06, #832; written in CR-13 phase 4)

## Purpose and process

**Purpose.** Reports over the whole association: a universe of objects (dimensions
and facts, in Dutch labels) that a board member picks from, run as a selection over
the `reporting` views, shown as a table, a pivot or a chart, saved, shared and
exported; the dashboard's numbers; and the assistant that turns a question into a
selection, with every name masked on its way to the language model (CR-07).

*Process (A2.4.4 — reporting and the change report).* Its own records are `SavedReport` and `ExportLog`; everything else it shows is read from the other domains through views.

## Publishes

### Facade (`api.py`) — the only door for other components and for this component's screens

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
  `TileNumber` — used by `app/ui/system_ui.py`.
- **The change report** (`changes.py`; here since CR-13 phase 4c, when the audit
  package left): `all_changes_since`, `member_changes_since`,
  `build_member_changes_ods`, `GROUPS` — what changed since a date, read from the
  history tables of activities, mdm, membership and payment through their
  facades (each owner writes its own history, `<domain>/history.py`). Used by
  `app/ui/changes_ui.py`: the two change screens and their .ods export.

Two modules outside this domain import it, both screens: `app/ui/system_ui.py`
and `app/ui/changes_ui.py` (`test_reporting_terminus_gate.py` holds the list).

### Events

None published, none subscribed.

### JSON routes

None. The screens are server-rendered (`admin_ui.py`); there is no `/api/v1` route.

*Counted in the code on 13 October 2026:* the facade exports 91 names (46 functions, 23 classes, 22 values); events it owns (`kernel/contracts/`): none; ports it offers: none.

## Consumes

*Counted in the code on 13 October 2026:* imports the facades of activities, auth, chatbot, mdm, membership, newsletter, payment; subscribes to no event; calls no port.

## Owns

### Data

Schema `reporting`: `saved_reports`, `export_log`, and the code list
`export_kind_codes`/`export_kind_labels`. The views the reports read (`d_*`, `f_*`)
are created by this domain's migrations over the other domains' tables.

**The dependency runs one way.** Reporting reads from everywhere through its views
and is imported by nobody but the dashboard; it writes only its own tables. A
report computes in SQL what an owner computes in Python — the one declared second
computation of CR-13 (§B4.3), bound by parity tests (the open amount against
`registration_balance`, #1249).

*Counted in the code on 13 October 2026:* schema `reporting`, 4 tables (2 data, 2 code and label), 2 of them with `tenant_id`; status columns: none; jobs: none.

## Screens

`admin_ui.py`: 17 routes under `/admin/rapporten`. The dashboard and the two change screens are drawn by `app/ui/` and ask this facade.

## Deprecations

None: no part of this contract is in its deprecation cycle.

## Standards

| Standard | Element | Our name | Follows / deviates, with the reason |
|---|---|---|---|
| OpenDocument | Spreadsheet (ODS), cells typed | every export: a report, a pivot, a dataset, the change report (`exports.py`, `changes.py`) | follows (#200) |

## Rules and gates

- **Rules whose home is this module** — No `@validates` and no `check()` in `models.py`; no `CheckConstraint` there. Its rules stand in its service. The universe (`universe.py`) is the vocabulary a selection is checked against.
- **Gates in this module's own `tests/`** — `test_reporting_detail_gate.py` (a report that groups on a detail attribute), `test_reporting_fanout_gate.py` (a measure that double-counts), `test_reporting_shipped_reports_gate.py` (a shipped report that no longer runs or exports), `test_reporting_universe_gate.py` (a universe object that does not resolve against the database). Beside them in `backend/tests/`: `test_reporting_terminus_gate.py`.

## Evolutions

Ids of part E of the architecture document, as it stood on 13 October 2026.

- **E16** — Raakje in the back office (CR-07): built in v2.5.0.
- **E24** — the tenant apart from the organisation (CR-20): the universe reads the tenant by its key; decided, on no release.
- **E38** — the close-out of the status lines of CR-06 and CR-07.
