"""#1891 — the local test scripts can use a database server that already runs.

`scripts/test-local.sh`, `e2e-local.sh` and `measure-local.sh` started the `db`
service of the dev stack, read its credentials out of that container and ran
their helper container on the compose network. A builder that runs as a system
user of its own cannot start that container at all, so it ran no browser test
and no measurement baseline. `EXISTING_DB_URL` — and `EXISTING_DB_SOCKET_DIR`
for a server reached over a unix socket — is the switch
(`scripts/local-db-lib.sh`).

What stands here:

* **with both unset the scripts call what they called before** — the docker
  calls of each are compared with a recording made on the scripts as they were
  (`tests/snapshots/local_runner_calls/`);
* **with the switch on**: no `compose`, no credential read, no `dev_internal`,
  and the mount when a socket directory is given;
* **the name guards**, which matter more now that the target is a server the
  script did not start: a wrong name is refused before any docker call, with the
  switch on, in the host form and in the socket form of the URL. And the name is
  parsed out of a URL, also where its last "/" stands inside `?host=` — in
  `test-local.sh` (`TEST_DATABASE_URL`) and in `measure-run.sh` (`DATABASE_URL`),
  the fourth place that read a URL.

A fake `docker` on the PATH records every call, as in `test_lokale_testrunner.py`:
the invariant of a refusal is not its exit code but that nothing was touched.

Broken to check that these can go red (run with scripts/test-local.sh, not
reasoned; each restored afterwards):

* `test-local.sh`: the parsed name replaced by the old cut,
  `DB_NAAM="${TEST_DATABASE_URL##*/}"` and the query taken off → the two socket
  cases of `test_a_whole_url_is_read_by_its_database_name` fail: the wrong name
  with `raaktest_sockets` in `?host=` is let through to docker, and the right
  name is refused because `sockets` was read;
* `measure-run.sh`: the `case` put back on the URL's text,
  `*/raakmeet|*/raakmeet_*` on `$DATABASE_URL` → the socket case with a wrong
  name of `test_the_measurement_run_reads_the_name_not_the_text` fails: no
  REFUSED;
* `test-local.sh`, `e2e-local.sh`, `measure-local.sh`, one at a time: the
  guard's pattern widened to `*)` → that script's four cases of
  `test_a_wrong_name_is_refused_with_the_switch_on` fail with returncode 0 and
  a trace that is not empty;
* `e2e-local.sh`: `RUN_ARGS=(--network "$NETWERK")` moved from inside the `if`
  to below it → `test_the_switch_leaves_the_dev_stack_alone` fails for that
  script in both URL forms and `test_a_socket_directory_is_mounted` fails:
  `dev_internal` is back and the mount is gone;
* `tests/_local_db.py`: the condition of `_refuse_another_name` replaced by
  `False` → the six cases of `test_another_name_is_refused_by_the_module_too`
  fail on the connection the module then attempts.

#1893 — the user of `test-local.sh`'s helper container. In a rootless Docker a
container only runs as root, and that script passed no user, so its container
started as the image's own and stopped at once. `HELPER_CONTAINER_USER` names
the user; unset, the calls are those of before (the recording above). Broken:

* `test-local.sh`: `"${USER_ARGS[@]}"` taken off the `docker run` line →
  `test_the_named_user_reaches_the_helper_container` fails: no `-u root`.

#1894 — `git` and a `psql` client in the helper container, for the seven tests
of the suite that run them. Installed by the script, as root, once per
container; the recording of `test-local.sh` gained that one call. Broken:

* `test-local.sh`: `-u root` taken off the install line →
  `test_git_and_psql_are_installed_as_root_from_debians_own_archive` fails:
  the install would run as the container's user, who may not install.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from tests._local_db import create, is_a_local_run_database, recreate

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
RECORDED = Path(__file__).resolve().parent / "snapshots" / "local_runner_calls"

pytestmark = pytest.mark.ui_agnostisch

#: Everything in the caller's environment that steers these scripts.
SWITCHES = (
    "TEST_DATABASE_URL",
    "TEST_DB_NAME",
    "E2E_DB_NAME",
    "MEASURE_DB_NAME",
    "EXISTING_DB_URL",
    "EXISTING_DB_SOCKET_DIR",
    "HELPER_CONTAINER_USER",
    "DATABASE_URL",
    "SNEL",
    "VERS",
)

#: The two forms of the switch: a host, and a unix socket (libpq: nothing between
#: "@" and "/", the directory in ?host=). Made-up values; nothing listens.
HOST_URL = "postgresql+psycopg2://u:p@dbhost:5432/postgres"
SOCKET_URL = "postgresql+psycopg2://u:p@/postgres?host=/sockets"

#: Per script: how the helper container is found, what makes the run short, the
#: variable that overrides its database name, and the name it derives. The
#: checkout of `_run` is a folder called "checkout", so that is the slug.
LOCAL_SCRIPTS = {
    "test-local.sh": ("missing", {"SNEL": "1"}, "TEST_DB_NAME", "raaktest_checkout"),
    "e2e-local.sh": ("missing", {}, "E2E_DB_NAME", "raake2e_checkout"),
    "measure-local.sh": ("running", {}, "MEASURE_DB_NAME", "raakmeet_checkout"),
}


def _run(tmp_path, script, *arguments, helper="missing", **environment):
    """Run a script in a checkout of its own, with a fake `docker` that records.

    `helper` is what `docker inspect` says of the helper container: "missing"
    (the script then creates it, so its `docker run` shows) or "running".
    """
    root = tmp_path / "checkout"
    shutil.copytree(SCRIPTS, root / "scripts")
    (root / "backend").mkdir()
    for name in ("requirements.txt", "requirements-dev.txt"):
        (root / "backend" / name).write_text("")
    trace = tmp_path / "docker-calls.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    inspect = "echo true" if helper == "running" else "exit 1"
    (fake_bin / "docker").write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{trace}"\n'
        'case "$*" in\n'
        '  *"printenv POSTGRES_USER"*) echo u ;;\n'
        '  *"printenv POSTGRES_PASSWORD"*) echo p ;;\n'
        f"  inspect*) {inspect} ;;\n"
        "esac\n"
        "exit 0\n"
    )
    (fake_bin / "docker").chmod(0o755)

    env = dict(os.environ)
    for name in SWITCHES:
        env.pop(name, None)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env.update(environment)
    done = subprocess.run(
        ["bash", str(root / "scripts" / script), *arguments],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    calls = trace.read_text().splitlines() if trace.exists() else []
    # The checkout's path and the checksum of the requirement files differ by place.
    calls = [re.sub(r"'[0-9a-f]{16}'", "'<sum>'", c.replace(str(root), "<root>")) for c in calls]
    return done, calls


def _run_local(tmp_path, script, **environment):
    helper, short, _name_variable, _derived = LOCAL_SCRIPTS[script]
    return _run(tmp_path, script, helper=helper, **short, **environment)


# ── Both unset: what the scripts called before ───────────────────────────────


@pytest.mark.parametrize("script", LOCAL_SCRIPTS)
def test_without_the_switch_the_calls_are_those_of_before(tmp_path, script):
    """Compared call by call with the recording made before #1891 touched the scripts."""
    done, calls = _run_local(tmp_path, script)

    assert done.returncode == 0, done.stderr
    recorded = (RECORDED / f"{script}.txt").read_text().splitlines()
    assert len(recorded) >= 7, "the recording is empty or cut short"
    assert calls == recorded


