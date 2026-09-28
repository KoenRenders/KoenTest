"""#1253 — the six post-deploy measurements come from a machine-readable block.

After every deploy six measurements are reported (CLAUDE.md, "Verifying a deploy via
the backend logs"). They used to be fished out of the prose of deploy.sh with search
terms on its Dutch messages — a second copy of what the script says, which #578 (the
scripts in English) would have broken in one go, and which one reworded sentence
would have broken silently: a search term that finds nothing reads as "no
migrations ran, as expected".

So deploy.sh and logging.sh print one block, from one definition
(`scripts/deploy-summary.sh`), and **the key names are the contract**. These tests
run the REAL scripts in a throwaway checkout with a fake `docker`, `git` and `curl`,
the same harness as test_deploy_postcheck.py.

Each test first asserts that it FOUND exactly one block, and only then what is in
it — a pattern search that finds nothing must not read as green (#678).

Broken on purpose to check these tests can go red (run, then restored):
  - `migrations_applied` removed from SUMMARY_KEYS → the contract tests fail with
    "missing keys: ['migrations_applied']" for deploy.sh and logging.sh alike;
  - an extra key `extra` added to SUMMARY_KEYS (additive) → the contract tests fail
    with "unexpected keys: ['extra']";
  - the NOT_MEASURED branch of summary_measure_startup made to return an empty
    value → test_no_startup_window_is_not_measured_rather_than_empty fails;
  - `set +x` removed from summary_print → five tests fail with "the summary block is
    interleaved with other output: '+ for key in ...'" (deploy.sh runs with set -x).
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]

# The contract. A reader of the block depends on these names, in this order; a
# change here is a new version of the block (v2), not an edit.
CONTRACT = [
    "environment",
    "commit",
    "alembic_heads",
    "alembic_current",
    "migrations_applied",
    "clean_start",
    "smoke",
]
BEGIN = "=== DEPLOY SUMMARY v1 ==="
END = "=== END DEPLOY SUMMARY ==="

STARTUP = """\
==> Running database migrations...
{upgrades}==> Starting API server...
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
"""


def _build(tmp_path, *, log, heads="095 (head)\n", smoke_exit=0):
    work = tmp_path / "checkout"
    (work / "tests").mkdir(parents=True)
    (work / "scripts").mkdir()
    for name in ("deploy.sh", "logging.sh"):
        shutil.copy(ROOT / name, work / name)
    shutil.copy(ROOT / "scripts" / "deploy-summary.sh", work / "scripts")
    counts = "passed=5 failed=0 skipped=0" if smoke_exit == 0 else "passed=4 failed=1 skipped=0"
    (work / "tests" / "run-all.sh").write_text(
        "#!/bin/sh\n"
        f'[ -n "$SMOKE_RESULT_FILE" ] && echo "{counts}" > "$SMOKE_RESULT_FILE"\n'
        f"exit {smoke_exit}\n"
    )
    (work / "tests" / "run-all.sh").chmod(0o755)
    for name in (".env.hdev", ".env.uat", ".env.prod"):
        (work / name).write_text("FRONTEND_URL=http://site.test\n")
    (tmp_path / "heads").write_text(heads)
    (tmp_path / "backendlog").write_text(log)

    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    (fakebin / "docker").write_text(
        '#!/bin/sh\ncase "$*" in\n'
        f'  *"alembic heads"*|*"alembic current"*) cat "{tmp_path}/heads" ;;\n'
        f'  *"logs backend"*) cat "{tmp_path}/backendlog" ;;\n'
        "esac\nexit 0\n"
    )
    (fakebin / "curl").write_text("#!/bin/sh\nexit 0\n")
    (fakebin / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (fakebin / "git").write_text(
        '#!/bin/sh\ncase "$1" in describe) echo v2.7.0 ;; rev-parse) echo deadbee ;;\n'
        '  grep) case "$*" in *down_revision*) ;; *) echo "revision = \'095\'" ;; esac ;;\n'
        "esac\nexit 0\n"
    )
    for f in fakebin.iterdir():
        f.chmod(0o755)
    return work, fakebin


def _run(work, fakebin, tmp_path, script, *args):
    env = dict(os.environ)
    env["PATH"] = f"{fakebin}:{env['PATH']}"
    env["DEPLOY_REEXEC"] = "1"
    env["LOG_OUT"] = str(tmp_path / "out.log")
    return subprocess.run(
        ["bash", f"./{script}", *args],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _blocks(output: str) -> list[dict]:
    """Every summary block in the output, as an ordered key → value dict."""
    found, current = [], None
    for line in output.splitlines():
        if line == BEGIN:
            current = {}
        elif line == END and current is not None:
            found.append(current)
            current = None
        elif current is not None:
            # The block must read on its own: a trace line or any other output
            # between the markers is a failure, not something to skip over.
            assert "=" in line and not line.startswith("+"), (
                f"the summary block is interleaved with other output: {line!r}"
            )
            key, value = line.split("=", 1)
            current[key] = value
    return found


def _one_block(done) -> dict:
    blocks = _blocks(done.stdout)
    assert blocks, f"no summary block in the output at all:\n{done.stdout[-2000:]}"
    assert len(blocks) == 1, f"expected one summary block, found {len(blocks)}"
    return blocks[0]


def _assert_contract(block: dict, who: str) -> None:
    keys = list(block)
    missing = [k for k in CONTRACT if k not in keys]
    unexpected = [k for k in keys if k not in CONTRACT]
    assert not missing, f"{who}: missing keys: {missing}"
    assert not unexpected, f"{who}: unexpected keys: {unexpected}"
    assert keys == CONTRACT, f"{who}: keys out of order: {keys}"


def test_deploy_prints_the_contract(tmp_path):
    work, fakebin = _build(tmp_path, log=STARTUP.format(upgrades=""))
    done = _run(work, fakebin, tmp_path, "deploy.sh", "hdev")
    assert done.returncode == 0, done.stdout[-3000:]
    block = _one_block(done)
    _assert_contract(block, "deploy.sh")
    assert block["environment"] == "hdev"
    assert block["commit"] == "v2.7.0"
    assert block["alembic_heads"] == block["alembic_current"] == "095"
    assert block["clean_start"] == "ok"
    assert block["smoke"] == "5 passed, 0 failed, 0 skipped"


def test_diagnose_prints_the_same_keys(tmp_path):
    """`raak diagnose` (logging.sh) and deploy.sh speak the same contract."""
    work, fakebin = _build(tmp_path, log=STARTUP.format(upgrades=""))
    done = _run(work, fakebin, tmp_path, "logging.sh", "prod")
    assert done.returncode == 0, done.stdout[-3000:]
    block = _one_block(done)
    _assert_contract(block, "logging.sh")
    assert block["smoke"] == "NOT_MEASURED", "diagnose runs no smoke test and must say so"
    assert block["migrations_applied"] == "", block


def test_no_migrations_is_an_empty_measurement(tmp_path):
    work, fakebin = _build(tmp_path, log=STARTUP.format(upgrades=""))
    block = _one_block(_run(work, fakebin, tmp_path, "deploy.sh", "hdev"))
    assert "migrations_applied" in block, "the key must be there, even when nothing ran"
    assert block["migrations_applied"] == "", block


def test_applied_migrations_are_named_in_order(tmp_path):
    upgrades = (
        "INFO  [alembic.runtime.migration] Running upgrade 094 -> 095, one\n"
        "INFO  [alembic.runtime.migration] Running upgrade 095 -> 096, two\n"
    )
    work, fakebin = _build(tmp_path, log=STARTUP.format(upgrades=upgrades), heads="096 (head)\n")
    block = _one_block(_run(work, fakebin, tmp_path, "deploy.sh", "hdev"))
    assert block["migrations_applied"] == "095,096", block


def test_no_startup_window_is_not_measured_rather_than_empty(tmp_path):
    """The difference the issue exists for: "no migrations" versus "did not look"."""
    work, fakebin = _build(tmp_path, log="a backend that printed something else\n")
    block = _one_block(_run(work, fakebin, tmp_path, "deploy.sh", "hdev"))
    assert block["migrations_applied"] == "NOT_MEASURED", block
    assert block["clean_start"] == "NOT_MEASURED", block


def test_a_failed_smoke_test_still_prints_a_complete_block(tmp_path):
    work, fakebin = _build(tmp_path, log=STARTUP.format(upgrades=""), smoke_exit=1)
    done = _run(work, fakebin, tmp_path, "deploy.sh", "hdev")
    assert done.returncode == 1
    block = _one_block(done)
    _assert_contract(block, "deploy.sh on a failed smoke test")
    assert block["smoke"] == "4 passed, 1 failed, 0 skipped"
    assert block["alembic_heads"] == "095", "measured on the failure path too"


def test_the_real_smoke_runner_writes_its_counts(tmp_path):
    """deploy.sh reads the counts from the file tests/run-all.sh writes, not from its
    Dutch result sentence. The real runner, with one passing and one failing check."""
    tests = tmp_path / "tests"
    (tests / "smoke").mkdir(parents=True)
    shutil.copy(ROOT / "tests" / "run-all.sh", tests / "run-all.sh")
    (tests / "smoke" / "a_ok.sh").write_text("exit 0\n")
    (tests / "smoke" / "b_fails.sh").write_text("exit 1\n")
    result = tmp_path / "result"
    env = dict(os.environ, SMOKE_RESULT_FILE=str(result))
    subprocess.run(
        ["bash", str(tests / "run-all.sh")], env=env, capture_output=True, text=True, timeout=60
    )
    assert result.exists(), "run-all.sh wrote no result file"
    assert result.read_text().strip() == "passed=1 failed=1 skipped=0"
