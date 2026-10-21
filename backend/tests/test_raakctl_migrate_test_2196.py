"""#2196 — `raakctl migrate-test <env> <tag> [dump]`: a tag's migrations on a throwaway
copy of an environment's dump, before the deploy does it for real.

The PROD deploy of v2.17.0 failed in migration 212 on data no other environment held.
`restore-test` proves a dump restores; it does not run the next release's migrations.

What must hold, and each part must be able to fail:

1. *A tag is required*, and it must look like a tag: without one, or with a path or an
   option, the verb refuses BEFORE anything runs.
2. *Only a dump inside that environment's `backups/`*, as `restore-test` takes it.
3. *The throwaway database is dropped on every exit* — a rehearsal that ends in a
   failed migration, one that cannot unpack the tag, and one that succeeds.
4. *The migration runs in a one-off container* (`docker run … alembic upgrade head`),
   not through the app: no `startup.sh`, no uvicorn, no seeding.
5. *The summary* is the fixed block the master CLI copies into the release tracker:
   tag, dump, upgrades, before and after counts, `result=ok|failed`; and a failed run
   ends non-zero and shows the exception.
6. *No secret in the report*: the connection string is masked.

`scripts/migrate-test.sh` really runs here, against a fake `docker` and a fake `git`
that record what they were asked and answer in the shape of the real ones. The real
thing was run on a sandbox environment: v2.17.0 against a dump holding a sent letter
with prose failed in migration 212 with `NoTenantContext`, and against a dump without
a letter it reached the head; the throwaway database and image were gone after both.

Broken on purpose, one additive violation at a time, each test seen failing on its own
assertion:

| Violation | Failed |
|---|---|
| a `tag` default (`tag="${1:-v0}"`) added before the refusing check | "a tag is required" |
| `trap cleanup EXIT` removed from the script | "dropped on every exit" (all three) |
| `alembic upgrade head` replaced by `./startup.sh` in the `docker run` | "runs alembic only" |
| the `sed` that masks the connection string removed | "no secret in the report" |
"""

import gzip
import os
import subprocess
import time
from pathlib import Path

import pytest

RAAKCTL = Path(__file__).resolve().parents[2] / "raakctl"

pytestmark = pytest.mark.ui_agnostisch

# A valid, empty gzip file: the fake psql reads and ignores it.
EMPTY_GZIP = gzip.compress(b"")

COUNTS = """\
 t                        | n
--------------------------+---------------------
 alembic_version          | {revision}
 mdm.members              | 412
 mdm.persons              | 977
 activities.registrations | 1530
 payment.payment_records  | 1204
(5 rows)
"""

# The shape of what the real tools print. `docker compose exec` is the db container
# (psql); `docker run` is the one-off container of the tag's image.
FAKE_DOCKER = """#!/bin/sh
echo "docker $*" >> "{trace}"
case "$1" in
  compose)
    case "$*" in
      *" ps -q db"*) echo "dbcontainer" ;;
      *"echo DATABASE_URL"*) echo "DATABASE_URL=postgresql://user:secretpw@db:5432/migrate_test" ;;
      *"alembic_version"*)
        if [ -f "{state}" ]; then rev=head_revision; else rev=old_revision; fi
        cat <<T
{counts}
T
        ;;
      *) cat > /dev/null ;;
    esac ;;
  inspect) echo "env_default" ;;
  build) echo "sha256:abc" ;;
  rmi) ;;
  run)
    case "$*" in
      *"alembic heads"*) echo "head_revision (head)" ;;
      *"alembic upgrade head"*)
        echo "INFO  [alembic.runtime.migration] Running upgrade old_revision -> mid_revision, first"
        echo "INFO  [alembic.runtime.migration] Running upgrade mid_revision -> head_revision, second"
        if [ "{migration_rc}" != "0" ]; then
          echo "Traceback (most recent call last):"
          echo "  File \\"/app/alembic/versions/212_x.py\\", line 244, in upgrade"
          echo "sqlalchemy.exc.OperationalError: could not connect to postgresql://user:secretpw@db:5432/migrate_test"
          echo "app.kernel.clock.NoTenantContext: the clock was asked for a day outside any tenant"
          exit {migration_rc}
        fi
        touch "{state}" ;;
    esac ;;
esac
exit 0
"""

