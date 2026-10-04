"""#1530 — the deploy's smoke test names the tenant it checks.

Since #1523 the bare HDEV host resolves to the platform, which has activities
and payment off, so the smoke test failed 1 of 2 on HDEV
(`/api/v1/activities` 404, `/api/v1/payment-status/records` 404). deploy.sh now
runs the smoke test under the association's path prefix, set once per
environment in its config block, and passes the bare host as PLATFORM_BASE only
where the platform check is switched on.

This runs the REAL deploy.sh in a throwaway checkout with a stubbed outside
world, and records what `tests/run-all.sh` was given. Red against master: BASE
was the bare host and PLATFORM_BASE was not passed.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]


def _deploy(tmp_path, env_name: str) -> str:
    work = tmp_path / "checkout"
    (work / "tests").mkdir(parents=True)
    (work / "scripts").mkdir()
    shutil.copy(ROOT / "deploy.sh", work / "deploy.sh")
    shutil.copy(ROOT / "scripts" / "deploy-summary.sh", work / "scripts")
    seen = tmp_path / "smoke-target"
    (work / "tests" / "run-all.sh").write_text(
        f'#!/bin/sh\necho "BASE=$BASE PLATFORM_BASE=$PLATFORM_BASE" > "{seen}"\nexit 0\n'
    )
    (work / "tests" / "run-all.sh").chmod(0o755)
    for name in (".env.hdev", ".env.uat", ".env.prod"):
        # A trailing slash, as an env file may carry one: no `//` in the target.
        (work / name).write_text("FRONTEND_URL=http://site.test/\n")

    stubs = tmp_path / "bin"
    stubs.mkdir()
    (stubs / "curl").write_text("#!/bin/sh\nexit 0\n")
    (stubs / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (stubs / "git").write_text(
        '#!/bin/sh\ncase "$1" in describe) echo v0.0.0 ;; rev-parse) echo deadbee ;; esac\nexit 0\n'
    )
    # One head and a clean start, so the post-check passes and nothing rolls back.
    (stubs / "docker").write_text(
        '#!/bin/sh\ncase "$*" in\n'
        '  *"alembic heads"*|*"alembic current"*) echo "001 (head)" ;;\n'
        '  *"logs backend"*) printf "INFO:     Uvicorn running on http://0.0.0.0:8000\\n" ;;\n'
        "esac\nexit 0\n"
    )
    for stub in stubs.iterdir():
        stub.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{stubs}:{env['PATH']}"
    env["DEPLOY_REEXEC"] = "1"
    env["LOG_OUT"] = str(tmp_path / "deploy.log")
    env.pop("SMOKE_BASE", None)
    args = ["bash", "./deploy.sh", env_name] + (["v0.0.0"] if env_name != "hdev" else [])
    done = subprocess.run(args, cwd=work, env=env, capture_output=True, text=True, timeout=120)
    assert seen.exists(), f"the smoke test never ran:\n{done.stdout[-2000:]}\n{done.stderr[-2000:]}"
    return seen.read_text().strip()


@pytest.mark.parametrize(
    "env_name,expected",
    [
        (
            "hdev",
            "BASE=http://localhost:8081/raakmillegem PLATFORM_BASE=http://localhost:8081",
        ),
        ("uat", "BASE=http://site.test/raakmillegem PLATFORM_BASE="),
        ("prod", "BASE=http://site.test/raakmillegem PLATFORM_BASE="),
    ],
)
def test_the_smoke_test_checks_an_association_by_its_prefix(tmp_path, env_name, expected):
    assert _deploy(tmp_path, env_name) == expected


def test_the_platform_check_runs_only_when_it_is_named(tmp_path):
    """run-all.sh picks up tests/platform/*.sh only with PLATFORM_BASE set."""
    tests = tmp_path / "tests"
    (tests / "smoke").mkdir(parents=True)
    (tests / "platform").mkdir()
    shutil.copy(ROOT / "tests" / "run-all.sh", tests / "run-all.sh")
    (tests / "lib.sh").write_text("")
    (tests / "smoke" / "a.sh").write_text('DESC="smoke a"\nexit 0\n')
    (tests / "platform" / "p.sh").write_text(
        'DESC="platform p"\n[ "$PLATFORM_BASE" = "http://p.test" ] || exit 1\nexit 0\n'
    )

    def run(**extra):
        env = {k: v for k, v in os.environ.items() if k != "PLATFORM_BASE"}
        env.update(BASE="http://s.test", **extra)
        return subprocess.run(
            ["bash", str(tests / "run-all.sh")], env=env, capture_output=True, text=True
        ).stdout

    without = run()
    assert "smoke a" in without and "platform p" not in without
    named = run(PLATFORM_BASE="http://p.test")
    assert "smoke a" in named and "platform p" in named and "1 gefaald" not in named