# ── The switch ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("script", LOCAL_SCRIPTS)
@pytest.mark.parametrize("url", [HOST_URL, SOCKET_URL])
def test_the_switch_leaves_the_dev_stack_alone(tmp_path, script, url):
    done, calls = _run_local(tmp_path, script, EXISTING_DB_URL=url)

    assert done.returncode == 0, done.stderr
    assert calls, "the script reached docker not at all"
    everything = "\n".join(calls)
    assert "compose" not in everything, "the script still asked the dev stack"
    assert "printenv" not in everything, "the script still read credentials from a container"
    assert "dev_internal" not in everything
    assert "--network" not in everything


@pytest.mark.parametrize("script", LOCAL_SCRIPTS)
def test_the_run_gets_its_own_database_on_the_given_server(tmp_path, script):
    """User, password and host of the given URL; the name the script derives itself."""
    _helper, _short, _name_variable, derived = LOCAL_SCRIPTS[script]
    done, calls = _run_local(tmp_path, script, EXISTING_DB_URL=HOST_URL)

    assert done.returncode == 0, done.stderr
    action = "create" if script == "test-local.sh" else "recreate"
    made = [call for call in calls if f"python -m tests._local_db {action} {derived}" in call]
    assert len(made) == 1, f"expected one call that makes {derived}, found {len(made)}"
    assert f"-e ADMIN_DATABASE_URL={HOST_URL} " in made[0]
    assert f"=postgresql+psycopg2://u:p@dbhost:5432/{derived} " in calls[-1], (
        f"the run itself does not go to {derived} on the given server: {calls[-1]}"
    )


