"""#1971 — `scripts/ruff-fix.sh` applies ruff's own diffs on the host.

The helper container of `scripts/test-local.sh` runs as `app` and cannot write into
the bind-mounted working copy, so ruff cannot fix in place there. The script has ruff
print `--diff` in that container and applies each diff on the host with `patch`.

What stands here, with a fake `docker` on the PATH that records every call and prints
the diffs a real ruff would (as in `test_local_runner_existing_database.py`):

* a missing helper container is refused with one sentence, and **nothing else is
  called** — in particular no `docker run`: the script never makes a container;
* the diffs reach the files of the checkout, and every docker call is a plain
  `docker exec -w /app/backend <container> python -m ruff …`: no `-u`, no `-e`, no URL,
  no `compose`, nothing written inside the container;
* a diff with a hunk that does not apply is refused **before** anything is written —
  also the file in it that would have applied;
* what ruff cannot fix is shown and ends the script with exit code 1.

Broken to check that these can go red (run with scripts/test-local.sh, each restored
afterwards): the `--dry-run` taken out of `apply_diff` →
`test_a_hunk_that_does_not_apply_leaves_every_file_untouched` fails: the file that
applied was written; the `inspect` guard removed → `test_a_missing_helper_container_is_refused`
fails on the extra calls.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ruff-fix.sh"

pytestmark = pytest.mark.ui_agnostisch

BEFORE = 'x = {  "a":1 }\n'
AFTER = 'x = {"a": 1}\n'

FORMAT_DIFF = """--- a.py
+++ a.py
@@ -1 +1 @@
-x = {  "a":1 }
+x = {"a": 1}
"""

#: The same file again, from a text the checkout does not hold: `patch` refuses it.
STRANGER_DIFF = """--- b.py
+++ b.py
@@ -1 +1 @@
-nothing like this is in the file
+changed
"""


def _run(tmp_path, *, container="running", format_diff="", check_diff="", final_rc=0, args=()):
    """The script in a checkout called "checkout", with a fake `docker` that records."""
    root = tmp_path / "checkout"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "ruff-fix.sh")
    (root / "backend").mkdir()
    (root / "backend" / "a.py").write_text(BEFORE)
    (root / "backend" / "b.py").write_text("y = 1\n")

    (tmp_path / "format.diff").write_text(format_diff)
    (tmp_path / "check.diff").write_text(check_diff)
    trace = tmp_path / "docker-calls.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    inspect = "echo true" if container == "running" else "exit 1"
    (fake_bin / "docker").write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{trace}"\n'
        'case "$*" in\n'
        f"  inspect*) {inspect} ;;\n"
        f'  *"ruff format"*"--diff"*) cat "{tmp_path}/format.diff" ;;\n'
        f'  *"ruff check"*"--diff"*) cat "{tmp_path}/check.diff" ;;\n'
        f'  *"ruff check"*) echo "F821 Undefined name" ; exit {final_rc} ;;\n'
        "esac\n"
        "exit 0\n"
    )
    (fake_bin / "docker").chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    done = subprocess.run(
        ["bash", str(root / "scripts" / "ruff-fix.sh"), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    calls = trace.read_text().splitlines() if trace.exists() else []
    return done, calls, root


def test_a_missing_helper_container_is_refused(tmp_path):
    done, calls, root = _run(tmp_path, container="missing", format_diff=FORMAT_DIFF)

    assert done.returncode == 2
    assert "REFUSED" in done.stderr and "raaktest-checkout" in done.stderr, done.stderr
    assert len(calls) == 1 and calls[0].startswith("inspect"), calls
    assert (root / "backend" / "a.py").read_text() == BEFORE


def test_the_diff_reaches_the_file_and_the_container_is_only_asked_to_run_ruff(tmp_path):
    done, calls, root = _run(tmp_path, format_diff=FORMAT_DIFF)

    assert done.returncode == 0, done.stderr
    assert (root / "backend" / "a.py").read_text() == AFTER
    assert "tree is clean" in done.stdout
    ruff_calls = [c for c in calls if not c.startswith("inspect")]
    assert len(ruff_calls) == 4, ruff_calls  # check --diff, format --diff, then both checks
    for call in ruff_calls:
        assert call.startswith("exec -w /app/backend raaktest-checkout python -m ruff "), call
        assert " -u " not in call and " -e " not in call and "--env" not in call, call
    assert not any(c.startswith(("run", "compose", "rm")) for c in calls), calls


def test_the_paths_of_the_caller_reach_ruff(tmp_path):
    done, calls, _root = _run(tmp_path, args=("app/domains/cms", "tests/test_x.py"))

    assert done.returncode == 0, done.stderr
    assert all(c.endswith("app/domains/cms tests/test_x.py") for c in calls[1:]), calls


def test_a_hunk_that_does_not_apply_leaves_every_file_untouched(tmp_path):
    """a.py would apply, b.py would not: nothing may be written."""
    done, _calls, root = _run(tmp_path, format_diff=FORMAT_DIFF + STRANGER_DIFF)

    assert done.returncode == 2
    assert "REFUSED" in done.stderr and "does not apply" in done.stderr, done.stderr
    assert (root / "backend" / "a.py").read_text() == BEFORE, "a half applied diff"
    assert (root / "backend" / "b.py").read_text() == "y = 1\n"


def test_what_ruff_cannot_fix_is_shown_and_ends_with_one(tmp_path):
    done, _calls, _root = _run(tmp_path, final_rc=1)

    assert done.returncode == 1
    assert "F821 Undefined name" in done.stderr, done.stderr
    assert "cannot fix" in done.stderr
