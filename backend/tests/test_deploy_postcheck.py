"""#604 — the deploy checks the migration chain and the startup itself.

After EVERY deploy three things ought to hold: exactly one alembic head, a `current`
equal to it, and a startup without errors. That happened by hand, or through
`raakctl diagnose` — a report without an exit code that you run separately, after the
deploy. The smoke test does not see these failures: it checks that public pages return
200 and that the admin is shielded. A split migration chain passes that unnoticed.

**These tests run the real `deploy.sh`** in a throwaway directory, with a fake `docker`
that returns alembic output and backend logs. A `grep` for "is the check in there"
would also be green if it guarded the wrong environment or never stopped anything —
exactly the class of failure that produced #800.

The core is the DIFFERENCE between the environments: the chain check is a gate on
UAT/PROD and reporting-only on HDEV, and the log check is reporting-only everywhere for
now. A test that only walks the happy path, or only one environment, would not see that
difference.

Broken on purpose to check that these tests can go red: set `KETEN_GATE=0` for uat →
the rollback test falls over while the hdev test stays green; widened the startup window
to the whole log → the scope test falls over.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy.sh"

HEALTHY_LOG = """\
==> Running database migrations...
INFO  [alembic.runtime.migration] Running upgrade 094 -> 095
==> Seeding postal codes (if empty)...
  1234 postal codes already present, skipping.