@pytest.mark.parametrize("script", LOCAL_SCRIPTS)
def test_a_socket_url_keeps_its_socket_directory(tmp_path, script):
    _helper, _short, _name_variable, derived = LOCAL_SCRIPTS[script]
    done, calls = _run_local(tmp_path, script, EXISTING_DB_URL=SOCKET_URL)

    assert done.returncode == 0, done.stderr
    assert f"=postgresql+psycopg2://u:p@/{derived}?host=/sockets " in calls[-1], calls[-1]


@pytest.mark.parametrize("script", ["test-local.sh", "e2e-local.sh"])
def test_a_socket_directory_is_mounted(tmp_path, script):
    """Where the URL's ?host= points, in the helper container. `measure-local.sh`
    creates no container: it runs in the one `e2e-local.sh` made."""
    done, calls = _run_local(
        tmp_path, script, EXISTING_DB_URL=SOCKET_URL, EXISTING_DB_SOCKET_DIR="/given/by/the/runner"
    )

    assert done.returncode == 0, done.stderr
    created = [call for call in calls if call.startswith("run ")]
    assert len(created) == 1, f"expected one docker run, found {len(created)}"
    assert " -v /given/by/the/runner:/sockets " in created[0], created[0]


@pytest.mark.parametrize("script", ["test-local.sh", "e2e-local.sh"])
def test_without_a_socket_directory_nothing_is_mounted_but_the_checkout(tmp_path, script):
    """The counterpart: a mount that is always there proves nothing."""
    done, calls = _run_local(tmp_path, script, EXISTING_DB_URL=SOCKET_URL)

    assert done.returncode == 0, done.stderr
    created = [call for call in calls if call.startswith("run ")]
    assert len(created) == 1
    assert created[0].count(" -v ") == 1, created[0]


# ── The name guards ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("script", LOCAL_SCRIPTS)
@pytest.mark.parametrize("url", [HOST_URL, SOCKET_URL])
@pytest.mark.parametrize("name", ["raakmillegem", "postgres"])
def test_a_wrong_name_is_refused_with_the_switch_on(tmp_path, script, url, name):
    """Before any docker call: the server is not one the script started itself."""
    _helper, _short, name_variable, _derived = LOCAL_SCRIPTS[script]
    done, calls = _run_local(tmp_path, script, EXISTING_DB_URL=url, **{name_variable: name})

    assert done.returncode == 2, done.stderr or done.stdout
    assert name in done.stderr
    assert calls == [], "the script called docker before it refused"


@pytest.mark.parametrize(
    ("url", "refused"),
    [
        ("postgresql+psycopg2://u:p@dbhost:5432/raakmillegem", True),
        # The old reading — everything after the last "/" — saw `raaktest_sockets` here.
        ("postgresql+psycopg2://u:p@/raakmillegem?host=/run/raaktest_sockets", True),
        ("postgresql+psycopg2://u:p@dbhost:5432/raaktest_proef", False),
        ("postgresql+psycopg2://u:p@/raaktest_proef?host=/run/sockets", False),
        ("not a url", True),
    ],
)
def test_a_whole_url_is_read_by_its_database_name(tmp_path, url, refused):
    """`TEST_DATABASE_URL` names the database itself, in either form."""
    done, calls = _run(tmp_path, "test-local.sh", SNEL="1", TEST_DATABASE_URL=url)

    if refused:
        assert done.returncode == 2, done.stderr or done.stdout
        assert calls == [], "the script called docker before it refused"
    else:
        assert done.returncode == 0, done.stderr
        assert f"TEST_DATABASE_URL={url} " in calls[-1]


