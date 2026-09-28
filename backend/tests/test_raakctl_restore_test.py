"""#1288 — the restore exercise as a raakctl verb, so it runs before a tag without a
shell on the host.

`scripts/restore-test.sh` (#1232) restores a dump into a throwaway database and counts
a few tables. Before this verb, running it meant a shell on the server, a `cd` into the
right checkout and a file name typed by hand. The verb takes over three things, and each
must be able to fail:

1. *Only a dump inside that environment's `backups/`.* The exercise restores whatever it
   is given; a path with a directory part, `..` or a leading `/` is refused BEFORE the
   script runs.
2. *`--list` shows the newest dump first*, with time and size — that is the one you want.
3. *The script of THAT environment's checkout runs, from that checkout.* Every
   environment is a checkout of the same repository, so the UAT checkout also has a
   `restore-test.sh`; running the wrong one restores the wrong environment's dumps.

And it ends in a fixed summary the master CLI copies into the release tracker: dump,
duration, the counts, `alembic_version` of the dump, `result=ok|failed`.

No `--confirm`, not even on PROD: the exercise writes only into a throwaway database and
drops it. A test holds that line.

The script really runs here: fake checkouts, each with its own fake `restore-test.sh`
that records where it ran and with what, and prints the real script's output shape.

Broken on purpose (28 September 2026), one additive violation at a time, each test
seen failing on its own assertion:

| Violation | Failed |
|---|---|
| `*/*\\|*..*) ;;` added before the refusing `case` branch (paths let through) | the three "outside backups/" tests — the script ran |
| `ls -1t` given `-r` (oldest first) | "--list shows the newest first" |
| `d="$(checkout hdev)"` added after the checkout is resolved | "that environment's checkout" (uat, prod), the newest-itself, prod, summary, menu and --list tests |
| `rc=0` added after the exit code is taken | "a failed exercise says failed" |
| a `--confirm` demand for prod added | "prod needs no confirmation", "that environment's checkout" (prod), --list |
"""

import os
import subprocess
from pathlib import Path

import pytest

RAAKCTL = Path(__file__).resolve().parents[2] / "raakctl"

pytestmark = pytest.mark.ui_agnostisch

# The shape of the real script's output: its header line, then psql's table.
FAKE_SCRIPT = """#!/bin/sh
echo "cwd=$(pwd) args=$* backup_dir=$BACKUP_DIR" >> "{trace}"
echo "== Restore-oefening met: ${{2:-$BACKUP_DIR/newest.sql.gz}} =="
echo "== Sanity-tellingen =="
echo "            t             |            n"
echo "--------------------------+---------------------"
echo " alembic_version          | 2026_09_27_101500"
echo " mdm.members              | 412"
echo " mdm.persons              | 977"
echo " activities.registrations | 1530"
echo " payment.payment_records  | 1204"
echo "(5 rows)"
exit {code}
"""


def _environment(tmp_path, code=0):
    """Fake checkouts for all three environments, each with a `backups/` dir and its
    own fake `scripts/restore-test.sh`, plus a fake `docker`."""
    trace = tmp_path / "invocations.txt"
    env = dict(os.environ)
    for name in ("hdev", "uat", "prod"):
        checkout = tmp_path / name
        (checkout / ".git").mkdir(parents=True)
        (checkout / "backups").mkdir()
        (checkout / "scripts").mkdir()
        (checkout / f"docker-compose.{name}.yml").write_text("services: {}\n")
        (checkout / f".env.{name}").write_text("\n")
        script = checkout / "scripts" / "restore-test.sh"
        script.write_text(FAKE_SCRIPT.format(trace=trace, code=code))
        script.chmod(0o755)
        env[f"DEPLOY_{name.upper()}_DIR"] = str(checkout)

    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    fake = fakebin / "docker"
    fake.write_text(f'#!/bin/sh\necho "docker $@" >> "{trace}"\nexit 0\n')
    fake.chmod(0o755)
    env["PATH"] = f"{fakebin}:{env['PATH']}"
    return env, trace


def _run(tmp_path, *args, code=0, dumps=(), stdin=""):
    env, trace = _environment(tmp_path, code)
    for environment, name, mtime in dumps:
        f = tmp_path / environment / "backups" / name
        f.write_bytes(b"x" * 2048)
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


# ── Only dumps inside backups/ ────────────────────────────────────────────────


@pytest.mark.parametrize("dump", ["../prod/backups/x.sql.gz", "/etc/passwd", "sub/x.sql.gz"])
def test_a_dump_outside_backups_is_refused_before_the_script_runs(dump, tmp_path):
    done, invocations = _run(tmp_path, "restore-test", "uat", dump)

    assert done.returncode != 0
    assert "not a path" in done.stderr, done.stderr
    assert "cwd=" not in invocations, f"the script ran anyway:\n{invocations}"


def test_a_dump_that_does_not_exist_is_refused(tmp_path):
    done, invocations = _run(tmp_path, "restore-test", "uat", "nope.sql.gz")

    assert done.returncode != 0
    assert "no dump 'nope.sql.gz'" in done.stderr, done.stderr
    assert "cwd=" not in invocations


