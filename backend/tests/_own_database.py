"""A database of its own for a migration test: the chain to a revision, the test's
cases written in raw SQL, then the migration under test (CR-20, CR-26).

The suite's database runs the whole chain on the seed only; a migration that moves
rows needs rows the seed lacks, written in the schema *before* it. One helper for
every such test — CR-20's, CR-26 phase 1's and phase 3's each had a copy of it.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


@contextmanager
def own_database(name: str):
    """Yields `(upgrade, engine)`: `upgrade(revision)` runs the chain to that
    revision on a fresh database named after the suite's with `_<name>`, which is
    dropped afterwards."""
    from tests.conftest import TEST_DATABASE_URL

    url = make_url(TEST_DATABASE_URL)
    own = url.set(database=f"{url.database}_{name}")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{own.database}" WITH (FORCE)')
        conn.exec_driver_sql(f'CREATE DATABASE "{own.database}"')
    rendered = own.render_as_string(hide_password=False)
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = rendered
    engine = create_engine(rendered)
    try:
        yield (lambda revision: command.upgrade(cfg, revision)), engine
    finally:
        engine.dispose()
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        with admin.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{own.database}" WITH (FORCE)')
        admin.dispose()