@pytest.mark.parametrize(
    ("url", "refused"),
    [
        ("postgresql+psycopg2://u:p@dbhost:5432/raakmillegem", True),
        # The old pattern on the URL's text matched "/raakmeet_" in the directory.
        ("postgresql+psycopg2://u:p@/raakmillegem?host=/run/raakmeet_sockets", True),
        ("postgresql+psycopg2://u:p@dbhost:5432/raakmeet_proef", False),
        ("postgresql+psycopg2://u:p@/raakmeet_proef?host=/run/sockets", False),
    ],
)
def test_the_measurement_run_reads_the_name_not_the_text(tmp_path, url, refused):
    """`scripts/measure-run.sh` (CI calls it too) has a guard of its own on
    `DATABASE_URL`. Past the guard this checkout has no measurement to run, so
    the script stops on something else — what counts is which sentence it says."""
    done, _calls = _run(tmp_path, "measure-run.sh", DATABASE_URL=url)

    assert done.returncode != 0
    assert ("REFUSED" in done.stderr) is refused, done.stderr


# ── A switch that is set halfway ─────────────────────────────────────────────


@pytest.mark.parametrize("script", LOCAL_SCRIPTS)
@pytest.mark.parametrize(
    ("environment", "names"),
    [
        ({"EXISTING_DB_SOCKET_DIR": "/given"}, "EXISTING_DB_SOCKET_DIR"),
        ({"EXISTING_DB_URL": "not a url"}, "EXISTING_DB_URL"),
        ({"EXISTING_DB_URL": HOST_URL, "EXISTING_DB_SOCKET_DIR": "/given"}, "?host="),
    ],
)
def test_a_switch_set_halfway_is_refused(tmp_path, script, environment, names):
    """A directory without a URL, a URL that is none, a directory for a URL that
    names no socket: each would otherwise run on something the caller did not mean."""
    done, calls = _run_local(tmp_path, script, **environment)

    assert done.returncode == 2, done.stderr or done.stdout
    assert names in done.stderr
    assert calls == [], "the script called docker before it refused"


def test_two_urls_at_once_are_refused(tmp_path):
    """`TEST_DATABASE_URL` is the whole URL, the switch derives one: not both."""
    done, calls = _run(
        tmp_path,
        "test-local.sh",
        SNEL="1",
        EXISTING_DB_URL=HOST_URL,
        TEST_DATABASE_URL="postgresql+psycopg2://u:p@dbhost:5432/raaktest_proef",
    )

    assert done.returncode == 2, done.stderr or done.stdout
    assert calls == []


def test_a_refusal_does_not_print_the_url(tmp_path):
    """The URL carries a password; the refusal names the variable, not its value."""
    done, _calls = _run(
        tmp_path, "e2e-local.sh", EXISTING_DB_URL="secret-in-here", E2E_DB_NAME="raake2e_proef"
    )

    assert done.returncode == 2
    assert "secret-in-here" not in done.stderr + done.stdout


# ── The user of the helper container (#1893) ─────────────────────────────────


@pytest.mark.parametrize("environment", [{}, {"EXISTING_DB_URL": SOCKET_URL}])
def test_the_named_user_reaches_the_helper_container(tmp_path, environment):
    """With or without the switch of #1891: the two are set apart."""
    done, calls = _run_local(tmp_path, "test-local.sh", HELPER_CONTAINER_USER="root", **environment)

    assert done.returncode == 0, done.stderr
    created = [call for call in calls if call.startswith("run ")]
    assert len(created) == 1, f"expected one docker run, found {len(created)}"
    assert " -u root " in created[0], created[0]
    assert created[0].index(" -u root ") < created[0].index(" raaktest-backend:"), (
        "the user stands after the image, where docker reads it as the command"
    )


