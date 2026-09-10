"""#818 — database questions per environment, read-only by default.

During the v2.0.0/v2.1.0 rollout this was the thing raakctl had no verb for most often:
roughly ten hand-written invocations naming a compose file, an env file, a container and
two levels of shell quoting. A forgotten `-T` gives a puzzling error; a wrong `<env>`
runs your query against the wrong database, and THAT is the failure with the worst
ending.

**Two properties are under test here, and both must be able to fail.**

1. *An unknown environment is refused BEFORE anything is executed.* Refusing after the
   connection is made is not refusing.
2. *Read-only is the default, on EVERY environment.* The brake is the server's own
   `default_transaction_read_only`, not a look at your SQL: a regex over a query is
   guesswork, Postgres refusing the write is a fact. Writing takes `--write`, and on
   PROD `--confirm` on top of it.

The script really runs here, with a fake `docker` on the PATH that records what it would
execute. That record IS the assertion.

Broken on purpose to check that these tests can go red: removed the `PGOPTIONS` line
from `cmd_psql` → the read-only tests fall over; removed the `case` check on the
environment → the refusal test falls over.
"""
import os
import subprocess
from pathlib import Path

import pytest

RAAKCTL = Path(__file__).resolve().parents[2] / "raakctl"

pytestmark = pytest.mark.ui_agnostisch

READ_ONLY = "default_transaction_read_only=on"


def _environment(tmp_path):
    """Fake checkouts for all three environments, plus a fake `docker`."""
    trace = tmp_path / "invocations.txt"
    env = dict(os.environ)
    for name in ("hdev", "uat", "prod"):
        checkout = tmp_path / name
        (checkout / ".git").mkdir(parents=True)
        (checkout / f"docker-compose.{name}.yml").write_text("services: {}\n")
        (checkout / f".env.{name}").write_text("\n")
        env[f"DEPLOY_{name.upper()}_DIR"] = str(checkout)

    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    # `ps -q db` must return something, otherwise the verb rightly refuses with "the db
    # container is not running" and we would be testing that refusal instead of the rest.
    fake = fakebin / "docker"
    fake.write_text(
        f'#!/bin/sh\necho "docker $@" >> "{trace}"\n'
        'case "$*" in *"ps -q db"*) echo fakecontainer ;; esac\nexit 0\n')
    fake.chmod(0o755)

    env["PATH"] = f"{fakebin}:{env['PATH']}"
    return env, trace


def _run(tmp_path, *args, stdin=""):
    env, trace = _environment(tmp_path)
    done = subprocess.run(["bash", str(RAAKCTL), *args], env=env, input=stdin,
                          capture_output=True, text=True, timeout=60)
    return done, (trace.read_text() if trace.exists() else "")


@pytest.mark.parametrize("environment", ["hdev", "uat", "prod"])
def test_reading_is_read_only_by_default(environment, tmp_path):
    """On EVERY environment, hdev included: the brake must not be a prod exception, or
    you never practise in the shape you eventually work in."""
    done, invocations = _run(tmp_path, "psql", environment, "-c", "SELECT 1")

    assert done.returncode == 0, done.stderr
    assert READ_ONLY in invocations, (
        f"the session does not run read-only:\n{invocations}")
    assert f"docker-compose.{environment}.yml" in invocations, "wrong environment"
    assert "SELECT 1" in invocations


def test_write_releases_the_brake(tmp_path):
    """The counterproof: without it a test that sees "read-only" would also be green if
    the verb could never do anything else."""
    done, invocations = _run(tmp_path, "psql", "hdev", "--write", "-c", "UPDATE x SET y=1")

    assert done.returncode == 0, done.stderr
    assert READ_ONLY not in invocations
    assert "WRITEABLE" in done.stderr, "you cannot see that you are in write mode"


def test_writing_on_prod_needs_a_confirmation(tmp_path):
    done, invocations = _run(tmp_path, "psql", "prod", "--write", "-c", "UPDATE x SET y=1")

    assert done.returncode != 0, "PROD allowed a write session without confirmation"
    assert "--confirm" in done.stderr
    assert "psql" not in invocations, "something ran before the refusal"


def test_writing_on_prod_is_allowed_with_confirm(tmp_path):
    """Otherwise the previous test is indistinguishable from "prod cannot do anything at
    all"."""
    done, invocations = _run(tmp_path, "psql", "prod", "--write", "--confirm",
                             "-c", "UPDATE x SET y=1")

    assert done.returncode == 0, done.stderr
    assert READ_ONLY not in invocations
    assert "docker-compose.prod.yml" in invocations


def test_an_unknown_environment_is_refused_before_anything_happens(tmp_path):
    """The failure with the worst ending is a query against the wrong database."""
    done, invocations = _run(tmp_path, "psql", "produktie", "-c", "SELECT 1")

    assert done.returncode != 0
    assert "produktie" in done.stderr
    assert invocations == "", (
        f"something was already executed before the refusal:\n{invocations}")


def test_another_database_can_be_chosen(tmp_path):
    """`umami_<env>` was needed repeatedly during the same rollout.

    On uat and not on hdev: since #820 no Umami runs there and `umami_hdev` no longer
    exists — an example pointing at a vanished database sends the next reader up the
    garden path.
    """
    _done, invocations = _run(tmp_path, "psql", "uat", "--db", "umami_uat",
                              "-c", "SELECT 1")

    assert "RAAKCTL_DB=umami_uat" in invocations


def test_an_sql_file_goes_in_over_stdin(tmp_path):
    """psql runs inside the container and cannot see your file; `-f` must therefore be
    translated into stdin rather than passed along."""
    query = tmp_path / "question.sql"
    query.write_text("SELECT count(*) FROM members;\n")

    done, invocations = _run(tmp_path, "psql", "uat", "-f", str(query))

    assert done.returncode == 0, done.stderr
    assert "exec -T" in invocations, "without -T a non-interactive session hangs"
    assert str(query) not in invocations, (
        "the path was handed to psql; inside the container it does not exist")


def test_a_missing_sql_file_is_reported_immediately(tmp_path):
    done, invocations = _run(tmp_path, "psql", "hdev", "-f", str(tmp_path / "gone.sql"))

    assert done.returncode != 0
    assert "no such SQL file" in done.stderr
    assert invocations == ""


def test_the_verb_appears_in_the_help_text(tmp_path):
    """#678: a test that finds nothing and is green anyway guards nothing."""
    env, _trace = _environment(tmp_path)
    done = subprocess.run(["bash", str(RAAKCTL), "help"], env=env,
                          capture_output=True, text=True, timeout=60)
    help_text = done.stdout + done.stderr

    assert "raakctl psql" in help_text, "the verb is not in the help"
    assert "READ-ONLY" in help_text, (
        "the help does not say that reading is the default — then you expect a write "
        "session")
