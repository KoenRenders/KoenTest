"""A test database per pytest-xdist worker (CR-29 F1).

The suite drops every schema and runs the migration chain once per process
(`_migrate_schema` in `conftest.py`). Four processes on one database would reset
each other's schema, so each worker gets a database of its own: the base name
plus the worker's name (`raaktest_gw0` … `raaktest_gw3`).

This module imports nothing from `app`: `conftest.py` needs the worker's URL
BEFORE `app.database` is imported, because the engine is created at that import.
A fixture would be too late.
"""

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


def worker_database_url(base_url: str, worker: str) -> str:
    """The URL a worker runs on: the base URL with `_<worker>` after the database name.

    Without a worker (a run in one process) the base URL comes back unchanged.
    """
    if not worker:
        return base_url
    url = make_url(base_url)
    return url.set(database=f"{url.database}_{worker}").render_as_string(hide_password=False)


def fresh_worker_database(base_url: str, worker_url: str) -> None:
    """Give the worker an EMPTY database of its own; a run in one process is left alone.

    Dropped and created, not emptied schema by schema. The sweep of CR-29 showed
    why: the suite's own reset drops every schema in one transaction, and four
    workers doing that at once on databases a previous run had filled ran the
    server out of lock space ("out of shared memory", `max_locks_per_transaction`)
    — half of a run's tests errored. Dropping a database takes no lock per table,
    and on an empty one the schema reset that follows has nothing to lock.

    Through a connection of its own to the BASE database, in autocommit: neither
    statement can run inside a transaction, and the worker's database is the one
    thing that connection must not be connected to.
    """
    if worker_url == base_url:
        return
    name = make_url(worker_url).database
    admin = create_engine(base_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    finally:
        admin.dispose()
