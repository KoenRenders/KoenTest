"""A local run's own database on a server that already exists (#1891).

The three local scripts make their database by asking the `db` container of the
dev stack. With `EXISTING_DB_URL` set there is no such container to ask — the
server belongs to someone else, and may only be reachable over a unix socket
mounted into the helper container — so the helper container does it itself,
over that URL:

    ADMIN_DATABASE_URL=… python -m tests._local_db create   raaktest_<name>
    ADMIN_DATABASE_URL=… python -m tests._local_db recreate raake2e_<name>

`create` leaves a database that exists alone (the pytest suite resets its own
schema); `recreate` drops it first (the browser tests and the measurement run
consume or freeze their seed).

The name is checked here too, after the script's own guard: this is the module
that says DROP DATABASE, and it can be called by hand.
"""

import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from tests._worker_db import fresh_worker_database

#: What a database of a local run is called: the prefixes of the three scripts.
PREFIXES = ("raaktest", "raake2e", "raakmeet")


def is_a_local_run_database(name: str) -> bool:
    return any(name == prefix or name.startswith(f"{prefix}_") for prefix in PREFIXES)


def _refuse_another_name(name: str) -> None:
    if not is_a_local_run_database(name):
        raise SystemExit(
            f"tests._local_db: REFUSED — '{name}' does not read as the database of a local run."
        )


def create(admin_url: str, name: str) -> None:
    """Make the database when it is not there; one that exists is left alone."""
    _refuse_another_name(name)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            found = conn.exec_driver_sql(
                "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
            ).first()
            if found is None:
                conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    finally:
        admin.dispose()


def recreate(admin_url: str, name: str) -> None:
    """Drop the database and make it again, empty."""
    _refuse_another_name(name)
    own_url = make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    fresh_worker_database(admin_url, own_url)


def main(arguments: list[str]) -> None:
    actions = {"create": create, "recreate": recreate}
    if len(arguments) != 2 or arguments[0] not in actions:
        raise SystemExit("usage: python -m tests._local_db create|recreate <database name>")
    admin_url = os.environ.get("ADMIN_DATABASE_URL")
    if not admin_url:
        raise SystemExit("tests._local_db: ADMIN_DATABASE_URL is not set")
    actions[arguments[0]](admin_url, arguments[1])


if __name__ == "__main__":
    main(sys.argv[1:])
