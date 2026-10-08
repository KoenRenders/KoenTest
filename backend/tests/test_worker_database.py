"""CR-29 F1 — every pytest-xdist worker runs on a database of its own.

The suite drops every schema and runs the migration chain once per process. Four
processes on one database would reset each other's schema in the middle of a run,
with errors about missing tables that have nothing to do with the change under
test. So the worker's name goes into the database name — and it goes in where the
URL is set, at the top of `conftest.py`, because `app.database` creates the engine
at import. A fixture that renames the database runs after that and changes nothing.

That is why the second test asks the ENGINE and the database itself, not a name
some helper computed: a suffix applied too late computes the right name and still
runs four workers on one database.

Broken to check that these can go red (run under `-n 2`, not reasoned):
  * `worker_database_url` returning the base URL for every worker → the first
    helper test fails, and the engine test fails in every worker;
  * in `conftest.py`, `os.environ["DATABASE_URL"]` set to the BASE url → the
    engine test fails in every worker on `raaktest…` without `_gw<n>`, while the
    helper tests stay green — which is the case the engine test exists for.
"""

import ast
import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.database import engine
from tests._worker_db import worker_database_url
from tests.conftest import BASE_DATABASE_URL

pytestmark = pytest.mark.ui_agnostisch

BASE = "postgresql+psycopg2://tester:s3cret@db:5432/raaktest_proef"


def test_a_worker_gets_the_base_name_plus_its_own():
    url = make_url(worker_database_url(BASE, "gw2"))

    assert url.database == "raaktest_proef_gw2"
    # Everything else of the URL survives — the password too, which a rendered
    # URL hides by default and would then fail to sign in with.
    assert (url.username, url.password, url.host, url.port) == ("tester", "s3cret", "db", 5432)


def test_a_run_in_one_process_keeps_the_base_database():
    assert worker_database_url(BASE, "") == BASE


def test_the_engine_is_bound_to_the_database_of_this_worker(db_session):
    worker = os.environ.get("PYTEST_XDIST_WORKER", "")
    base = make_url(BASE_DATABASE_URL).database
    expected = f"{base}_{worker}" if worker else base

    assert engine.url.database == expected
    assert db_session.execute(text("SELECT current_database()")).scalar() == expected


def test_the_helper_imports_nothing_of_the_app():
    """It runs before `app.database` is imported; importing `app` would create the engine."""
    tree = ast.parse((Path(__file__).parent / "_worker_db.py").read_text(encoding="utf-8"))
    imported = [
        node.module if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]
    assert imported, "no imports found — the walk looked at nothing"
    assert not [name for name in imported if name == "app" or name.startswith("app.")]
