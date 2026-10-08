"""The suite's session is configured as the app's (#1771).

The fixture used to build its own `sessionmaker(bind=connection)`, with
SQLAlchemy's default autoflush; the app's `SessionLocal` runs without. A service
that adds a row and looks it up again in the same request found it in the suite
and not in the app — a page could not be created on a local test version while
every test passed. The fixture now asks the app's own factory for its session,
so there is one place where a session's options are written.

Proven red (8 October 2026): `sessionmaker(bind=connection)()` put back in the
`db_session` fixture → the first test fails on "the suite flushes where the app
does not", the second on a row found that the app would not have found.
"""

from datetime import datetime, timezone

import pytest

from app.database import SessionLocal
from app.kernel.jobs import KernelJob

pytestmark = pytest.mark.ui_agnostisch


def test_the_suite_session_has_the_options_of_the_app_session(db_session):
    of_the_app = SessionLocal()
    try:
        assert db_session.autoflush is of_the_app.autoflush, (
            "the suite flushes where the app does not"
        )
        assert db_session.expire_on_commit is of_the_app.expire_on_commit
    finally:
        of_the_app.close()


def test_a_row_that_was_only_added_is_not_found_by_a_query(db_session):
    """What the app's setting means, by its behaviour: an added row is not sent
    to the database by the next query, only by a flush or a commit."""
    db_session.add(KernelJob(name="only.added.1771", payload={}, run_at=datetime.now(timezone.utc)))

    def found() -> int:
        return db_session.query(KernelJob).filter(KernelJob.name == "only.added.1771").count()

    assert found() == 0
    db_session.flush()
    assert found() == 1
