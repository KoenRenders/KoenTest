"""#1296 — the e2e environment has one source, read by CI and by the local script.

The CI job `e2e` and `scripts/e2e-local.sh` each kept their own list of the
variables the e2e server runs with, and the lists drifted: the script lacked
`PAYMENT_PROVIDER=stub` (#1274), so the payment e2e's went red locally on what CI
showed green. A local run that is red on something that is not broken teaches
people to ignore red.

So what shapes the app under test lives in `backend/tests_e2e/e2e.env`, and both
read it: the CI job appends it to `$GITHUB_ENV`, the script passes it to every
`docker exec` with `--env-file`. What differs by place — the database URL, the
secret, the base URL — stays where it is set. These tests hold that line from
both sides: a variable added to only one of the two places fails here, whichever
place it is.

The script really runs, with a fake `docker` on the PATH that records every call;
that record is what is judged, not the script's text.

Proven red (29 September 2026), each an additive variable in one place only:

| Violation | Failed |
|---|---|
| `FOO: "1"` added to the CI job's `env:` | "the CI job sets only what differs by place" |
| `-e FOO=1` added to the script's server `docker exec` | "the script sets only what differs by place" |
| `--env-file "$ENV_FILE"` dropped from the pytest `docker exec` | "every exec reads the file" |
| the `$GITHUB_ENV` step moved after "Start backend" | "the CI job reads the file before the server starts" |
"""

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
ENV_FILE = REPO / "backend" / "tests_e2e" / "e2e.env"
WORKFLOW = REPO / ".github" / "workflows" / "backend-tests.yml"
SCRIPT = REPO / "scripts" / "e2e-local.sh"

pytestmark = pytest.mark.ui_agnostisch

# What may differ by place, and why. Everything else belongs in e2e.env.
CI_PLACE = {"DATABASE_URL", "SECRET_KEY", "E2E_BASE_URL"}
SCRIPT_PLACE = {
    "DATABASE_URL",  # the helper container's own database, credentials read at run time
    "SECRET_KEY",
    "E2E_BASE_URL",
    # The helper container outlives a run (`sleep infinity`); the scheduler is kept
    # out of it, as in scripts/test-local.sh. CI leaves the default on.
    "JOBS_ENABLED",
}
# Set on the seed step alone, in both places: seed_e2e.py refuses without it.
SEED_ONLY = {"E2E_SEED"}


def _file_names() -> dict[str, str]:
    out = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, _, value = line.partition("=")
            out[name] = value
    return out


def _e2e_job() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["e2e"]


def _script_calls(tmp_path) -> list[str]:
    """Every docker call of the script, with the helper container created fresh."""
    trace = tmp_path / "docker.txt"
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    fake = fakebin / "docker"
    # `inspect` fails, so the script takes the path that creates the container.
    fake.write_text(
        f'#!/bin/sh\necho "$@" >> "{trace}"\ncase "$1" in inspect) exit 1 ;; esac\nexit 0\n'
    )
    fake.chmod(0o755)
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", E2E_DB_NAME="raake2e_proef")
    done = subprocess.run(
        ["bash", str(SCRIPT), "tests_e2e/test_x.py"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return trace.read_text().splitlines()


def _runs_code(call: str) -> bool:
    """The calls that start something in the helper container — not the tool
    installs and not the readiness probe, which run no app code."""
    return call.startswith(("run ", "exec ")) and not re.search(
        r"\b(pip|playwright) install|urllib\.request", call
    )


# ── The file ──────────────────────────────────────────────────────────────────


def test_the_file_carries_the_stub_and_dev():
    names = _file_names()
    assert names.get("PAYMENT_PROVIDER") == "stub", names
    assert names.get("APP_ENV") == "dev", names
    # docker's --env-file keeps quotes as part of the value
    assert not [v for v in names.values() if v[:1] in "\"'"], names


# ── CI ────────────────────────────────────────────────────────────────────────


def test_the_ci_job_sets_only_what_differs_by_place():
    job = _e2e_job()
    assert set(job["env"]) == CI_PLACE, sorted(set(job["env"]) ^ CI_PLACE)
    for step in job["steps"]:
        extra = set(step.get("env", {})) - SEED_ONLY
        assert not extra, f"step {step.get('name')!r} sets {sorted(extra)} — put it in e2e.env"


def test_the_ci_job_reads_the_file_before_the_server_starts():
    names = [s.get("name", "") for s in _e2e_job()["steps"]]
    runs = [s.get("run", "") for s in _e2e_job()["steps"]]
    reads = [i for i, r in enumerate(runs) if "tests_e2e/e2e.env" in r and "$GITHUB_ENV" in r]
    assert len(reads) == 1, runs
    assert reads[0] < names.index("Start backend") < names.index("Run e2e (golden flows)")


# ── The script ────────────────────────────────────────────────────────────────


def test_every_exec_reads_the_file(tmp_path):
    calls = [c for c in _script_calls(tmp_path) if _runs_code(c)]
    # creation, alembic, postal codes, seed, server, pytest
    assert len(calls) >= 6, calls
    missing = [c for c in calls if f"--env-file {ENV_FILE}" not in c]
    assert not missing, "without the e2e.env:\n" + "\n".join(missing)


def test_the_script_sets_only_what_differs_by_place(tmp_path):
    set_inline = {
        m.group(1) for c in _script_calls(tmp_path) for m in re.finditer(r"-e ([A-Z0-9_]+)=", c)
    }
    extra = set_inline - SCRIPT_PLACE - SEED_ONLY
    assert not extra, f"the script sets {sorted(extra)} itself — put it in e2e.env"
    assert not set_inline & set(_file_names()), "set in the script AND in e2e.env"
