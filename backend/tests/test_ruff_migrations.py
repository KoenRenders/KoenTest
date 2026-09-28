"""#781: ruff leaves the merged migrations alone and checks every new one.

`CLAUDE.md` forbids modifying a migration that has been merged, so the ruff
config freezes the migrations that existed at #781 in `extend-exclude`. That list
must do two things at once, and a mistake in either direction is silent:

  - a migration on the list is never touched: not by the one-off formatting pass
    and not by a later `ruff format .`;
  - a migration generated after #781 is NOT on the list, so a formatting slip or
    an undefined name in it turns CI red before it ever runs on a database.

These tests run the real ruff with the real config. They pass file contents on
stdin under a chosen path (`--stdin-filename`), which is how the exclusion is
applied without writing into the repository; `force-exclude = true` makes ruff
honour the list for a single path as well.

Broken on purpose to check these tests can go red (run, then restored):
  - `force-exclude = true` removed → the frozen migration is formatted after all,
    and `test_a_frozen_migration_is_left_alone` fails;
  - a future migration (`999_…`) added to the frozen list (additive) →
    `test_a_new_migration_is_checked` fails on its first assertion, and the list
    test fails with "frozen entries whose file no longer exists".
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"

#: The number of migrations frozen by #781. The list may only shrink.
FROZEN_AT_781 = 169

#: Valid Python that `ruff format` would rewrite (spacing, quotes, a long call).
BADLY_FORMATTED = "import sqlalchemy as sa\nx=sa.Column( 'a',sa.String(  ) )\n"


def _ruff(*args: str, stdin: str, path: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ruff", *args, "--stdin-filename", path, "-"],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=BACKEND,
        timeout=60,
    )


def _frozen() -> list[str]:
    config = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    return config["tool"]["ruff"]["extend-exclude"]


def test_the_frozen_list_names_existing_migrations_and_never_grows():
    frozen = _frozen()
    assert frozen, "the ruff config freezes no migrations at all"
    missing = [p for p in frozen if not (BACKEND / p).exists()]
    assert not missing, f"frozen entries whose file no longer exists — remove them: {missing}"
    assert len(frozen) <= FROZEN_AT_781, (
        f"the frozen list grew to {len(frozen)} (was {FROZEN_AT_781}); a new migration "
        f"belongs under ruff, not on the list"
    )


def test_a_frozen_migration_is_left_alone():
    newest_frozen = sorted(_frozen())[-1]
    done = _ruff("format", "--check", stdin=BADLY_FORMATTED, path=newest_frozen)
    assert done.returncode == 0, (
        f"ruff formatted the frozen migration {newest_frozen}:\n{done.stdout}{done.stderr}"
    )


def test_a_new_migration_is_checked():
    new = "alembic/versions/999_2099_01_01_000000_future_migration_.py"
    assert new not in _frozen()
    done = _ruff("format", "--check", stdin=BADLY_FORMATTED, path=new)
    assert done.returncode != 0, "a badly formatted NEW migration passed ruff format --check"
    linted = _ruff("check", stdin="def upgrade():\n    return undefined_name\n", path=new)
    assert linted.returncode != 0 and "F821" in linted.stdout, (
        f"an undefined name in a NEW migration passed ruff check:\n{linted.stdout}"
    )


def test_the_revision_template_renders_ruff_clean():
    """Every migration starts as this template; if it is not clean, every new one fails.

    Rendered with a body that uses `op` and `sa`, as every real migration does. The
    bare stub (`pass`) does report `op` and `sa` as unused (F401), and that is
    right: an empty migration should not be committed, and an unused import in a
    real one is worth reporting. A `# noqa` in the template would hide it forever.
    """
    mako = pytest.importorskip("mako.template")
    rendered = mako.Template(filename=str(BACKEND / "alembic" / "script.py.mako")).render(
        message="add a column",
        up_revision="168_2026_10_01_120000",
        down_revision="167_2026_09_28_045715",
        branch_labels=None,
        depends_on=None,
        create_date="2026-10-01 12:00:00",
        imports="",
        upgrades='op.add_column("things", sa.Column("colour", sa.String(20)))',
        downgrades='op.drop_column("things", "colour")',
    )
    new = "alembic/versions/168_2026_10_01_120000_add_a_column.py"
    formatted = _ruff("format", "--check", stdin=rendered, path=new)
    assert formatted.returncode == 0, f"the template is not ruff-formatted:\n{formatted.stdout}"
    linted = _ruff("check", stdin=rendered, path=new)
    assert linted.returncode == 0, f"the template does not pass ruff check:\n{linted.stdout}"
