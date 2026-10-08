"""#1232 — the restore exercise (`scripts/restore-test.sh`) works, and fails loudly.

The exercise is meant to run once per release (§19.1), and since the schema
split it could not have succeeded: its counts named `members`, `persons`, …
without a schema, and those tables live in `mdm`, `activities` and `payment`
now. And its restore ran without `ON_ERROR_STOP`, so a dump that broke halfway
produced errors but no exit code — a half restore could pass as a success.

**These tests run the real script against a real PostgreSQL.** Only one thing
is faked: the redirection. The script calls
`docker compose -f … --env-file … exec -T db sh -c '<command>'`; a fake
`docker` on the PATH runs `sh -c '<command>'` locally instead, with
`POSTGRES_USER`, `POSTGRES_DB` and the libpq variables pointing at the test
database server (in CI the Postgres service container). The `psql` that then
runs is the real one, so a broken dump is refused by a real
`psql -v ON_ERROR_STOP=1` — a fake psql would test the fake, not the script.

The dumps are small SQL files written here, in the shape `pg_dump` produces:
the schemas, the four counted tables and `alembic_version`.

**These tests need a real `psql` client.** CI's runner has one; the
`raaktest-runner` container does not, so there they fail on the assertion that
says so.

Broken on purpose to check that these tests can go red:
- `-v ON_ERROR_STOP=1` removed from the restore line → the broken-dump test
  falls over: psql skips the failing statement, the counts still run, and the
  script reports success on a half-restored database;
- `mdm.persons` written back as `persons` in the counts → the good-dump test
  falls over on `relation "persons" does not exist`;
- the `trap` removed → both tests fall over on the throwaway database that
  stays behind: the script drops it through the trap only, on success too.
"""

import gzip
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pytest

# CR-29: the script under test restores into ONE scratch database with a fixed
# name (`restore_test`) on the server, whatever worker calls it. Two of these
# tests in two processes would drop it under each other, so they share a worker.
pytestmark = [pytest.mark.ui_agnostisch, pytest.mark.xdist_group("restore_test")]

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "restore-test.sh"
PSQL = shutil.which("psql")

GOOD_DUMP = """\
CREATE SCHEMA mdm;
CREATE SCHEMA activities;
CREATE SCHEMA payment;
CREATE TABLE public.alembic_version (version_num varchar(64) PRIMARY KEY);
INSERT INTO public.alembic_version VALUES ('163_2026_09_26_144116');
CREATE TABLE mdm.members (id integer PRIMARY KEY);
INSERT INTO mdm.members VALUES (1), (2), (3);
CREATE TABLE mdm.persons (id integer PRIMARY KEY, first_name text);
INSERT INTO mdm.persons VALUES (1, 'a'), (2, 'b'), (3, 'c'), (4, 'd'), (5, 'e');
CREATE TABLE activities.registrations (id integer PRIMARY KEY);
INSERT INTO activities.registrations VALUES (1), (2);
CREATE TABLE payment.payment_records (id integer PRIMARY KEY);
INSERT INTO payment.payment_records VALUES (1), (2), (3), (4);
"""

#: The same dump with one statement that fails halfway: a value that does not
#: fit its column. Everything after it still parses, so without ON_ERROR_STOP
#: psql carries on and the database looks restored — minus the persons.
BROKEN_DUMP = GOOD_DUMP.replace(
    "INSERT INTO mdm.persons VALUES (1, 'a'), (2, 'b'), (3, 'c'), (4, 'd'), (5, 'e');",
    "INSERT INTO mdm.persons VALUES ('niet-een-getal', 'a');",
)


def _server_env() -> dict[str, str]:
    url = urlparse(os.environ["TEST_DATABASE_URL"].replace("+psycopg2", ""))
    return {
        "PGHOST": url.hostname or "localhost",
        "PGPORT": str(url.port or 5432),
        "PGPASSWORD": url.password or "",
        "POSTGRES_USER": url.username or "",
        "POSTGRES_DB": url.path.lstrip("/"),
    }


def _run(tmp_path: Path, dump_sql: str) -> subprocess.CompletedProcess:
    assert PSQL, "these tests need a real psql client (CI's runner has one)"
    work = tmp_path / "checkout"
    (work / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, work / "scripts" / "restore-test.sh")
    backups = work / "backups"
    backups.mkdir()
    with gzip.open(backups / "pre-deploy-hdev-20260927-120000.sql.gz", "wt") as fh:
        fh.write(dump_sql)

    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    # The redirection and nothing else: run the command the script hands to
    # `sh -c` inside the container, here, with stdin passed through.
    (fakebin / "docker").write_text('#!/bin/sh\nfor last; do :; done\nexec sh -c "$last"\n')
    (fakebin / "docker").chmod(0o755)

    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", **_server_env())
    return subprocess.run(
        ["bash", "scripts/restore-test.sh", "hdev"],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _restore_db_exists() -> bool:
    env = dict(os.environ, **_server_env())
    out = subprocess.run(
        [
            PSQL,
            "-tA",
            "-U",
            env["POSTGRES_USER"],
            "-d",
            env["POSTGRES_DB"],
            "-c",
            "SELECT count(*) FROM pg_database WHERE datname = 'restore_test'",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip() != "0"


def test_a_good_dump_is_restored_and_counted_by_schema(tmp_path):
    done = _run(tmp_path, GOOD_DUMP)

    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    out = done.stdout
    assert "163_2026_09_26_144116" in out, "the exercise shows the dump's revision"
    for table, count in (
        ("mdm.members", 3),
        ("mdm.persons", 5),
        ("activities.registrations", 2),
        ("payment.payment_records", 4),
    ):
        assert any(
            table in line and line.rstrip().endswith(str(count)) for line in out.splitlines()
        ), f"{table} {count} not in:\n{out}"
    assert "geslaagd" in out
    assert not _restore_db_exists(), "the throwaway database is dropped afterwards"


def test_a_dump_that_breaks_halfway_fails_the_exercise_and_cleans_up(tmp_path):
    done = _run(tmp_path, BROKEN_DUMP)

    assert done.returncode != 0, "a half restore must not pass"
    assert "geslaagd" not in done.stdout
    assert "niet-een-getal" in done.stderr or "invalid input" in done.stderr, done.stderr[-2000:]
    assert not _restore_db_exists(), "the trap drops the throwaway database on failure too"
