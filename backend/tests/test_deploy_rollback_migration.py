"""#1203 — no automatic rollback over a release that adds a migration.

The previous image runs `alembic upgrade head` at startup. After a release with a
migration the database carries a revision that image does not know, alembic
refuses, and the backend does not start — so the rollback would replace a
running-but-failed release by one that is down. Koen's decision (27 September
2026): `deploy.sh` compares the alembic head of the previous ref with that of the
new one, straight from git, and skips the rollback when they differ, stopping
with the database revision, the reason and the dump to restore.

**These tests run the real `deploy.sh`** against a real git repository with two
refs, like `test_deploy_postcheck.py` does with a fake outside world: `git grep`
goes to the real repository, everything else git, docker and curl do is faked.

Broken on purpose to check that these tests can go red: the comparison in
`rollback_can_start` inverted (`!=` for `=`) → both tests fall over, the one with
a migration because the rollback runs, the one without because it stops;
`$BACKUP_FILE` left out of the stop message → the dump test falls over.

**These tests need a real `git` binary.** CI has one. The `raaktest-runner`
container does not: run there, every test here fails on the assertion in `_repo`
("these tests need a real git binary"), which says nothing about `deploy.sh`.
Run them on a host with git, or in CI.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy.sh"
REAL_GIT = shutil.which("git")

MIGRATION = """revision = '{rev}'
down_revision = {down}
"""


def _repo(tmp_path, *, adds_migration: bool) -> Path:
    """Two refs: `v0.0.1` ends at migration a1; HEAD adds b2, or only code."""
    assert REAL_GIT, "these tests need a real git binary (CI has one)"
    repo = tmp_path / "repo"
    versions = repo / "backend" / "alembic" / "versions"
    versions.mkdir(parents=True)

    def git(*args):
        subprocess.run([REAL_GIT, "-C", str(repo), *args], check=True,
                       capture_output=True)

    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "test")
    (versions / "001_a1.py").write_text(MIGRATION.format(rev="a1", down="None"))
    git("add", "-A")
    git("commit", "-qm", "previous release")
    git("tag", "v0.0.1")
    if adds_migration:
        (versions / "002_b2.py").write_text(MIGRATION.format(rev="b2", down="'a1'"))
    else:
        (repo / "change.txt").write_text("code only\n")
    git("add", "-A")
    git("commit", "-qm", "new release")
    return repo


def _build(tmp_path, repo: Path):
    work = tmp_path / "checkout"
    (work / "tests").mkdir(parents=True)
    shutil.copy(DEPLOY, work / "deploy.sh")
    (work / "deploy.sh").chmod(0o755)

    smoke_counter = tmp_path / "smoke-runs"
    # The smoke test fails every time: that is what sends the script to the
    # rollback decision under test.
    (work / "tests" / "run-all.sh").write_text(
        f'#!/bin/sh\necho x >> "{smoke_counter}"\nexit 1\n')
    (work / "tests" / "run-all.sh").chmod(0o755)
    for name in (".env.uat", ".env.prod"):
        (work / name).write_text("FRONTEND_URL=http://site.test\n")

    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    # A running db container, so the deploy takes its pre-migration dump; the
    # database answers the revision it carries.
    (fakebin / "docker").write_text(
        '#!/bin/sh\ncase "$*" in\n'
        '  *"ps -q db"*) echo db123 ;;\n'
        '  *pg_dump*) echo "-- dump" ;;\n'
        '  *alembic_version*) echo b2 ;;\n'
        'esac\nexit 0\n')
    (fakebin / "curl").write_text('#!/bin/sh\nexit 0\n')
    (fakebin / "sleep").write_text('#!/bin/sh\nexit 0\n')
    (fakebin / "git").write_text(
        '#!/bin/sh\ncase "$1" in\n'
        '  describe) echo v0.0.2 ;;\n'
        '  rev-parse) echo deadbee ;;\n'
        f'  grep) exec "{REAL_GIT}" -C "{repo}" "$@" ;;\n'
        'esac\nexit 0\n')
    for f in fakebin.iterdir():
        f.chmod(0o755)
    return work, fakebin, smoke_counter


def _deploy(tmp_path, *, adds_migration: bool, environment: str = "prod"):
    repo = _repo(tmp_path, adds_migration=adds_migration)
    work, fakebin, smoke_counter = _build(tmp_path, repo)
    env = dict(os.environ)
    env["PATH"] = f"{fakebin}:{env['PATH']}"
    env["DEPLOY_REEXEC"] = "1"
    env["LOG_OUT"] = str(tmp_path / "deploy.log")
    env["BACKUP_DIR"] = str(tmp_path / "backups")
    env["DEPLOY_PREV_REF"] = "v0.0.1"
    done = subprocess.run(["bash", "./deploy.sh", environment, "v0.0.2"], cwd=work,
                          env=env, capture_output=True, text=True, timeout=120)
    return done, smoke_counter


@pytest.mark.parametrize("environment", ["uat", "prod"])
def test_a_release_with_a_migration_is_not_rolled_back(environment, tmp_path):
    done, smoke_counter = _deploy(tmp_path, adds_migration=True, environment=environment)

    assert done.returncode != 0, "a failed smoke test is still a failed deploy"
    assert "Automatische rollback" not in done.stdout, done.stdout[-3000:]
    assert "This release adds a migration" in done.stdout
    assert "v0.0.1 ends at a1" in done.stdout and "at b2" in done.stdout
    assert "Database revision now: b2" in done.stdout
    assert smoke_counter.read_text().count("x") == 1, "the rollback ran after all"


def test_the_stop_message_names_the_dump_of_this_deploy(tmp_path):
    """Whoever restores at three in the night should not have to look for it."""
    done, _ = _deploy(tmp_path, adds_migration=True)

    [dump] = list((tmp_path / "backups").glob("pre-deploy-prod-*.sql.gz"))
    assert f"Dump taken just before this deploy: {dump}" in done.stdout
    assert f"gunzip -c {dump} |" in done.stdout, "the restore command names the dump"
    assert "DEPLOY_ROLLBACK=1 ./deploy.sh prod v0.0.1" in done.stdout


def test_a_release_without_a_migration_still_rolls_back(tmp_path):
    """The counterproof: nothing changes for a release that adds no migration."""
    done, smoke_counter = _deploy(tmp_path, adds_migration=False)

    assert "No migration in this release (alembic head a1 on both refs)" in done.stdout
    assert "Automatische rollback naar v0.0.1" in done.stdout, done.stdout[-3000:]
    assert smoke_counter.read_text().count("x") == 2, (
        "the rollback did not re-run the smoke test, or rolled back more than once")
