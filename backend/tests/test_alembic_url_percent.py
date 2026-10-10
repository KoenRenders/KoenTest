"""#1897 — a database URL with a percent sign reaches alembic.

`alembic/env.py` hands `DATABASE_URL` to alembic's `Config`, which keeps its
options in a configparser. A bare `%` there is the start of an interpolation:
`ValueError: invalid interpolation syntax in 'postgresql+psycopg2://…'`. A URL
holds a `%` as soon as anything in it is percent-encoded:

* the socket directory of `?host=` once SQLAlchemy has rendered the URL — which
  `tests/_worker_db.worker_database_url` does for every pytest-xdist worker. So
  the full local run in four processes over a unix socket (#1891) stopped at
  the set-up of every test, while a run in one process, whose URL is not
  rendered, went through;
* a password with a special character, on any road — also at the start of the
  application on an environment.

Both are one fault, at the one place that feeds alembic, and `env.py` doubles
the `%` there.

Broken to check that these can go red (run with scripts/test-local.sh, not
reasoned; restored afterwards): `.replace("%", "%%")` taken off the line in
`alembic/env.py` → all three tests fail with the ValueError above — the two that
expect a refused connection get the ValueError in its place. And the `%`
quadrupled instead of doubled → `test_the_percent_sign_arrives_as_one` fails:
the server refuses the option, "-c % requires a value".
"""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from tests._worker_db import worker_database_url

pytestmark = pytest.mark.ui_agnostisch

BACKEND = os.path.dirname(os.path.dirname(__file__))


def _alembic_current(monkeypatch, url: str) -> None:
    """`alembic current` on `url`: the smallest command that runs `env.py` and
    connects, as the upgrade of the suite's set-up and of `startup.sh` does."""
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.chdir(BACKEND)
    command.current(Config(os.path.join(BACKEND, "alembic.ini")))


def test_a_workers_url_over_a_unix_socket_reaches_alembic(monkeypatch):
    """The road of #1897 itself: a socket-form base URL, made a worker's.

    Nothing listens in that directory, so past alembic's own configuration the
    connection is refused — which is the proof that the URL got that far.
    """
    base = "postgresql+psycopg2://u:p@/raaktest_proef?host=/nowhere/at/all"
    url = worker_database_url(base, "gw0")
    assert "%2F" in url, "the worker URL is no longer percent-encoded; this test proves nothing"

    with pytest.raises(OperationalError):
        _alembic_current(monkeypatch, url)


def test_a_password_with_a_percent_sign_reaches_alembic(monkeypatch):
    """The same fault by another road: a special character in a password is
    written percent-encoded in a URL."""
    url = "postgresql+psycopg2://u:p%25q%40r@/raaktest_proef?host=/nowhere/at/all"
    assert make_url(url).password == "p%q@r"

    with pytest.raises(OperationalError):
        _alembic_current(monkeypatch, url)


def test_the_percent_sign_arrives_as_one(monkeypatch):
    """The counterpart: doubled on the way in, single again on the way out.

    On the suite's own server, with a start-up option written percent-encoded:
    `-c search_path=public`. With the `%` single the server gets exactly that and
    the command runs. Had it stayed doubled, the option would read
    `-c% search_path=public`, which the server refuses — so a command that runs
    is the proof.
    """
    from tests.conftest import TEST_DATABASE_URL

    base = make_url(TEST_DATABASE_URL).render_as_string(hide_password=False)
    joiner = "&" if "?" in base else "?"
    url = f"{base}{joiner}options=-c%20search_path%3Dpublic"

    _alembic_current(monkeypatch, url)
