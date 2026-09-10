"""#766 — the application log outlives a deploy.

Container logs belong to the **container**, and `up --build` creates a new one. For a
deploy log that is exactly right; for the application log it is not, because that one is
about what the app does and that does not stop at a deploy. Consequence today: every
question of the form *"does this actually happen?"* can only be answered for the period
since the last deploy, and that is usually short. #763 showed it concretely: a failed
payment creation leaves no trace, and a log line only fixes that if the line survives
the next deploy.

**The gate below is derived, not enumerated.** It walks the compose files that exist and
demands of EVERY backend block a volume that outlives the container. A list of three
names would be blind to a fourth environment — precisely the shape that went wrong three
times in #798 and #821: neatly in `.env`, never in the container.

A **named volume** and not a bind mount: the container runs as `app` (uid 10001) and a
bind mount to a directory Docker creates as root is not writable for it. A named volume
inherits ownership and permissions from `/var/log/raak` in the image.

Broken on purpose to check that these tests can go red: removed the volume from
`docker-compose.uat.yml` → the gate falls over naming that environment; removed the
`FileHandler` from `configure_logging` → the behaviour test falls over.
"""
import logging
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = "/var/log/raak"
# The environments the issue requires. Derived from the files on disk below; this set is
# only the floor, so that the test fails if it finds NOTHING (#678).
AT_LEAST = {"hdev", "uat", "prod"}


def _compose_files() -> dict[str, dict]:
    found = {}
    for path in sorted(ROOT.glob("docker-compose.*.yml")):
        environment = path.name.removeprefix("docker-compose.").removesuffix(".yml")
        config = yaml.safe_load(path.read_text())
        if "backend" in (config.get("services") or {}):
            found[environment] = config
    return found


def test_the_gate_finds_the_environments_it_must_guard():
    """#678: fourteen gates fetched their files without checking that they FOUND any. A
    moved file or a changed glob makes such a gate green forever."""
    assert AT_LEAST <= set(_compose_files()), (
        "the compose files with a backend were not found — this gate guards nothing")


@pytest.mark.parametrize("environment", sorted(AT_LEAST))
def test_the_backend_keeps_its_log_outside_the_container(environment):
    config = _compose_files()[environment]
    backend = config["services"]["backend"]
    mounts = backend.get("volumes") or []

    on_the_log_dir = [m for m in mounts if isinstance(m, str) and m.endswith(f":{LOG_DIR}")]
    assert on_the_log_dir, (
        f"{environment}: the backend mounts nothing on {LOG_DIR}, so the application "
        f"log disappears at the next `up --build`")

    source = on_the_log_dir[0].split(":")[0]
    assert not source.startswith("."), (
        f"{environment}: {source} is a bind mount. Docker creates such a directory as "
        f"root and the backend runs as uid 10001, so it cannot write there — a named "
        f"volume inherits the owner from the image")
    assert source in (config.get("volumes") or {}), (
        f"{environment}: {source} is not declared as a volume anywhere")


def test_the_image_creates_the_directory_with_the_right_owner():
    """A named volume inherits ownership from THIS point in the image. Without the
    directory it is root-owned and the app cannot write there — the mount is then
    present and the log still does not arrive."""
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text()

    assert f"mkdir -p {LOG_DIR}" in dockerfile and f"chown app:app {LOG_DIR}" in dockerfile
    created = dockerfile.index(f"mkdir -p {LOG_DIR}")
    assert created < dockerfile.index("USER app"), (
        "the directory is created after the image switches to the non-root user")


def test_lines_are_written_to_the_file_when_the_directory_exists(tmp_path, monkeypatch):
    """The behaviour itself: a log line ends up on disk as well."""
    from app.config import settings
    from app.logging_config import configure_logging

    monkeypatch.setattr(settings, "app_log_dir", str(tmp_path))
    try:
        configure_logging()
        logging.getLogger("test").warning("this must survive the deploy")
        for handler in logging.getLogger().handlers:
            handler.flush()
        content = (tmp_path / "app.log").read_text()
    finally:
        # Otherwise the FileHandler to tmp_path is dragged along through the rest of the
        # suite.
        monkeypatch.setattr(settings, "app_log_dir", "")
        configure_logging()

    assert "this must survive the deploy" in content
    assert "WARNING" in content


def test_a_missing_directory_does_not_block_startup(tmp_path, monkeypatch):
    """The counterproof that makes this safe. Locally and in CI there is no volume; an
    application that refuses to start over that is worse than a missing log."""
    from app.config import settings
    from app.logging_config import app_log_file, configure_logging

    monkeypatch.setattr(settings, "app_log_dir", str(tmp_path / "does-not-exist"))
    try:
        configure_logging()          # must not raise
        assert app_log_file() is None
        logging.getLogger("test").info("straight to stdout")
    finally:
        monkeypatch.setattr(settings, "app_log_dir", "")
        configure_logging()


def test_the_deploy_reports_whether_the_log_survived():
    """The issue asks for this check to be part of the deploy verification, so that a
    later change quietly undoing it stands out."""
    deploy = (ROOT / "deploy.sh").read_text()

    assert "applicatielog_regel" in deploy, "the deploy does not report the application log"
    assert "nacontrole()" in deploy and deploy.index("nacontrole()") < deploy.index(
        "  applicatielog_regel\n"), "the report sits outside the post-check"
    assert "/var/log/raak/app.log" in (ROOT / "logging.sh").read_text(), (
        "`raakctl diagnose` does not show the application log")


def test_raakctl_can_read_the_log_back():
    """A log that survives the deploy but cannot be read solves nothing:
    `docker compose logs` only knows the current container."""
    raakctl = (ROOT / "raakctl").read_text()

    assert 'if [ "$svc" = app ]' in raakctl, "`raakctl logs <env> app` does not exist"
    assert "echo app" in raakctl, "`app` is not in the list of log sources"
