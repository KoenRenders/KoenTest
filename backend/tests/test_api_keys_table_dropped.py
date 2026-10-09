"""The table `auth.api_keys` leaves, and only when it is empty (#1251, the auth cut).

Migration `199_2026_10_09_034931` drops the table of a feature that never had a
consumer. It was empty on PROD, UAT and HDEV when the migration was written — and
the migration does not take that on trust: a table that holds a row is not
dropped, the deploy stops. Held here on the migration's own function, inside the
test's transaction.

Proven red (9 October 2026): the count taken out of `drop_if_empty` → the table
with a key in it is dropped and the first test fails.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.ui_agnostisch

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "199_2026_10_09_034931_drop_auth_api_keys.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("migration_drop_api_keys", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _exists(connection) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'auth' AND table_name = 'api_keys'"
            )
        ).scalar()
    )


def _the_table_as_it_was(connection) -> None:
    connection.execute(
        text(
            "CREATE TABLE auth.api_keys (id serial PRIMARY KEY, name varchar(100) NOT NULL, "
            "key_hash varchar(64) NOT NULL, is_active boolean NOT NULL DEFAULT true)"
        )
    )


def test_the_schema_at_head_has_no_api_keys_table(db_session):
    assert not _exists(db_session.connection())


def test_a_table_that_holds_a_key_is_not_dropped(db_session):
    connection = db_session.connection()
    _the_table_as_it_was(connection)
    connection.execute(
        text("INSERT INTO auth.api_keys (name, key_hash) VALUES ('a consumer', 'not-a-real-hash')")
    )
    with pytest.raises(RuntimeError, match="holds 1 row"):
        _migration().drop_if_empty(connection)
    assert _exists(connection), "the table must still be there for whoever comes to ask"


def test_an_empty_table_is_dropped_and_a_missing_one_is_left_alone(db_session):
    connection = db_session.connection()
    _the_table_as_it_was(connection)
    migration = _migration()
    assert migration.drop_if_empty(connection) is True
    assert not _exists(connection)
    assert migration.drop_if_empty(connection) is False  # run twice: nothing to do