def test_no_exec_names_another_user_than_root(tmp_path):
    """A `docker exec` runs as the user the container was created with. One that
    named another would install or write as someone else than the run reads as —
    and in a rootless Docker it would not start. Root is the exception (#1894):
    the one user that exists in an ordinary Docker and in a rootless one, and
    the one that may install."""
    done, calls = _run_local(tmp_path, "test-local.sh", HELPER_CONTAINER_USER="root")

    assert done.returncode == 0, done.stderr
    executed = [call for call in calls if call.startswith("exec ")]
    assert len(executed) >= 2, "the script reached its exec calls not at all"
    for call in executed:
        assert " -u " not in call.replace(" -u root ", " ") and "--user" not in call, call


@pytest.mark.parametrize("environment", [{}, {"HELPER_CONTAINER_USER": "root"}])
def test_git_and_psql_are_installed_as_root_from_debians_own_archive(tmp_path, environment):
    """One call, only when one of the two is missing, and no other source than
    the archive the image already trusts."""
    done, calls = _run_local(tmp_path, "test-local.sh", **environment)

    assert done.returncode == 0, done.stderr
    installs = [call for call in calls if "apt-get install" in call]
    assert len(installs) == 1, f"expected one install call, found {len(installs)}"
    install = installs[0]
    assert install.startswith("exec -u root raaktest-checkout "), install
    assert "command -v git >/dev/null && command -v psql >/dev/null || {" in install
    assert install.rstrip().endswith("git postgresql-client >/dev/null; }"), install
    for other_source in ("sources.list", "apt-key", "curl", "wget", "http"):
        assert other_source not in install, install


def test_the_browser_helper_container_keeps_its_own_user(tmp_path):
    """`e2e-local.sh` creates its container as root, always; the variable is
    `test-local.sh`'s and must not land there a second time."""
    done, calls = _run_local(tmp_path, "e2e-local.sh", HELPER_CONTAINER_USER="someone")

    assert done.returncode == 0, done.stderr
    created = [call for call in calls if call.startswith("run ")]
    assert len(created) == 1
    assert created[0].count(" -u ") == 1 and " -u root " in created[0], created[0]


# ── tests._local_db: what makes the database when no container can be asked ──


@pytest.mark.parametrize("script", LOCAL_SCRIPTS)
def test_the_module_admits_the_name_each_script_derives(script):
    """The module keeps the three prefixes itself; this ties them to the scripts."""
    assert is_a_local_run_database(LOCAL_SCRIPTS[script][3])


@pytest.mark.parametrize("action", [create, recreate])
@pytest.mark.parametrize("name", ["raakmillegem", "postgres", "raaktestament"])
def test_another_name_is_refused_by_the_module_too(action, name):
    """Before it connects: the URL here leads nowhere, and is never used."""
    with pytest.raises(SystemExit, match="REFUSED"):
        action("postgresql+psycopg2://u:p@nowhere.invalid:1/postgres", name)


def _exists(admin_url: str, name: str) -> bool:
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            return (
                conn.exec_driver_sql(
                    "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
                ).first()
                is not None
            )
    finally:
        engine.dispose()


def _tables(admin_url: str, name: str) -> int:
    engine = create_engine(make_url(admin_url).set(database=name))
    try:
        with engine.connect() as conn:
            return conn.exec_driver_sql(
                "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
            ).scalar_one()
    finally:
        engine.dispose()


def test_create_leaves_what_exists_and_recreate_empties_it():
    """Against the suite's own server: `create` twice keeps the table, `recreate`
    drops it. A name of its own per worker, dropped again at the end."""
    from tests.conftest import BASE_DATABASE_URL

    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    name = f"raaktest_localdb_probe_{worker}"
    drop = create_engine(BASE_DATABASE_URL, isolation_level="AUTOCOMMIT")
    try:
        recreate(BASE_DATABASE_URL, name)
        assert _exists(BASE_DATABASE_URL, name)

        own = create_engine(make_url(BASE_DATABASE_URL).set(database=name))
        with own.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE kept (id integer)")
        own.dispose()

        create(BASE_DATABASE_URL, name)
        assert _tables(BASE_DATABASE_URL, name) == 1, "create touched a database that existed"

        recreate(BASE_DATABASE_URL, name)
        assert _tables(BASE_DATABASE_URL, name) == 0, "recreate left the old content"
    finally:
        with drop.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        drop.dispose()
    assert not _exists(BASE_DATABASE_URL, name)