def test_an_unknown_environment_is_refused(tmp_path):
    done, invocations = _run(tmp_path, "restore-test", "dev")

    assert done.returncode != 0
    assert "hdev, uat or prod" in done.stderr, done.stderr
    assert "cwd=" not in invocations


# ── --list ────────────────────────────────────────────────────────────────────


def test_list_shows_the_newest_first_with_time_and_size(tmp_path):
    """The names sort the other way round from the times, so an alphabetical list
    cannot pass for a newest-first one."""
    done, invocations = _run(
        tmp_path,
        "restore-test",
        "prod",
        "--list",
        dumps=[
            ("prod", "a-newest.sql.gz", 1_790_000_000),
            ("prod", "b-middle.sql.gz", 1_780_000_000),
            ("prod", "c-oldest.sql.gz", 1_770_000_000),
            ("uat", "z-other-environment.sql.gz", 1_800_000_000),
        ],
    )

    assert done.returncode == 0, done.stderr
    lines = done.stdout.strip().splitlines()
    names = [line.split()[-1] for line in lines]
    assert names == ["a-newest.sql.gz", "b-middle.sql.gz", "c-oldest.sql.gz"], done.stdout
    # time (YYYY-MM-DD HH:MM) and size on every line
    for line in lines:
        date, clock, size, _name = line.split()
        assert len(date) == 10 and date[4] == "-" and clock[2] == ":", line
        assert size.endswith("K"), line
    assert "cwd=" not in invocations, "--list ran the exercise"


def test_list_says_so_when_there_are_no_dumps(tmp_path):
    done, _ = _run(tmp_path, "restore-test", "hdev", "--list")

    assert done.returncode == 0, done.stderr
    assert "no dumps in backups/ of hdev" in done.stdout


# ── The script of that environment's checkout ─────────────────────────────────


@pytest.mark.parametrize("environment", ["hdev", "uat", "prod"])
def test_the_script_of_that_environments_checkout_runs(environment, tmp_path):
    done, invocations = _run(
        tmp_path,
        "restore-test",
        environment,
        "chosen.sql.gz",
        dumps=[(environment, "chosen.sql.gz", 1_790_000_000)],
    )

    assert done.returncode == 0, done.stderr
    checkout = tmp_path / environment
    backups = checkout / "backups"
    assert invocations.strip() == (
        f"cwd={checkout} args={environment} {backups / 'chosen.sql.gz'} backup_dir={backups}"
    ), invocations


def test_without_a_dump_the_script_picks_the_newest_itself(tmp_path):
    done, invocations = _run(tmp_path, "restore-test", "uat")

    assert done.returncode == 0, done.stderr
    assert f"args=uat backup_dir={tmp_path / 'uat' / 'backups'}" in invocations, invocations


def test_prod_needs_no_confirmation(tmp_path):
    """Safe on a throwaway database — a confirmation that protects nothing teaches
    people to type it without reading."""
    done, invocations = _run(tmp_path, "restore-test", "prod")

    assert done.returncode == 0, done.stderr
    assert f"cwd={tmp_path / 'prod'}" in invocations


# ── The fixed summary ─────────────────────────────────────────────────────────


def _summary(stdout: str) -> list[str]:
    assert "== restore-test summary ==" in stdout, stdout
    return stdout.split("== restore-test summary ==", 1)[1].strip().splitlines()


def test_a_good_exercise_ends_in_the_fixed_summary(tmp_path):
    done, _ = _run(
        tmp_path,
        "restore-test",
        "uat",
        "chosen.sql.gz",
        dumps=[("uat", "chosen.sql.gz", 1_790_000_000)],
    )

    assert done.returncode == 0, done.stderr
    summary = _summary(done.stdout)
    assert summary[0] == "environment=uat"
    assert summary[1] == "dump=chosen.sql.gz"
    assert summary[2].startswith("duration=") and summary[2].endswith("s")
    assert summary[3:] == [
        "alembic_version=2026_09_27_101500",
        "mdm.members=412",
        "mdm.persons=977",
        "activities.registrations=1530",
        "payment.payment_records=1204",
        "result=ok",
    ], summary


def test_a_failed_exercise_says_failed_and_exits_non_zero(tmp_path):
    done, _ = _run(tmp_path, "restore-test", "hdev", code=3)

    assert done.returncode == 3
    assert _summary(done.stdout)[-1] == "result=failed"


# ── Findable ──────────────────────────────────────────────────────────────────


def test_the_verb_appears_in_the_help_text(tmp_path):
    done, _ = _run(tmp_path, "help")

    assert "raakctl restore-test <env> [dump]" in done.stdout
    assert "--confirm" in done.stdout.split("restore-test", 1)[1][:400]


def test_the_menu_runs_the_exercise(tmp_path):
    """`r`, then the environment by number (uat = 2), then quit."""
    done, invocations = _run(tmp_path, stdin="r\n2\nq\n")

    assert "r) restore exercise" in done.stdout
    assert f"cwd={tmp_path / 'uat'}" in invocations, (done.stdout, done.stderr)
    assert "result=ok" in done.stdout