FAKE_GIT = """#!/bin/sh
echo "git $*" >> "{trace}"
case "$1" in
  rev-parse) [ "$4" = "refs/tags/{known_tag}^{{commit}}" ] || [ "$3" = "refs/tags/{known_tag}^{{commit}}" ] || exit 1 ;;
  archive) tar -cf - -T /dev/null ;;
  fetch) ;;
esac
exit 0
"""


def _environment(tmp_path, migration_rc=0, known_tag="v9.9.9"):
    trace = tmp_path / "invocations.txt"
    state = tmp_path / "migrated"
    env = dict(os.environ)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    for name, body in (
        (
            "docker",
            FAKE_DOCKER.format(
                trace=trace,
                state=state,
                migration_rc=migration_rc,
                counts=COUNTS.format(revision="$rev"),
            ),
        ),
        ("git", FAKE_GIT.format(trace=trace, known_tag=known_tag)),
    ):
        f = fakebin / name
        f.write_text(body)
        f.chmod(0o755)
    env["PATH"] = f"{fakebin}:{env['PATH']}"

    for name in ("hdev", "uat", "prod"):
        checkout = tmp_path / name
        (checkout / ".git").mkdir(parents=True)
        (checkout / "backups").mkdir()
        (checkout / f"docker-compose.{name}.yml").write_text("services: {}\n")
        (checkout / f".env.{name}").write_text("\n")
        env[f"DEPLOY_{name.upper()}_DIR"] = str(checkout)
    # The script raakctl runs is the real one, next to the real raakctl.
    return env, trace