==> Starting API server...
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
"""


def _build(tmp_path, *, heads="095 (head)\n", current="095 (head)\n",
           log=HEALTHY_LOG):
    """A throwaway checkout with the REAL deploy.sh and a fake outside world."""
    work = tmp_path / "checkout"
    (work / "tests").mkdir(parents=True)
    shutil.copy(DEPLOY, work / "deploy.sh")
    (work / "deploy.sh").chmod(0o755)

    smoke_counter = tmp_path / "smoke-runs"
    (work / "tests" / "run-all.sh").write_text(
        f'#!/bin/sh\necho x >> "{smoke_counter}"\nexit 0\n')
    (work / "tests" / "run-all.sh").chmod(0o755)

    for name in (".env.hdev", ".env.uat", ".env.prod"):
        (work / name).write_text("FRONTEND_URL=http://site.test\n")

    (tmp_path / "heads").write_text(heads)
    (tmp_path / "current").write_text(current)
    (tmp_path / "backendlog").write_text(log)

    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    # The fake container answers exactly what the post-check asks. `ps -q db` stays
    # empty, so the script skips the pre-migration backup.
    (fakebin / "docker").write_text(
        '#!/bin/sh\ncase "$*" in\n'
        f'  *"alembic heads"*) cat "{tmp_path}/heads" ;;\n'
        f'  *"alembic current"*) cat "{tmp_path}/current" ;;\n'
        f'  *"logs backend"*) cat "{tmp_path}/backendlog" ;;\n'
        'esac\nexit 0\n')
    (fakebin / "curl").write_text('#!/bin/sh\nexit 0\n')
    (fakebin / "git").write_text(
        '#!/bin/sh\ncase "$1" in describe) echo v0.0.0 ;; rev-parse) echo deadbee ;; esac\n'
        'exit 0\n')
    (fakebin / "sleep").write_text('#!/bin/sh\nexit 0\n')
    for f in fakebin.iterdir():
        f.chmod(0o755)

    return work, fakebin, smoke_counter


def _run(work, fakebin, environment, tmp_path, **extra_env):
    env = dict(os.environ)
    env["PATH"] = f"{fakebin}:{env['PATH']}"
    # The re-exec after the checkout (#162) is not what is under test here.
    env["DEPLOY_REEXEC"] = "1"
    env["LOG_OUT"] = str(tmp_path / "deploy.log")
    env.update(extra_env)
    args = ["bash", "./deploy.sh", environment] + (["v0.0.0"] if environment != "hdev" else [])
    return subprocess.run(args, cwd=work, env=env, capture_output=True, text=True,
                          timeout=120)


@pytest.mark.parametrize("environment", ["hdev", "uat", "prod"])
def test_a_healthy_deploy_simply_continues(environment, tmp_path):
    """The counterproof that makes the rest usable: this must never become a false
    rollback."""
    work, fakebin, _ = _build(tmp_path)

    done = _run(work, fakebin, environment, tmp_path)

    assert done.returncode == 0, done.stdout[-3000:]
    assert "Migratieketen OK" in done.stdout and "Schone start OK" in done.stdout


def test_two_heads_roll_uat_back(tmp_path):
    """A split chain is the failure this issue started from: it passes the smoke test
    unnoticed, because the site simply answers."""
    work, fakebin, smoke_counter = _build(tmp_path, heads="095 (head)\n0a1b2c (head)\n")

    # DEPLOY_PREV_REF must differ from what runs now, otherwise there is no target to
    # roll back to and the script stops immediately.
    done = _run(work, fakebin, "uat", tmp_path, DEPLOY_PREV_REF="v0.0.1")

    assert done.returncode != 0, "a split chain must not count as success"
    assert "2 heads" in done.stdout
    assert "Automatische rollback naar v0.0.1" in done.stdout
    assert smoke_counter.read_text().count("x") == 2, (
        "the rollback did not re-run the smoke test, or rolled back more than once")


def test_two_heads_do_not_stop_hdev(tmp_path):
    """HDEV is the integration line: report loudly, stop nothing."""
    work, fakebin, _ = _build(tmp_path, heads="095 (head)\n0a1b2c (head)\n")

    done = _run(work, fakebin, "hdev", tmp_path)

    assert done.returncode == 0, "HDEV must not fail on this"
    assert "2 heads" in done.stdout, "…but it does have to be in the output"
    assert "rapporterend op hdev" in done.stdout


def test_a_lagging_current_fails(tmp_path):
    """Two heads is not the only shape: a migration that never applied leaves the chain
    intact while the database lags behind."""
    work, fakebin, _ = _build(tmp_path, heads="095 (head)\n", current="094\n")

    done = _run(work, fakebin, "prod", tmp_path, DEPLOY_PREV_REF="v0.0.1")

    assert done.returncode != 0
    assert "niet gelijk aan" in done.stdout or "en niet [095]" in done.stdout


def test_a_traceback_at_startup_is_reported_but_does_not_roll_back(tmp_path):
    """The log check is deliberately reporting-only this release: a false rollback on
    PROD over a single ERROR line costs more than a missed warning."""
    broken = HEALTHY_LOG.replace(
        "==> Starting API server...",
        "Traceback (most recent call last):\n  RuntimeError: seed failed\n"
        "==> Starting API server...")
    work, fakebin, _ = _build(tmp_path, log=broken)

    done = _run(work, fakebin, "prod", tmp_path, DEPLOY_PREV_REF="v0.0.1")

    assert done.returncode == 0, "LOG_GATE is 0; this must not roll anything back yet"
    assert "fouten tijdens het opstarten" in done.stdout
    assert "RuntimeError: seed failed" in done.stdout


def test_traffic_after_startup_does_not_count(tmp_path):
    """The window is tight: container start until 'Uvicorn running'.

    Without that scope EVERY deploy becomes a complaint — a Mollie webhook returning 404
    or a visitor with an invalid request is not a deploy failure. And with LOG_GATE=1
    that would later become a rollback.
    """
    noise = HEALTHY_LOG + (
        'ERROR:    Exception in ASGI application\n'
        'Traceback (most recent call last):\n  ValueError: broken request\n')
    work, fakebin, _ = _build(tmp_path, log=noise)

    done = _run(work, fakebin, "prod", tmp_path, DEPLOY_PREV_REF="v0.0.1")

    assert done.returncode == 0
    assert "Schone start OK" in done.stdout
    assert "broken request" not in done.stdout, (
        "traffic after 'Uvicorn running' falls inside the startup window")


def test_a_backend_that_never_starts_is_noticed(tmp_path):
    """The failure the smoke test really cannot see while Caddy still serves an old
    container: migrations started, but 'Uvicorn running' never arrives."""
    work, fakebin, _ = _build(
        tmp_path, log="==> Running database migrations...\nINFO  [alembic] busy\n")

    done = _run(work, fakebin, "hdev", tmp_path)

    assert "bereikte 'Uvicorn running' niet" in done.stdout