def _run(tmp_path, *args, migration_rc=0, dumps=(), stdin="", known_tag="v9.9.9"):
    env, trace = _environment(tmp_path, migration_rc, known_tag)
    for environment, name, mtime in dumps:
        f = tmp_path / environment / "backups" / name
        f.write_bytes(EMPTY_GZIP)
        os.utime(f, (mtime, mtime))
    done = subprocess.run(
        ["bash", str(RAAKCTL), *args],
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return done, (trace.read_text() if trace.exists() else "")


DUMP = [("prod", "dump-1.sql.gz", 1_000_000)]


def _statements(invocations, text):
    return [line for line in invocations.splitlines() if text in line]


# ── The tag is required ───────────────────────────────────────────────────────


def test_a_tag_is_required(tmp_path):
    done, invocations = _run(tmp_path, "migrate-test", "prod", dumps=DUMP)

    assert done.returncode != 0
    assert "needs the tag" in done.stderr, done.stderr
    assert invocations == "", f"something ran anyway:\n{invocations}"


@pytest.mark.parametrize("tag", ["--list", "../v1", "a/b", "v1 2"])
def test_something_that_is_not_a_tag_is_refused(tag, tmp_path):
    done, invocations = _run(tmp_path, "migrate-test", "prod", tag, dumps=DUMP)

    assert done.returncode != 0
    assert "not a release tag" in done.stderr, done.stderr
    assert invocations == ""


def test_an_unknown_environment_is_refused(tmp_path):
    done, invocations = _run(tmp_path, "migrate-test", "caddy", "v9.9.9")

    assert done.returncode != 0
    assert "works on hdev, uat or prod" in done.stderr
    assert invocations == ""


@pytest.mark.parametrize("dump", ["../prod/backups/x.sql.gz", "/etc/passwd", "sub/x.sql.gz"])
def test_a_dump_outside_backups_is_refused(dump, tmp_path):
    done, invocations = _run(tmp_path, "migrate-test", "prod", "v9.9.9", dump, dumps=DUMP)

    assert done.returncode != 0
    assert "not a path" in done.stderr, done.stderr
    assert invocations == ""


# ── A rehearsal that succeeds ─────────────────────────────────────────────────


def test_a_rehearsal_reaches_the_head_and_reports_before_and_after(tmp_path):
    done, invocations = _run(tmp_path, "migrate-test", "prod", "v9.9.9", dumps=DUMP)

    assert done.returncode == 0, done.stdout + done.stderr
    out = done.stdout
    assert "== migrate-test summary ==" in out
    for line in (
        "environment=prod",
        "tag=v9.9.9",
        "dump=dump-1.sql.gz",
        "upgrades=2",
        "head=head_revision",
        "before.alembic_version=old_revision",
        "before.mdm.members=412",
        "after.alembic_version=head_revision",
        "after.payment.payment_records=1204",
        "result=ok",
    ):
        assert line in out.splitlines(), f"{line!r} missing from:\n{out}"


def test_the_migration_runs_alembic_only_in_a_one_off_container(tmp_path):
    done, invocations = _run(tmp_path, "migrate-test", "prod", "v9.9.9", dumps=DUMP)

    assert done.returncode == 0, done.stdout + done.stderr
    runs = _statements(invocations, "docker run")
    upgrade = [r for r in runs if "alembic upgrade head" in r]
    assert len(upgrade) == 1, invocations
    assert "--rm" in upgrade[0] and "--network env_default" in upgrade[0]
    # Nothing that starts the app or seeds: only alembic runs in a container.
    assert not _statements(invocations, "startup.sh")
    assert not _statements(invocations, "uvicorn")
    # The tag's code comes from the tag, not from the checkout of the environment.
    assert any("git archive refs/tags/v9.9.9" in line for line in invocations.splitlines())


# ── The throwaway database is dropped on every exit ───────────────────────────


def _last_drop_is_after_everything(invocations):
    lines = invocations.splitlines()
    drops = [i for i, line in enumerate(lines) if "DROP DATABASE IF EXISTS migrate_test" in line]
    return bool(drops) and drops[-1] == max(
        i for i, line in enumerate(lines) if line.startswith(("docker compose", "docker rmi"))
    ) - (1 if lines[-1].startswith("docker rmi") else 0)


def test_the_throwaway_database_is_dropped_after_a_success(tmp_path):
    done, invocations = _run(tmp_path, "migrate-test", "prod", "v9.9.9", dumps=DUMP)

    assert done.returncode == 0
    assert _statements(invocations, "DROP DATABASE IF EXISTS migrate_test")
    assert _last_drop_is_after_everything(invocations), invocations


def test_the_throwaway_database_is_dropped_after_a_failed_migration(tmp_path):
    done, invocations = _run(tmp_path, "migrate-test", "prod", "v9.9.9", migration_rc=1, dumps=DUMP)

    assert done.returncode != 0
    assert len(_statements(invocations, "DROP DATABASE IF EXISTS migrate_test")) >= 2, (
        "the trap did not drop it after the failure:\n" + invocations
    )
    assert _last_drop_is_after_everything(invocations), invocations


def test_the_throwaway_database_is_dropped_when_the_tag_cannot_be_found(tmp_path):
    done, invocations = _run(tmp_path, "migrate-test", "prod", "v1.0.0", dumps=DUMP)

    assert done.returncode != 0
    assert "Unknown tag" in done.stdout + done.stderr
    # Nothing was created before the tag was known, and the trap still ran.
    assert not _statements(invocations, "CREATE DATABASE migrate_test")
    assert _statements(invocations, "DROP DATABASE IF EXISTS migrate_test")


# ── A failed rehearsal says so and shows why ──────────────────────────────────


def test_a_failed_migration_shows_the_exception_and_ends_failed(tmp_path):
    done, invocations = _run(tmp_path, "migrate-test", "prod", "v9.9.9", migration_rc=1, dumps=DUMP)

    out = done.stdout
    assert done.returncode != 0
    assert "NoTenantContext" in out, out
    assert "== First error ==" in out
    assert "result=failed" in out.splitlines()
    # The counts before are reported even though there is no 'after'.
    assert "before.mdm.members=412" in out.splitlines()
    assert not any(line.startswith("after.") for line in out.splitlines())


def test_no_secret_reaches_the_report(tmp_path):
    done, invocations = _run(tmp_path, "migrate-test", "prod", "v9.9.9", migration_rc=1, dumps=DUMP)

    assert "secretpw" not in done.stdout + done.stderr, done.stdout
    assert "postgresql://***@" in done.stdout


# ── The menu ──────────────────────────────────────────────────────────────────


def test_the_menu_asks_the_environment_then_the_tag(tmp_path):
    """`select` reads whatever is in the pipe when it reads, so the answers are given in
    two moments, as a person types them: the environment first, the tag after."""
    env, trace = _environment(tmp_path)
    (tmp_path / "prod" / "backups" / "dump-1.sql.gz").write_bytes(EMPTY_GZIP)
    menu = subprocess.Popen(
        ["bash", str(RAAKCTL)],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    menu.stdin.write("m\n3\n")
    menu.stdin.flush()
    time.sleep(1)
    out, err = menu.communicate("v9.9.9\nq\n", timeout=60)

    assert menu.returncode == 0, err + "\n--stdout--\n" + out[-1500:]
    assert "m) migration rehearsal" in out
    assert "environment=prod" in out.splitlines()
    assert "tag=v9.9.9" in out.splitlines()
